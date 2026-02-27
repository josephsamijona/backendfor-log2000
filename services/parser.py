import csv
from typing import Optional

from core.config import CSV_DIR
from core.logger import get_logger

logger = get_logger("services.parser")

def _safe_int(val, default=0) -> int:
    if val is None or val == "" or str(val).strip().upper() == "N/A":
        return default
    try:
        return int(float(val))  # On cast en float d'abord au cas où il y a des décimales
    except (ValueError, TypeError):
        return default

def _safe_float(val, default=0.0) -> float:
    if val is None or val == "" or str(val).strip().upper() == "N/A":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def parse_csv_stats() -> Optional[dict]:
    """Parse les fichiers CSV générés par Locust et retourne les stats structurées."""
    logger.debug("Début du parsing des fichiers CSV...")
    stats_file = CSV_DIR / "rapport_stats.csv"
    history_file = CSV_DIR / "rapport_stats_history.csv"

    result = {
        "global": {},
        "endpoints": [],
        "history": [],
    }

    # Stats globales et par endpoint
    if stats_file.exists():
        logger.info(f"Fichier trouvé: {stats_file.name}, début de l'extraction des données globales et URLs.")
        try:
            with open(stats_file, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Name") == "Aggregated":
                        result["global"] = {
                            "num_requests": _safe_int(row.get("Request Count")),
                            "num_failures": _safe_int(row.get("Failure Count")),
                            "median_response": _safe_float(row.get("50%")),
                            "p95_response": _safe_float(row.get("95%")),
                            "max_response": _safe_float(row.get("Max")),
                            "avg_response": _safe_float(row.get("Average (ms)")),
                            "rps": _safe_float(row.get("Requests/s")),
                            "failure_rate": 0.0,
                        }
                        total = result["global"]["num_requests"]
                        if total > 0:
                            result["global"]["failure_rate"] = round(
                                result["global"]["num_failures"] / total * 100, 2
                            )
                        logger.debug(f"Stats globales extraites: {result['global']}")
                    else:
                        result["endpoints"].append({
                            "name": row.get("Name", ""),
                            "method": row.get("Type", "GET"),
                            "requests": _safe_int(row.get("Request Count")),
                            "failures": _safe_int(row.get("Failure Count")),
                            "median": _safe_float(row.get("50%")),
                            "p95": _safe_float(row.get("95%")),
                            "max": _safe_float(row.get("Max")),
                            "rps": _safe_float(row.get("Requests/s")),
                        })
            logger.info(f"Extraction terminée: {len(result['endpoints'])} endpoints trouvés.")
        except Exception as e:
            logger.error(f"Erreur lors de la lecture de {stats_file.name}: {e}")
    else:
        logger.warning(f"Fichier CSV manquant: {stats_file.name}")

    # Historique temporel
    if history_file.exists():
        logger.info(f"Fichier trouvé: {history_file.name}, début de l'extraction de l'historique temporel.")
        try:
            with open(history_file, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                count = 0
                for row in reader:
                    if row.get("Name") == "Aggregated":
                        result["history"].append({
                            "timestamp": _safe_int(row.get("Timestamp")),
                            "users": _safe_int(row.get("User Count")),
                            "rps": _safe_float(row.get("Requests/s")),
                            "failures_s": _safe_float(row.get("Failures/s")),
                            "median": _safe_float(row.get("50%")),
                            "p95": _safe_float(row.get("95%")),
                            "p99": _safe_float(row.get("99%")),
                        })
                        count += 1
            logger.info(f"Extraction terminée: {count} points d'historique trouvés.")
        except Exception as e:
            logger.error(f"Erreur lors de la lecture de {history_file.name}: {e}")
    else:
        logger.warning(f"Fichier CSV d'historique manquant: {history_file.name}")

    if result["global"]:
        logger.debug("Parsing CSV réussi (données globales présentes).")
        return result
    else:
        logger.warning("Parsing terminé mais aucune donnée globale trouvée. Renvoi de None.")
        return None

