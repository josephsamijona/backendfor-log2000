import asyncio
import threading
import pytest
from unittest.mock import patch, MagicMock

from services.locust_runner import run_locust_thread
from core.state import state

@pytest.fixture
def mock_subprocess_popen():
    with patch("subprocess.Popen") as mock_popen:
        # Configuration d'un faux processus qui se termine tout de suite
        process_mock = MagicMock()
        process_mock.pid = 9999
        process_mock.returncode = 0

        # text=True dans Popen → readline() retourne des str (plus des bytes)
        process_mock.stdout.readline.side_effect = [
            "[2023-10-27 10:00:00] Starting Locust 2.15.1\n",
            "  5 URL(s) utilisees pour le test de charge.\n",  # Trigger crawl→running
            "Hello Locust test line\n",
            ""  # Sentinelle de fin de flux (str vide)
        ]

        mock_popen.returncode = 0
        mock_popen.return_value = process_mock
        yield mock_popen

def test_run_locust_thread_success(mock_subprocess_popen):
    """Vérifie que run_locust_thread met à jour l'état et lance le subprocess."""
    state["status"] = "idle"
    state["logs"] = []

    with patch("services.locust_runner.parse_csv_stats", return_value={
        "global": {"num_requests": 10, "failure_rate": 0, "rps": 1, "p95_response": 100}
    }):
        # La loop doit être active pour que asyncio.run_coroutine_threadsafe fonctionne.
        # On la fait tourner dans un thread daemon (comme en production).
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()

        run_locust_thread("https://test.com", loop)

        # Arrêter proprement la loop
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=5)
        loop.close()

        # subprocess.Popen appelé avec le bon host et --csv
        args, kwargs = mock_subprocess_popen.call_args
        assert any("--host=https://test.com" in cmd for cmd in args[0])
        assert any("--csv=" in cmd for cmd in args[0])

        # État final attendu : done
        assert state["status"] == "done"

        # Les logs clés ont bien été broadcastés
        logs_str = " ".join(state["logs"])
        assert "[DÉMARRAGE]" in logs_str
        assert "Hello Locust test line" in logs_str
        assert "[TERMINÉ]" in logs_str
