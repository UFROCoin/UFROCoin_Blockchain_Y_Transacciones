"""
Fixtures compartidas para los tests del proyecto UFROCoin.

Provee:
- Mock del cliente MongoDB (colecciones transacciones y blocks).
- TransactionService instanciado con mocks (sin dependencias externas).
- TestClient de FastAPI con dependency override para aislar tests de infra.
- Datos de ejemplo reutilizables (transacción pendiente, bloque confirmado, etc.).
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Datos de ejemplo
# ---------------------------------------------------------------------------

VALID_OBJECT_ID = "683f1a2b3c4d5e6f7a8b9c0d"
NONEXISTENT_OBJECT_ID = "000000000000000000000000"

SAMPLE_PENDING_TX_DOC = {
    "_id": __import__("bson").ObjectId(VALID_OBJECT_ID),
    "from": "a1b2c3d4e5f678901234567890abcdef12345678",
    "to": "b1c2d3e4f5a678901234567890abcdef12345678",
    "amount": 25.0,
    "type": "TRANSFER",
    "status": "PENDING",
    "timestamp": "2026-06-03T22:45:00+00:00",
    "block_index": None,
}

SAMPLE_CONFIRMED_TX_IN_BLOCK = {
    "id": "683f1a2b3c4d5e6f7a8b9c0d",
    "from": "a1b2c3d4e5f678901234567890abcdef12345678",
    "to": "b1c2d3e4f5a678901234567890abcdef12345678",
    "amount": 50.0,
    "type": "TRANSFER",
    "timestamp": "2026-06-02T10:00:00+00:00",
}

SAMPLE_BLOCK = {
    "index": 3,
    "timestamp": "2026-06-02T12:00:00+00:00",
    "transactions": [SAMPLE_CONFIRMED_TX_IN_BLOCK],
    "previous_hash": "a" * 64,
    "nonce": 12345,
    "hash": "b" * 64,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db_client():
    """Cliente MongoDB falso con colecciones transacciones y blocks."""
    client = MagicMock()
    db = MagicMock()
    client.blockchain_db = db

    # Colección transacciones (mempool)
    db.transacciones = MagicMock()
    db.transacciones.find_one.return_value = None
    db.transacciones.find.return_value = []

    # Colección blocks
    db.blocks = MagicMock()
    db.blocks.find.return_value = []

    return client


@pytest.fixture()
def mock_transaction_service(mock_db_client):
    """TransactionService con dependencias externas parcheadas."""
    with (
        patch("src.services.transaction_service.RabbitMQPublisher"),
        patch("src.services.transaction_service.ExternalWalletService"),
    ):
        from src.services.transaction_service import TransactionService

        service = TransactionService(mock_db_client)
    return service


@pytest.fixture()
def test_app():
    """
    Crea una instancia limpia de FastAPI SIN lifespan (evita initialize_database
    y GenesisService) e incluye los routers relevantes.
    """
    app = FastAPI(title="UFROCoin Test App")

    from src.api.global_router import router as global_router
    from src.api.transaction_router import router as transaction_router

    app.include_router(global_router)
    app.include_router(transaction_router, prefix="/api")

    return app


@pytest.fixture()
def test_client(test_app, mock_transaction_service):
    """
    TestClient de FastAPI con el TransactionService mockeado inyectado
    como dependency override.
    """
    from src.api.transaction_router import get_transaction_service

    test_app.dependency_overrides[get_transaction_service] = lambda: mock_transaction_service

    client = TestClient(test_app)
    yield client

    test_app.dependency_overrides.clear()
