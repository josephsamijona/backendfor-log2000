import asyncio
import os
import subprocess
import sys
import threading
import traceback
from core.config import BASE_DIR, MAIN_PY, CSV_DIR
from core.state import state
from services.parser import parse_csv_stats
from api.websockets import broadcast_log, broadcast_status
from core.logger import get_logger

logger = get_logger("services.locust_runner")

MAX_DURATION = 360  # 6 minutes — hard limit (crawl ~60s + test 150s + marge)


from core.database import get_db

def _kill_if_running(proc):
    if proc.poll() is None:
        logger.warning("[WATCHDOG] Durée max atteinte — processus Locust forcé à s'arrêter")
        proc.terminate()

def run_locust_thread(domain: str, loop, user_id: str = None):
    """Lance Locust en subprocess dans un thread séparé."""
    logger.info(f"[DIAG][THREAD] ===== THREAD LOCUST DÉMARRÉ =====")
    logger.info(f"[DIAG][THREAD] domain={domain}")
    logger.info(f"[DIAG][THREAD] loop={loop}, loop.is_running={loop.is_running()}, loop.is_closed={loop.is_closed()}")
    logger.info(f"[DIAG][THREAD] state['status'] AU DÉBUT DU THREAD = '{state['status']}'")

    def _broadcast(coro):
        try:
            logger.info(f"[DIAG][THREAD] _broadcast: envoi coroutine au loop...")
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            result = future.result(timeout=5)
            logger.info(f"[DIAG][THREAD] _broadcast: coroutine terminée avec succès")
        except Exception as e:
            logger.error(f"[DIAG][THREAD] _broadcast ERREUR: {type(e).__name__}: {e}")

    logger.info(f"[DIAG][THREAD] Appel broadcast_status('crawling')...")
    _broadcast(broadcast_status("crawling"))
    logger.info(f"[DIAG][THREAD] state['status'] APRÈS crawling broadcast = '{state['status']}'")
    _broadcast(broadcast_log(f"[DÉMARRAGE] Cible : {domain}"))

    csv_prefix = str(CSV_DIR / "rapport")

    cmd = [
        sys.executable, "-u", "-m", "locust",  # -u = stdout non bufferisé
        "-f", str(MAIN_PY),
        f"--host={domain}",
        "--headless",
        f"--csv={csv_prefix}",
        "--csv-full-history",
        "--loglevel=INFO",
    ]

    cmd_str = ' '.join(cmd)
    logger.debug(f"Commande Locust as subprocess: {cmd_str}")
    _broadcast(broadcast_log(f"[CMD] {cmd_str}"))

    try:
        logger.info(f"[DIAG][THREAD] Lancement subprocess.Popen pour {domain}")
        logger.info(f"[DIAG][THREAD] CWD = {str(BASE_DIR)}")
        logger.info(f"[DIAG][THREAD] MAIN_PY = {str(MAIN_PY)}, exists={MAIN_PY.exists()}")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(BASE_DIR),
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
        )
        state["process"] = proc
        logger.info(f"[DIAG][THREAD] Subprocess Locust démarré avec PID: {proc.pid}")
        logger.info(f"[DIAG][THREAD] state['process'] assigné. proc.returncode={proc.returncode}")

        watchdog = threading.Timer(MAX_DURATION, _kill_if_running, args=(proc,))
        watchdog.daemon = True
        watchdog.start()

        crawl_done = False
        logger.debug("Début de la lecture du stdout du processus Locust")
        for line in iter(proc.stdout.readline, ""):
            line = line.rstrip()
            if not line:
                continue

            # Synchroniser les URLs découvertes dans le state partagé.
            # Le crawler imprime chaque URL sur une ligne "    - /chemin"
            stripped = line.strip()
            if stripped.startswith("- /") or (stripped.startswith("- http") and "://" in stripped):
                url_part = stripped[2:].strip()
                if url_part and url_part not in state["discovered_urls"]:
                    state["discovered_urls"].append(url_part)

            # Detect crawl -> running transition.
            # On attend la ligne imprimée APRÈS le crawl dans on_test_start()
            # ("URL(s) utilisees pour le test" sans accent, ou le banner final).
            # On évite "LOAD TEST" qui apparaît AVANT le crawl dans on_test_start.
            if not crawl_done and (
                "URL(s) utilisees pour le test" in line   # fin du crawl (main.py l.302)
                or "utilisees pour le test de charge" in line  # variante
                or "Aucune URL decouverte" in line         # cas sans URL
                or "All users spawned" in line             # Locust démarre les users
                or "Spawning is complete" in line          # Locust ancien format
            ):
                crawl_done = True
                logger.info("Transition détectée: Crawl terminé -> Lancement du Test")
                _broadcast(broadcast_status("running"))

            logger.debug(f"[Locust Stdout] {line}")
            _broadcast(broadcast_log(line))

        proc.wait()
        watchdog.cancel()
        exit_code = proc.returncode
        logger.info(f"Process Locust terminé avec le code d'arrêt: {exit_code}")

        # Parse CSV stats
        logger.info("Parsing final des statistiques CSV...")
        stats = parse_csv_stats()
        state["stats"] = stats

        if exit_code != 0 and not stats:
            error_msg = f"Locust a terminé de manière inattendue avec le code {exit_code}"
            logger.error(error_msg)
            _broadcast(broadcast_log(f"[ERREUR] {error_msg}"))
            _broadcast(broadcast_status("error"))
        else:
            logger.info("Test de charge Locust complété avec succès.")
            _broadcast(broadcast_status("done"))
            _broadcast(broadcast_log("[TERMINÉ] Test de charge terminé."))
            if stats:
                g = stats["global"]
                result_str = (
                    f"{g['num_requests']} requêtes | "
                    f"Erreurs: {g['failure_rate']}% | "
                    f"RPS: {g['rps']:.1f} | "
                    f"P95: {g['p95_response']:.1f}ms"
                )
                logger.info(f"Résumé stats: {result_str}")
                _broadcast(broadcast_log(f"[RÉSULTAT] {result_str}"))

                # Save to DB
                if user_id:
                    async def save_to_db():
                        db = get_db()
                        if db is not None:
                            import datetime
                            scan_doc = {
                                "domain": domain,
                                "total_requests": g['num_requests'],
                                "failures": g['num_failures'],
                                "error_rate": g['failure_rate'],
                                "avg_rps": g['rps'],
                                "p95_latency": g['p95_response'],
                                "global_stats": g,
                                "user_id": user_id,
                                "created_at": datetime.datetime.utcnow()
                            }
                            await db.scans.insert_one(scan_doc)
                            logger.info(f"Scan history saved to database for user {user_id}")
                    _broadcast(save_to_db())

    except Exception as e:
        logger.exception(f"Exception non gérée dans le thread Locust runner: {e}")
        _broadcast(broadcast_log(f"[ERREUR] {e}"))
        _broadcast(broadcast_log(f"[TRACEBACK] {traceback.format_exc()}"))
        _broadcast(broadcast_status("error"))
    finally:
        logger.debug("Nettoyage: state['process'] mis à None")
        state["process"] = None

