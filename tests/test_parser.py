import pytest
from unittest.mock import patch
from pathlib import Path

from services.parser import parse_csv_stats

# False data for testing
MOCK_CSV_STATS = """Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time,Min Response Time,Max Response Time,Average Content Size,Requests/s,Failures/s,50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%
GET,/api/users,100,5,50,55,10,200,1024,10.5,0.5,50,60,70,80,90,120,150,180,195,200,200
GET,/api/products,50,0,30,35,5,100,2048,5.2,0.0,30,35,40,45,50,80,90,95,98,100,100
None,Aggregated,150,5,45,48,5,200,1365,15.7,0.5,45,55,65,75,85,110,130,150,190,200,200
"""

@pytest.fixture
def mock_csv_dir(tmp_path):
    """Créer un dossier temporaire avec de faux fichiers CSV pour le test."""
    stats_file = tmp_path / "rapport_stats.csv"
    stats_file.write_text(MOCK_CSV_STATS, encoding="utf-8")
    
    # On ajoute un fichier history vide pour éviter une erreur s'il est lu mais qu'on ne le teste pas spécifiquement ici
    history_file = tmp_path / "rapport_stats_history.csv"
    history_file.write_text("Type,Name,Timestamp,User Count,Requests/s,Failures/s,50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%\n", encoding="utf-8")

    return tmp_path

def test_parse_csv_stats_success(mock_csv_dir):
    """Vérifie le parsing correct d'un fichier CSV Locust valide."""
    # On mock le CSV_DIR dans services.parser pour pointer vers notre tmp_path
    with patch("services.parser.CSV_DIR", mock_csv_dir):
        result = parse_csv_stats()
        
        assert result is not None
        assert "global" in result
        assert "endpoints" in result
        
        g = result["global"]
        assert g["num_requests"] == 150
        assert g["num_failures"] == 5
        assert g["median_response"] == 45.0
        assert g["p95_response"] == 110.0
        assert g["rps"] == 15.7
        # Calcul du failure rate attendu: (5 / 150) * 100 = 3.33
        assert g["failure_rate"] == 3.33
        
        # Vérification des endpoints individuels
        endpoints = result["endpoints"]
        assert len(endpoints) == 2
        assert endpoints[0]["name"] == "/api/users"
        assert endpoints[0]["requests"] == 100
        assert endpoints[0]["failures"] == 5
        
        assert endpoints[1]["name"] == "/api/products"
        assert endpoints[1]["requests"] == 50
        assert endpoints[1]["failures"] == 0

def test_parse_csv_stats_missing_files():
    """Vérifie que la fonction gère bien l'absence de fichiers CSV en renvoyant None."""
    # On pointe vers un chemin qui n'existe garantiement pas
    with patch("services.parser.CSV_DIR", Path("/path/does/not/exist/123987")):
        result = parse_csv_stats()
        assert result is None
