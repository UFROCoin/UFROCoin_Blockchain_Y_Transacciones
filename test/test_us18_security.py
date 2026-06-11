import pytest
from unittest.mock import MagicMock, patch
from src.services.transaction_service import TransactionService

# --- Configuración del entorno de prueba ---

@pytest.fixture
def mock_db():
    client = MagicMock()
    db = MagicMock()
    db.transactions = MagicMock()
    db.blocks = MagicMock()
    db.blocks.find.return_value = []
    db.__getitem__.side_effect = {
        "transactions": db.transactions,
        "blocks": db.blocks,
    }.__getitem__
    client.__getitem__.return_value = db
    return client

@pytest.fixture
def service(mock_db):
    with patch('src.services.transaction_service.RabbitMQPublisher'), \
         patch('src.services.transaction_service.ExternalWalletService') as mock_wallet:
        
        svc = TransactionService(mock_db)
        svc.wallet_service = mock_wallet.return_value
        
        svc.wallet_service.check_wallet_exist.return_value = True
        svc.transactions_collection.count_documents.return_value = 0
        
        mock_insert_result = MagicMock()
        mock_insert_result.inserted_id = "mock_tx_123"
        svc.transactions_collection.insert_one.return_value = mock_insert_result
        
        return svc

# --- Datos base de prueba ---

def get_base_tx_data():
    return {
        "from": "billetera_origen",
        "to": "billetera_destino",
        "amount": 10.0,
        "type": "TRANSFER",
        "timestamp": "2026-04-13T12:00:00Z"
    }

# --- Casos de Prueba US-18 ---

def test_monto_cero_o_negativo(service):
    tx_data = get_base_tx_data()
    tx_data["amount"] = 0
    
    # Texto actualizado
    with pytest.raises(ValueError, match="El monto de la transacción debe ser mayor a cero"):
        service.create_transfer(tx_data)
        
    tx_data["amount"] = -5
    with pytest.raises(ValueError, match="El monto de la transacción debe ser mayor a cero"):
        service.create_transfer(tx_data)

def test_exceso_de_decimales(service):
    tx_data = get_base_tx_data()
    tx_data["amount"] = 10.555  
    
    # Texto actualizado
    with pytest.raises(ValueError, match="El monto de la transacción no puede tener más de 2 decimales"):
        service.create_transfer(tx_data)

def test_wallet_origen_no_existe(service):
    tx_data = get_base_tx_data()
    service.wallet_service.check_wallet_exist.side_effect = lambda addr: addr != "billetera_origen"
    
    with pytest.raises(ValueError, match="La wallet de origen es invalida o no existe"):
        service.create_transfer(tx_data)

def test_wallet_destino_no_existe(service):
    tx_data = get_base_tx_data()
    service.wallet_service.check_wallet_exist.side_effect = lambda addr: addr != "billetera_destino"
    
    with pytest.raises(ValueError, match="La wallet de destino es invalida o no existe"):
        service.create_transfer(tx_data)

def test_limite_transacciones_pendientes_superado(service):
    tx_data = get_base_tx_data()
    service.transactions_collection.count_documents.return_value = 10
    
    # Texto actualizado
    with pytest.raises(ValueError, match="No se pueden crear más de 10 transacciones pendientes para la misma wallet de origen"):
        service.create_transfer(tx_data)

def test_transaccion_exitosa_cumple_reglas(service):
    tx_data = get_base_tx_data()
    service.calculate_balance = MagicMock(return_value=100.0)
    
    resultado = service.create_transfer(tx_data)
    
    assert resultado["_id"] == "mock_tx_123"
    assert resultado["amount"] == 10.0
    assert service.transactions_collection.insert_one.called
