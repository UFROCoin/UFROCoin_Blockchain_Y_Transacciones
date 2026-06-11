"""
Tests para GET /api/chain (US-10).

Estrategia:
- Se usa TestClient de FastAPI para pruebas de integración del endpoint.
- BlockService se mockea mediante app.dependency_overrides para aislar la
  lógica del router de MongoDB sin necesitar la base de datos activa.
- No se requiere token (endpoint público).
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.block_router import router as block_router
from src.api.block_router import get_block_service

app = FastAPI(title="UFROCoin Chain Test App")
app.include_router(block_router, prefix="/api")

# ---------------------------------------------------------------------------
# Bloques de prueba
# ---------------------------------------------------------------------------

GENESIS_BLOCK = {
    "index": 0,
    "timestamp": "2026-04-09T12:00:00Z",
    "transactions": [
        {
            "id": "genesis-001",
            "type": "GENESIS",
            "from": "SYSTEM",
            "to": "REWARD_POOL",
            "amount": 1_000_000.0,
            "timestamp": "2026-04-09T12:00:00Z",
            "status": "CONFIRMED",
            "block_index": 0,
        }
    ],
    "previous_hash": "0" * 64,
    "nonce": 0,
    "hash": "a" * 64,
}

BLOCK_1 = {
    "index": 1,
    "timestamp": "2026-04-10T10:00:00Z",
    "transactions": [
        {
            "id": "tx-001",
            "type": "TRANSFER",
            "from": "abc123" + "0" * 58,
            "to": "def456" + "0" * 58,
            "amount": 25.0,
            "timestamp": "2026-04-10T09:59:00Z",
            "status": "CONFIRMED",
            "block_index": 1,
        }
    ],
    "previous_hash": "a" * 64,
    "nonce": 48271,
    "hash": "b" * 64,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_service(blocks: list[dict], total: int) -> MagicMock:
    """Crea un mock de BlockService que retorna los bloques indicados."""
    mock = MagicMock()
    mock.get_chain.return_value = (blocks, total)
    return mock


def override_service(blocks: list[dict], total: int):
    """Retorna un override callable para app.dependency_overrides."""
    mock = make_mock_service(blocks, total)

    def _override():
        return mock

    return _override, mock


# ---------------------------------------------------------------------------
# Fixture de cliente con overrides limpios
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """TestClient con dependency_overrides limpiados después de cada test."""
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetChainEndpoint:
    """Tests para GET /api/chain."""

    def test_returns_200_without_auth_token(self, client):
        """El endpoint es público — debe responder 200 sin Authorization header."""
        override, _ = override_service([GENESIS_BLOCK], 1)
        app.dependency_overrides[get_block_service] = override

        response = client.get("/api/chain")
        assert response.status_code == 200

    def test_response_has_correct_shape(self, client):
        """La respuesta debe incluir success, message, data y error."""
        override, _ = override_service([GENESIS_BLOCK], 1)
        app.dependency_overrides[get_block_service] = override

        body = client.get("/api/chain").json()
        assert "success" in body
        assert "message" in body
        assert "data" in body
        assert "error" in body
        assert body["success"] is True
        assert body["error"] is None

    def test_blocks_are_in_chronological_order(self, client):
        """Los bloques deben venir ordenados por index ascendente."""
        override, _ = override_service([GENESIS_BLOCK, BLOCK_1], 2)
        app.dependency_overrides[get_block_service] = override

        body = client.get("/api/chain").json()
        indices = [b["index"] for b in body["data"]]
        assert indices == sorted(indices), "Los bloques no están en orden cronológico"

    def test_default_pagination_params(self, client):
        """Sin query params, el servicio debe recibir page=1, limit=10."""
        override, mock_svc = override_service([GENESIS_BLOCK], 1)
        app.dependency_overrides[get_block_service] = override

        client.get("/api/chain")
        mock_svc.get_chain.assert_called_once_with(page=1, limit=10)

    def test_custom_pagination_params(self, client):
        """Con ?page=2&limit=5, el servicio debe recibir esos valores."""
        override, mock_svc = override_service([], 0)
        app.dependency_overrides[get_block_service] = override

        client.get("/api/chain?page=2&limit=5")
        mock_svc.get_chain.assert_called_once_with(page=2, limit=5)

    def test_empty_blockchain_returns_empty_data(self, client):
        """Si no hay bloques, data debe ser lista vacía y success=True."""
        override, _ = override_service([], 0)
        app.dependency_overrides[get_block_service] = override

        body = client.get("/api/chain").json()
        assert body["success"] is True
        assert body["data"] == []

    def test_block_data_fields_present(self, client):
        """Cada bloque debe incluir index, timestamp, hash, previous_hash, nonce y transactions."""
        override, _ = override_service([GENESIS_BLOCK], 1)
        app.dependency_overrides[get_block_service] = override

        body = client.get("/api/chain").json()
        block = body["data"][0]
        required_fields = {"index", "timestamp", "hash", "previous_hash", "nonce", "transactions"}
        assert required_fields.issubset(block.keys()), (
            f"Faltan campos en el bloque: {required_fields - block.keys()}"
        )

    def test_invalid_page_zero_returns_422(self, client):
        """page=0 es inválido (ge=1) — FastAPI debe retornar 422."""
        override, _ = override_service([], 0)
        app.dependency_overrides[get_block_service] = override

        response = client.get("/api/chain?page=0")
        assert response.status_code == 422

    def test_invalid_limit_zero_returns_422(self, client):
        """limit=0 es inválido (ge=1) — FastAPI debe retornar 422."""
        override, _ = override_service([], 0)
        app.dependency_overrides[get_block_service] = override

        response = client.get("/api/chain?limit=0")
        assert response.status_code == 422

    def test_out_of_range_page_returns_empty_data(self, client):
        """Una página fuera de rango debe retornar data vacío (no error)."""
        override, _ = override_service([], 3)
        app.dependency_overrides[get_block_service] = override

        body = client.get("/api/chain?page=999&limit=10").json()
        assert body["success"] is True
        assert body["data"] == []
