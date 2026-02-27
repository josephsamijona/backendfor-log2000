from fastapi import WebSocket

state = {
    "status": "idle",  # idle | crawling | running | done | error
    "domain": "",
    "logs": [],
    "process": None,
    "stats": None,
    "discovered_urls": [],
}

log_subscribers: list[WebSocket] = []
