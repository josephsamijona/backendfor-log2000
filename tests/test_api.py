import pytest
from unittest.mock import patch

from models.schemas import ScanRequest
from core.state import state

def test_get_status_idle(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["status"] == "idle"

def test_start_scan_success(client):
    # On mock run_locust_thread directement pour ne pas lancer Locust.
    # Évite de patcher threading.Thread.start globalement (casserait anyio/TestClient).
    with patch("api.routes.run_locust_thread") as mock_runner:
        response = client.post("/api/scan", json={"domain": "isteah.org"})

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["domain"] == "https://isteah.org"

        # Vérifie que l'état a été nettoyé/préparé
        assert state["domain"] == "https://isteah.org"
        assert state["stats"] is None

def test_start_scan_already_running(client):
    state["status"] = "running"
    response = client.post("/api/scan", json={"domain": "isteah.org"})

    # 409 Conflict attendu
    assert response.status_code == 409
    assert "Un test est déjà en cours" in response.json()["detail"]

def test_stop_scan_not_running(client):
    response = client.post("/api/stop")
    assert response.status_code == 200
    assert "error" in response.json()

def test_websocket_connection(client, test_token):
    """Teste la connexion initiale du WebSocket et sa réception du statut de base."""
    with client.websocket_connect(f"/ws/logs?token={test_token}") as websocket:
        # À la connexion, le serveur envoie immédiatement le status actuel
        data = websocket.receive_json()
        assert data["type"] == "status"
        assert data["data"] == state["status"]  # Devrait être 'idle' par défaut
