from src.core.database import get_db_client

# --- Logica de Historial ---

def get_wallet_history(address: str, page: int = 1, limit: int = 10) -> list[dict]:
    client = get_db_client()
    db = client.get_database("blockchain_db")
    
    history = []
    skip = (page - 1) * limit
    
    query = {"$or": [{"from": address}, {"to": address}]}
    
    pending_cursor = db.transacciones.find(query)
    
    for tx in pending_cursor:
        tx["_id"] = str(tx["_id"])
        if not tx.get("status"):
            tx["status"] = "PENDING"
        history.append(tx)
        
    blocks_cursor = db.blocks.find({
        "transactions": {
            "$elemMatch": {
                "$or": [{"from": address}, {"to": address}]
            }
        }
    })
    
    for block in blocks_cursor:
        for tx in block.get("transactions", []):
            if tx.get("from") == address or tx.get("to") == address:
                if "_id" in tx:
                    tx["_id"] = str(tx["_id"])
                
                tx["status"] = "CONFIRMED"
                tx["block_index"] = block.get("index")
                history.append(tx)
                
    history.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    
    return history[skip : skip + limit]