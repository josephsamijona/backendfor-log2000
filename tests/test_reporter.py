import io
import pytest
from reportlab.pdfgen.canvas import Canvas

from services.reporter import build_pdf

@pytest.fixture
def mock_stats():
    return {
        "global": {
            "num_requests": 1500,
            "num_failures": 15,
            "failure_rate": 1.0,
            "rps": 25.5,
            "median_response": 45.0,
            "p95_response": 110.0,
            "max_response": 450.0,
        },
        "endpoints": [
            {
                "name": "/api/test",
                "method": "GET",
                "requests": 1500,
                "failures": 15,
                "median": 45.0,
                "p95": 110.0,
                "max": 450.0,
                "rps": 25.5,
            }
        ],
        "history": []
    }

def test_build_pdf_success(mock_stats):
    """Vérifie que le PDF est généré sans erreur et contient des données."""
    # On utilise un buffer en mémoire pour ne pas créer de fichier sur le disque
    pdf_buffer = io.BytesIO()
    
    # On exécute la fonction avec nos fausses statistiques
    # Cette étape lève une exception si reportlab échoue
    build_pdf(pdf_buffer, mock_stats)
    
    # On vérifie que des données ont bien été écrites dans le buffer
    pdf_buffer.seek(0)
    pdf_content = pdf_buffer.read()
    
    # Un fichier PDF valide commence toujours par %PDF-
    assert pdf_content.startswith(b"%PDF-")
    
    # On vérifie que la taille du fichier généré est raisonnable (> qqs centaines d'octets)
    assert len(pdf_content) > 500

def test_build_pdf_empty_endpoints(mock_stats):
    """Vérifie que le PDF se génère même sans endpoints."""
    # On vide la liste des endpoints
    mock_stats["endpoints"] = []
    
    pdf_buffer = io.BytesIO()
    build_pdf(pdf_buffer, mock_stats)
    
    pdf_buffer.seek(0)
    pdf_content = pdf_buffer.read()
    
    assert pdf_content.startswith(b"%PDF-")
    assert len(pdf_content) > 500
