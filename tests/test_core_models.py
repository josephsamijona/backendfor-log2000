import pytest
from pydantic import ValidationError

from models.schemas import ScanRequest
from core.state import state

def test_scan_request_valid():
    """Vérifie qu'un domaine valide passe la validation."""
    req = ScanRequest(domain="https://isteah.org")
    assert req.domain == "https://isteah.org"
    
def test_scan_request_invalid_type():
    """Vérifie que Pydantic rejette un type invalide."""
    with pytest.raises(ValidationError):
        # On essaie de passer un entier alors qu'une chaîne est attendue
        ScanRequest(domain=["not a string"])

def test_initial_state():
    """Vérifie que le state a la configuration par défaut attendue."""
    assert state["status"] == "idle"
    assert state["domain"] == ""
    assert isinstance(state["logs"], list)
    assert len(state["logs"]) == 0
    assert state["process"] is None
    assert state["stats"] is None
