"""
Tests para GET /api/chain/stats.

Estrategia:
- Se usa TestClient de FastAPI para pruebas de integración del endpoint.
- BlockService se mockea mediante app.dependency_overrides para aislar la
  lógica del router de MongoDB sin necesitar la base de datos activa.
- No se requiere token (endpoint público).
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.api.block_router import get_block_service

# ---------------------------------------------------------------------------
# Datos de estadísticas de prueba
# ---------------------------------------------------------------------------

STATS_FULL = {
    "total_blocks": 3,
    "last_block_time": "2026-04-10T10:00:00Z",
    "total_transactions": 4,
    "total_ufrocoins_emitidos": 1_000_025.0,
}

STATS_EMPTY = {
    "total_blocks": 0,
    "last_block_time": None,
    "total_transactions": 0,
    "total_ufrocoins_emitidos": 0.0,
}

STATS_SINGLE_BLOCK = {
    "total_blocks": 1,
    "last_block_time": "2026-04-09T12:00:00Z",
    "total_transactions": 1,
    "total_ufrocoins_emitidos": 1_000_000.0,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_service(stats: dict) -> MagicMock:
    """Crea un mock de BlockService que retorna las estadísticas indicadas."""
    mock = MagicMock()
    mock.get_chain_stats.return_value = stats
    return mock


def override_service(stats: dict):
    """Retorna un override callable para app.dependency_overrides."""
    mock = make_mock_service(stats)

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


class TestGetChainStatsEndpoint:
    """Tests para GET /api/chain/stats."""

    def test_returns_200_without_auth_token(self, client):
        """El endpoint es público — debe responder 200 sin Authorization header."""
        override, _ = override_service(STATS_FULL)
        app.dependency_overrides[get_block_service] = override

        response = client.get("/api/chain/stats")
        assert response.status_code == 200

    def test_response_has_correct_shape(self, client):
        """La respuesta debe incluir status y data en el nivel raíz."""
        override, _ = override_service(STATS_FULL)
        app.dependency_overrides[get_block_service] = override

        body = client.get("/api/chain/stats").json()
        assert "status" in body
        assert "data" in body
        assert body["status"] == "ok"

    def test_data_has_all_required_fields(self, client):
        """data debe incluir los cuatro campos del contrato."""
        override, _ = override_service(STATS_FULL)
        app.dependency_overrides[get_block_service] = override

        data = client.get("/api/chain/stats").json()["data"]
        required_fields = {
            "total_blocks",
            "last_block_time",
            "total_transactions",
            "total_ufrocoins_emitidos",
        }
        assert required_fields.issubset(data.keys()), (
            f"Faltan campos en data: {required_fields - data.keys()}"
        )

    def test_total_blocks_matches_service_value(self, client):
        """total_blocks debe reflejar exactamente el valor devuelto por el servicio."""
        override, _ = override_service(STATS_FULL)
        app.dependency_overrides[get_block_service] = override

        data = client.get("/api/chain/stats").json()["data"]
        assert data["total_blocks"] == STATS_FULL["total_blocks"]

    def test_last_block_time_matches_service_value(self, client):
        """last_block_time debe reflejar exactamente el timestamp del último bloque."""
        override, _ = override_service(STATS_FULL)
        app.dependency_overrides[get_block_service] = override

        data = client.get("/api/chain/stats").json()["data"]
        assert data["last_block_time"] == STATS_FULL["last_block_time"]

    def test_total_transactions_matches_service_value(self, client):
        """total_transactions debe reflejar la suma acumulada del servicio."""
        override, _ = override_service(STATS_FULL)
        app.dependency_overrides[get_block_service] = override

        data = client.get("/api/chain/stats").json()["data"]
        assert data["total_transactions"] == STATS_FULL["total_transactions"]

    def test_total_ufrocoins_emitidos_matches_service_value(self, client):
        """total_ufrocoins_emitidos debe reflejar la suma acumulada del servicio."""
        override, _ = override_service(STATS_FULL)
        app.dependency_overrides[get_block_service] = override

        data = client.get("/api/chain/stats").json()["data"]
        assert data["total_ufrocoins_emitidos"] == STATS_FULL["total_ufrocoins_emitidos"]

    def test_empty_chain_returns_zeros_and_null_time(self, client):
        """Con cadena vacía, los contadores deben ser 0 y last_block_time debe ser null."""
        override, _ = override_service(STATS_EMPTY)
        app.dependency_overrides[get_block_service] = override

        data = client.get("/api/chain/stats").json()["data"]
        assert data["total_blocks"] == 0
        assert data["last_block_time"] is None
        assert data["total_transactions"] == 0
        assert data["total_ufrocoins_emitidos"] == 0.0

    def test_single_block_chain_returns_correct_stats(self, client):
        """Con un solo bloque (génesis), los valores deben coincidir con ese bloque."""
        override, _ = override_service(STATS_SINGLE_BLOCK)
        app.dependency_overrides[get_block_service] = override

        data = client.get("/api/chain/stats").json()["data"]
        assert data["total_blocks"] == 1
        assert data["last_block_time"] == "2026-04-09T12:00:00Z"
        assert data["total_transactions"] == 1
        assert data["total_ufrocoins_emitidos"] == 1_000_000.0

    def test_get_chain_stats_is_called_once(self, client):
        """El router debe invocar get_chain_stats exactamente una vez por petición."""
        override, mock_svc = override_service(STATS_FULL)
        app.dependency_overrides[get_block_service] = override

        client.get("/api/chain/stats")
        mock_svc.get_chain_stats.assert_called_once()

    def test_status_is_ok_string(self, client):
        """El campo status debe ser exactamente la cadena 'ok', no True ni ningún otro valor."""
        override, _ = override_service(STATS_FULL)
        app.dependency_overrides[get_block_service] = override

        body = client.get("/api/chain/stats").json()
        assert body["status"] == "ok"
        assert isinstance(body["status"], str)

    def test_no_extra_fields_in_response(self, client):
        """La respuesta no debe incluir campos fuera del contrato (status, data)."""
        override, _ = override_service(STATS_FULL)
        app.dependency_overrides[get_block_service] = override

        body = client.get("/api/chain/stats").json()
        assert set(body.keys()) == {"status", "data"}

    def test_no_extra_fields_in_data(self, client):
        """data no debe incluir campos fuera del contrato de ChainStatsData."""
        override, _ = override_service(STATS_FULL)
        app.dependency_overrides[get_block_service] = override

        data = client.get("/api/chain/stats").json()["data"]
        expected_fields = {
            "total_blocks",
            "last_block_time",
            "total_transactions",
            "total_ufrocoins_emitidos",
        }
        assert set(data.keys()) == expected_fields
