import logging
import sys

def get_logger(name: str) -> logging.Logger:
    """Crée et configure un logger standard pour l'application."""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Format des logs structuré
        formatter = logging.Formatter(
            "%(asctime)s - [%(levelname)s] - %(name)s : %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # Sortie vers la console (stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
    return logger
