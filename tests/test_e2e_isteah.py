"""
╔══════════════════════════════════════════════════════════════╗
║   TEST END-TO-END — Backend LoadTest Dashboard               ║
║   Cible : https://isteah.org                                 ║
╠══════════════════════════════════════════════════════════════╣
║   Ce script teste le flux complet d'utilisation :            ║
║   Status → Scan → WebSocket → Stats → PDF → Stop            ║
║                                                              ║
║   Prérequis : uvicorn app:app --port 8000 doit tourner       ║
║   Usage     : python tests/test_e2e_isteah.py                ║
╚══════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import time
import sys

import httpx
import websockets

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/logs"
TARGET_DOMAIN = "https://isteah.org"

# Timeout max pour attendre la fin du test Locust (5 paliers de 30s + crawl)
MAX_WAIT_SECONDS = 300

# ── Compteurs ────────────────────────────────────────────────
passed = 0
failed = 0
results = []


def report(step: str, success: bool, detail: str = ""):
    global passed, failed
    icon = "✅" if success else "❌"
    if success:
        passed += 1
    else:
        failed += 1
    msg = f"  {icon}  {step}"
    if detail:
        msg += f"  —  {detail}"
    print(msg)
    results.append((step, success, detail))


async def main():
    global passed, failed

    print("\n" + "=" * 60)
    print("   TEST E2E — Backend LoadTest Dashboard")
    print(f"   Cible : {TARGET_DOMAIN}")
    print("=" * 60 + "\n")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:

        # ───────────────────────────────────────────────────────
        # ÉTAPE 1 : Vérifier le statut initial
        # ───────────────────────────────────────────────────────
        print("─── Étape 1 : Statut Initial ───")
        try:
            r = await client.get("/api/status")
            data = r.json()
            # On accepte idle OU done/error si un test précédent a tourné
            report(
                "GET /api/status",
                r.status_code == 200 and "status" in data,
                f"status={data.get('status')}"
            )
        except Exception as e:
            report("GET /api/status", False, str(e))
            print("\n  ⛔ Le serveur backend ne répond pas. Vérifiez que uvicorn tourne sur le port 8000.")
            return

        # ───────────────────────────────────────────────────────
        # ÉTAPE 2 : Lancer le scan
        # ───────────────────────────────────────────────────────
        print("\n─── Étape 2 : Lancement du Scan ───")
        try:
            r = await client.post("/api/scan", json={"domain": TARGET_DOMAIN})
            data = r.json()
            if r.status_code == 200 and data.get("ok"):
                report("POST /api/scan", True, f"domain={data.get('domain')}")
            elif r.status_code == 409:
                report("POST /api/scan", False, "Un test est déjà en cours (409). Attendez ou faites POST /api/stop.")
                return
            else:
                report("POST /api/scan", False, f"Code={r.status_code} Body={data}")
                return
        except Exception as e:
            report("POST /api/scan", False, str(e))
            return

        # ───────────────────────────────────────────────────────
        # ÉTAPE 3 & 4 & 5 : WebSocket — Logs en direct + transitions de statut
        # ───────────────────────────────────────────────────────
        print("\n─── Étape 3-5 : WebSocket — Suivi en direct ───")
        ws_connected = False
        statuses_seen = set()
        log_count = 0
        ws_logs_sample = []

        try:
            async with websockets.connect(WS_URL) as ws:
                ws_connected = True
                report("Connexion WebSocket /ws/logs", True)

                # Le premier message est le status initial (potentiellement stale)
                first_msg = True
                start_time = time.time()
                while time.time() - start_time < MAX_WAIT_SECONDS:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5)
                        msg = json.loads(raw)

                        if msg["type"] == "status":
                            status_val = msg["data"]
                            elapsed = int(time.time() - start_time)

                            if first_msg:
                                first_msg = False
                                if status_val in ("error", "done"):
                                    print(f"    ⏱ [{elapsed:>3}s] Statut initial stale ignoré → {status_val}")
                                    continue
                                # Si c'est idle ou crawling, c'est le vrai statut du nouveau scan
                                print(f"    ⏱ [{elapsed:>3}s] Statut initial → {status_val}")
                                statuses_seen.add(status_val)
                                continue

                            statuses_seen.add(status_val)
                            print(f"    ⏱ [{elapsed:>3}s] Statut → {status_val}")

                            if status_val == "done":
                                break
                            if status_val == "error":
                                print("    ⚠️  Le test Locust a terminé avec une erreur.")
                                break

                        elif msg["type"] == "log":
                            log_count += 1
                            if log_count <= 5 or log_count % 50 == 0:
                                ws_logs_sample.append(msg["data"])

                    except asyncio.TimeoutError:
                        # Pas de message pendant 5s, on continue d'attendre
                        elapsed = int(time.time() - start_time)
                        print(f"    ⏳ [{elapsed:>3}s] En attente de logs...")
                        continue
                    except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed) as e:
                        print(f"    ⚠️  Connexion WebSocket interrompue: {type(e).__name__}")
                        break

        except (asyncio.CancelledError, KeyboardInterrupt):
            print("    ⚠️  Script interrompu par l'utilisateur.")
        except Exception as e:
            if not ws_connected:
                report("Connexion WebSocket /ws/logs", False, str(e))
            else:
                print(f"    ⚠️  Erreur WebSocket inattendue: {e}")

        # Vérifications post-WebSocket
        report(
            "Logs reçus via WebSocket",
            log_count > 0,
            f"{log_count} messages de log reçus"
        )

        # Vérification des transitions de statut
        saw_crawling = "crawling" in statuses_seen
        saw_running = "running" in statuses_seen
        saw_done = "done" in statuses_seen
        saw_error = "error" in statuses_seen

        report(
            "Transition: crawling détecté",
            saw_crawling,
            f"Statuts vus: {statuses_seen}"
        )
        report(
            "Transition: running détecté",
            saw_running,
            f"Statuts vus: {statuses_seen}"
        )
        report(
            "Transition: done ou error détecté",
            saw_done or saw_error,
            f"Statuts vus: {statuses_seen}"
        )

        # ───────────────────────────────────────────────────────
        # ÉTAPE 6 : Récupérer les statistiques
        # ───────────────────────────────────────────────────────
        print("\n─── Étape 6 : Statistiques ───")
        try:
            r = await client.get("/api/stats")
            stats = r.json()
            has_global = "global" in stats and stats["global"].get("num_requests", 0) > 0
            report(
                "GET /api/stats",
                has_global,
                f"Requêtes={stats.get('global', {}).get('num_requests', 'N/A')} | "
                f"RPS={stats.get('global', {}).get('rps', 'N/A')} | "
                f"P95={stats.get('global', {}).get('p95_response', 'N/A')}ms | "
                f"Erreurs={stats.get('global', {}).get('failure_rate', 'N/A')}%"
            )
            endpoints = stats.get("endpoints", [])
            report(
                "Endpoints détectés dans stats",
                len(endpoints) > 0,
                f"{len(endpoints)} endpoint(s) trouvé(s)"
            )
        except Exception as e:
            report("GET /api/stats", False, str(e))

        # ───────────────────────────────────────────────────────
        # ÉTAPE 7 : Récupérer les logs accumulés
        # ───────────────────────────────────────────────────────
        print("\n─── Étape 7 : Logs accumulés ───")
        try:
            r = await client.get("/api/logs")
            logs_data = r.json()
            logs_list = logs_data.get("logs", [])
            report(
                "GET /api/logs",
                len(logs_list) > 0,
                f"{len(logs_list)} lignes de log accumulées"
            )
        except Exception as e:
            report("GET /api/logs", False, str(e))

        # ───────────────────────────────────────────────────────
        # ÉTAPE 8 : Télécharger le rapport PDF
        # ───────────────────────────────────────────────────────
        print("\n─── Étape 8 : Rapport PDF ───")
        try:
            r = await client.get("/api/report/pdf")
            content = r.content
            is_pdf = content[:5] == b"%PDF-"
            report(
                "GET /api/report/pdf",
                is_pdf and len(content) > 500,
                f"Taille={len(content)} octets | Commence par %PDF-: {is_pdf}"
            )
        except Exception as e:
            report("GET /api/report/pdf", False, str(e))

        # ───────────────────────────────────────────────────────
        # ÉTAPE 9 : Arrêt propre (idempotent)
        # ───────────────────────────────────────────────────────
        print("\n─── Étape 9 : Arrêt propre ───")
        try:
            r = await client.post("/api/stop")
            report(
                "POST /api/stop",
                r.status_code == 200,
                f"Réponse: {r.json()}"
            )
        except Exception as e:
            report("POST /api/stop", False, str(e))

        # ───────────────────────────────────────────────────────
        # ÉTAPE 10 : Statut final
        # ───────────────────────────────────────────────────────
        print("\n─── Étape 10 : Statut Final ───")
        try:
            r = await client.get("/api/status")
            data = r.json()
            final_status = data.get("status")
            report(
                "GET /api/status (final)",
                final_status in ("done", "idle", "error"),
                f"status={final_status}, domain={data.get('domain')}"
            )
        except Exception as e:
            report("GET /api/status (final)", False, str(e))

    # ───────────────────────────────────────────────────────
    # RAPPORT FINAL
    # ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("   RAPPORT FINAL")
    print("=" * 60)
    print(f"  ✅ Réussis : {passed}")
    print(f"  ❌ Échoués : {failed}")
    print(f"  📊 Total   : {passed + failed}")
    print("=" * 60)

    if ws_logs_sample:
        print("\n  📝 Échantillon de logs WebSocket reçus :")
        for line in ws_logs_sample[:8]:
            truncated = line[:100] + "..." if len(line) > 100 else line
            print(f"    │ {truncated}")

    if failed > 0:
        print("\n  ⛔ RÉSULTAT : ÉCHEC — Des étapes ont échoué.\n")
        sys.exit(1)
    else:
        print("\n  🎉 RÉSULTAT : SUCCÈS — Toutes les étapes sont passées !\n")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
