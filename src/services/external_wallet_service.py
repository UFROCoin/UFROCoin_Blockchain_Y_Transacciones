import logging

# --- Inicializacion ---

logger = logging.getLogger(__name__)

# --- Lógica de Servicio Externo ---

class ExternalWalletService:
    def __init__(self, base_url:str = "http://modulo1-usuario:8000/api"):
        self.base_url = base_url

    def check_wallet_exist(self, address: str) -> bool:
        if not address or address.startswith("invalid"):
            return False
        
        return True