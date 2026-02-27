import asyncio
import io
import threading
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from datetime import datetime

from core.database import get_db
from core.config import CSV_DIR
from core.state import state
from models.schemas import ScanRequest
from models.user import UserInDB
from api.auth import get_current_user
from services.parser import parse_csv_stats
from services.locust_runner import run_locust_thread
from services.reporter import build_pdf
from services.scan_service import get_user_global_stats, get_scan_details
from core.logger import get_logger
from bson import ObjectId

logger = get_logger("api.routes")
router = APIRouter()


@router.get("/status")
async def get_status():
    logger.debug(f"/status appelé. Statut actuel: {state['status']}")
    return {"status": state["status"], "domain": state["domain"]}


@router.post("/scan")
async def start_scan(req: ScanRequest, current_user: UserInDB = Depends(get_current_user)):
    """Lance le test de charge Locust en subprocess headless."""
    logger.info(f"========== POST /api/scan APPELÉ par {current_user.username} ==========")
    logger.info(f"[DIAG] Domaine demandé: {req.domain}")
    logger.info(f"[DIAG] État AVANT scan: status={state['status']}, domain={state['domain']}, logs_count={len(state['logs'])}, stats={'oui' if state['stats'] else 'non'}, process={state['process']}")

    if state["status"] in ("crawling", "running"):
        logger.warning(f"[DIAG] REJET: un test est déjà en cours ({state['status']})")
        raise HTTPException(status_code=409, detail="Un test est déjà en cours")

    domain = req.domain.strip().rstrip("/")
    if not domain.startswith(("http://", "https://")):
        domain = "https://" + domain
    logger.info(f"[DIAG] Domaine final après formatage: {domain}")

    logger.info(f"[DIAG] Reset de state: logs=[], stats=None, status='idle'")
    state["status"] = "idle"
    state["domain"] = domain
    state["logs"] = []
    state["stats"] = None
    state["discovered_urls"] = []

    # Supprimer les anciens CSV
    logger.info("[DIAG] Nettoyage des anciens fichiers CSV de rapport...")
    csv_count = 0
    for csv_file in CSV_DIR.glob("rapport_*.csv"):
        try:
            csv_file.unlink(missing_ok=True)
            csv_count += 1
            logger.info(f"[DIAG] CSV supprimé: {csv_file.name}")
        except Exception as e:
            logger.error(f"[DIAG] ERREUR suppression {csv_file.name}: {e}")
    logger.info(f"[DIAG] {csv_count} fichier(s) CSV nettoyé(s)")

    loop = asyncio.get_running_loop()
    logger.info(f"[DIAG] Event loop obtenu: {loop}, running={loop.is_running()}, closed={loop.is_closed()}")
    logger.info(f"[DIAG] Lancement du thread Locust MAINTENANT pour {domain}")
    t = threading.Thread(
        target=run_locust_thread,
        args=(domain, loop, current_user.id),
        daemon=True
    )
    t.start()
    logger.info(f"[DIAG] Thread Locust démarré: name={t.name}, is_alive={t.is_alive()}")
    logger.info(f"[DIAG] État APRÈS lancement du thread: status={state['status']}")
    return {"ok": True, "domain": domain}


@router.post("/stop")
async def stop_scan(current_user: UserInDB = Depends(get_current_user)):
    """Arrête le test en cours."""
    logger.info(f"========== POST /api/stop APPELÉ par {current_user.username}==========")
    proc = state.get("process")
    logger.info(f"[DIAG] État actuel: status={state['status']}, process={proc}, returncode={proc.returncode if proc else 'N/A'}")
    if proc and proc.returncode is None:
        logger.info(f"[DIAG] Terminaison du processus Locust (PID: {proc.pid})")
        proc.terminate()
        state["status"] = "idle"
        logger.info(f"[DIAG] Status changé à 'idle'")
        return {"ok": True}

    logger.warning(f"[DIAG] Aucun processus Locust en cours. process={proc}")
    return {"error": "Aucun test en cours"}


