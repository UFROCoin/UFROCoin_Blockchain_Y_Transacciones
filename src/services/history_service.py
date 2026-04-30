from src.core.database import db_client

# --- Servicio de Historial ---

def get_wallet_history(address: str) -> list[dict]:
    db = db_client.get_database("ufrocoin")
    
    history = []
    
    pending_cursor = db.transactions.find(
        {"$or": [{"from": address}, {"to": address}]}
    )
    
    for tx in pending_cursor:
        tx["_id"] = str(tx["_id"])
        tx["status"] = "PENDING"
        history.append(tx)
        
    blocks_cursor = db.blocks.find()
    
    for block in blocks_cursor:
        for tx in block.get("transactions", []):
            if tx.get("from") == address or tx.get("to") == address:
                if "_id" in tx:
                    tx["_id"] = str(tx["_id"])
                
                tx["status"] = "CONFIRMED"
                history.append(tx)
                
    history.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    
    return history