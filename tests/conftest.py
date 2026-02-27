import pytest
from fastapi.testclient import TestClient

from app import app
from core.state import state
from core.security import create_access_token

@pytest.fixture
def client():
    """Client synchrone pour tester l'API FastAPI."""
    return TestClient(app)

@pytest.fixture
def test_token():
    """JWT token valide pour les tests qui nécessitent une authentification."""
    return create_access_token(data={"sub": "testuser"})

@pytest.fixture(autouse=True)
def reset_state():
    """Réinitialise l'état global avant chaque test pour éviter les effets de bord."""
    state["status"] = "idle"
    state["domain"] = ""
    state["logs"] = []
    state["process"] = None
    state["stats"] = None
    state["discovered_urls"] = []
    
    # Nettoyage manuel du pytest mocker si besoin
    yield