@router.get("/stats")
async def get_stats(current_user: UserInDB = Depends(get_current_user)):
    logger.info(f"========== GET /api/stats APPELÉ ==========")
    logger.info(f"[DIAG] stats en mémoire: {'oui' if state['stats'] else 'non'}")
    if state["stats"]:
        g = state["stats"].get("global", {})
        logger.info(f"[DIAG] Stats en cache: requests={g.get('num_requests')}, rps={g.get('rps')}, p95={g.get('p95_response')}")
        return state["stats"]

    # Essayer de parser si les CSV existent
    logger.info("[DIAG] Stats absentes en mémoire, tentative de parsing CSV...")
    stats = parse_csv_stats()
    if stats:
        logger.info(f"[DIAG] Parsing CSV réussi: {stats.get('global', {})}")
        state["stats"] = stats
        return stats

    logger.warning("[DIAG] AUCUNE statistique trouvée (ni en mémoire ni dans les CSV).")
    return {"error": "Aucune donnée disponible"}


@router.get("/logs")
async def get_logs(current_user: UserInDB = Depends(get_current_user)):
    """Retourne tous les logs accumulés (pour reconnexion)."""
    logger.debug("/logs appelé.")
    return {"logs": state["logs"]}


@router.get("/scans")
async def get_scans(current_user: UserInDB = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection not initialized")

    cursor = db.scans.find({"user_id": current_user.id}).sort("created_at", -1)
    scans = await cursor.to_list(length=100)

    for scan in scans:
        scan["id"] = str(scan["_id"])
        del scan["_id"]
        # Do not send raw global stats dump in the list for performance reasons
        if "global_stats" in scan:
            del scan["global_stats"]

    return scans


@router.get("/scans/summary")
async def get_scans_summary(current_user: UserInDB = Depends(get_current_user)):
    """Retourne les statistiques globales de l'utilisateur pour le Dashboard Home."""
    stats = await get_user_global_stats(current_user.id)
    return stats


@router.get("/scans/{scan_id}/details")
async def get_scan_details_route(scan_id: str, current_user: UserInDB = Depends(get_current_user)):
    """Retourne les statistiques complètes d'un scan spécifique."""
    # FIX: Check "current" BEFORE any DB lookup to avoid bson.InvalidId crash
    if scan_id == "current":
        if state["stats"]:
            return state["stats"]
        raise HTTPException(status_code=404, detail="No active scan stats available")

    scan = await get_scan_details(scan_id, current_user.id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found or unauthorized")

    if "global_stats" not in scan:
        raise HTTPException(status_code=404, detail="No detailed stats found for this scan")

    return {"global": scan["global_stats"], "_id": scan["id"]}


@router.get("/report/pdf")
async def generate_pdf(scan_id: str = None, current_user: UserInDB = Depends(get_current_user)):
    """Génère et retourne le rapport PDF."""
    logger.info("Demande de génération de rapport PDF reçue.")

    # Fetch from memory OR from historical DB
    stats = None
    if scan_id:
        scan = await get_scan_details(scan_id, current_user.id)
        if scan and "global_stats" in scan:
            stats = {"global": scan["global_stats"]}
    else:
        stats = state.get("stats") or parse_csv_stats()

    if not stats or not stats.get("global"):
        logger.error("Génération PDF impossible: aucune donnée de statistique disponible.")
        raise HTTPException(status_code=404, detail="Aucune donnée disponible pour générer le rapport")

    logger.info("Construction du PDF en cours...")
    try:
        buffer = io.BytesIO()
        build_pdf(buffer, stats)
        buffer.seek(0)
        logger.info("PDF généré avec succès.")

        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="rapport_load_test.pdf"'},
        )
    except Exception as e:
        logger.exception(f"Erreur inattendue pendant la génération du PDF: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne lors de la création du PDF")


@router.delete("/scans/{scan_id}")
async def delete_scan(scan_id: str, current_user: UserInDB = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection not initialized")

    result = await db.scans.delete_one({"_id": ObjectId(scan_id), "user_id": current_user.id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Scan not found or not authorized to delete")

    return {"ok": True, "deleted_id": scan_id}
