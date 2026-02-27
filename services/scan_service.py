from core.database import get_db
from bson import ObjectId

async def get_user_global_stats(user_id: str):
    db = get_db()
    
    # Provide sensible defaults if no scans exist
    default_stats = {
        "total_scans": 0,
        "unique_domains": 0,
        "total_requests": 0,
        "avg_error_rate": 0.0,
        "avg_rps": 0.0,
        "avg_p95_latency": 0.0
    }
    
    if db is None:
        return default_stats
        
    pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id": None,
                "total_scans": {"$sum": 1},
                "unique_domains_set": {"$addToSet": "$domain"},
                "total_requests": {"$sum": "$total_requests"},
                "avg_error_rate": {"$avg": "$error_rate"},
                "avg_rps": {"$avg": "$avg_rps"},
                "avg_p95_latency": {"$avg": "$p95_latency"}
            }
        },
        {
            "$project": {
                "_id": 0,
                "total_scans": 1,
                "unique_domains": {"$size": "$unique_domains_set"},
                "total_requests": 1,
                "avg_error_rate": {"$round": ["$avg_error_rate", 2]},
                "avg_rps": {"$round": ["$avg_rps", 1]},
                "avg_p95_latency": {"$round": ["$avg_p95_latency", 1]}
            }
        }
    ]
    
    cursor = db.scans.aggregate(pipeline)
    result = await cursor.to_list(length=1)
    
    if result and len(result) > 0:
        return result[0]
        
    return default_stats

async def get_scan_details(scan_id: str, user_id: str):
    db = get_db()
    if db is None:
        return None
        
    try:
        scan = await db.scans.find_one({"_id": ObjectId(scan_id), "user_id": user_id})
        if scan:
            scan["id"] = str(scan["_id"])
            del scan["_id"]
            return scan
    except Exception:
        pass
    
    return None
