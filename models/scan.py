from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class ScanHistoryBase(BaseModel):
    domain: str
    total_requests: int
    failures: int
    error_rate: float
    avg_rps: float
    p95_latency: float

class ScanHistoryCreate(ScanHistoryBase):
    global_stats: Optional[Dict[str, Any]] = None # Store raw stats dump just in case

class ScanHistoryInDB(ScanHistoryBase):
    id: str
    user_id: str # The user who ran the scan
    created_at: datetime = Field(default_factory=datetime.utcnow)
    global_stats: Optional[Dict[str, Any]] = None

class ScanHistoryResponse(ScanHistoryBase):
    id: str
    user_id: str
    created_at: datetime
    # We might omit global_stats to keep the list lightweight
