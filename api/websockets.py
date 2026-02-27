import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import jwt
from core.state import state, log_subscribers
from core.config import settings
from core.logger import get_logger

logger = get_logger("api.websockets")
router = APIRouter()

async def broadcast_log(line: str):
    """Envoie une ligne de log à tous les WebSocket connectés."""
    state["logs"].append(line)
    logger.info(f"[DIAG][broadcast_log] Envoi à {len(log_subscribers)} client(s): {line[:80]}")
    dead = []
    for ws in log_subscribers:
        try:
            await ws.send_text(json.dumps({"type": "log", "data": line}))
        except Exception as e:
            logger.warning(f"[DIAG][broadcast_log] ERREUR envoi WS: {e}")
            dead.append(ws)

    for ws in dead:
        logger.info(f"[DIAG][broadcast_log] Nettoyage client WS mort. Restants: {len(log_subscribers) - 1}")
        log_subscribers.remove(ws)


async def broadcast_status(new_status: str):
    old_status = state["status"]
    state["status"] = new_status
    logger.info(f"[DIAG][broadcast_status] ===== TRANSITION: '{old_status}' → '{new_status}' =====")
    logger.info(f"[DIAG][broadcast_status] Envoi à {len(log_subscribers)} client(s) WS")
    dead = []
    for ws in log_subscribers:
        try:
            await ws.send_text(json.dumps({"type": "status", "data": new_status}))
            logger.info(f"[DIAG][broadcast_status] Status '{new_status}' envoyé avec succès à un client")
        except Exception as e:
            logger.warning(f"[DIAG][broadcast_status] ERREUR envoi status WS: {e}")
            dead.append(ws)

    for ws in dead:
        logger.info(f"[DIAG][broadcast_status] Nettoyage client WS mort. Restants: {len(log_subscribers) - 1}")
        log_subscribers.remove(ws)


@router.websocket("/ws/logs")
async def websocket_logs(ws: WebSocket, token: str = Query(...)):
    # FIX: Validate JWT token before accepting the WebSocket connection
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username = payload.get("sub")
        if not username:
            await ws.close(code=1008)
            return
    except jwt.PyJWTError:
        logger.warning("[DIAG][ws_connect] Token WS invalide — connexion refusée")
        await ws.close(code=1008)
        return

    await ws.accept()
    log_subscribers.append(ws)
    logger.info(f"[DIAG][ws_connect] ===== NOUVEAU CLIENT WSocket ({username}) =====")
    logger.info(f"[DIAG][ws_connect] Total connectés: {len(log_subscribers)}")
    logger.info(f"[DIAG][ws_connect] Status actuel envoyé au client: '{state['status']}'")
    logger.info(f"[DIAG][ws_connect] Logs existants à envoyer: {len(state['logs'])} lignes")

    # Envoyer l'état actuel et les logs existants dès la connexion
    await ws.send_text(json.dumps({"type": "status", "data": state["status"]}))
    for log_line in state["logs"]:
        await ws.send_text(json.dumps({"type": "log", "data": log_line}))
    logger.info(f"[DIAG][ws_connect] Historique envoyé. En attente de nouveaux messages...")

    try:
        while True:
            await ws.receive_text()   # Garder la connexion ouverte
    except WebSocketDisconnect:
        logger.info(f"[DIAG][ws_disconnect] Client WebSocket déconnecté. Restants: {len(log_subscribers) - 1}")
        if ws in log_subscribers:
            log_subscribers.remove(ws)
