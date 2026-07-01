"""
Tests de integración para los endpoints de checkpoints.

  POST /api/chain/checkpoints/generate
  GET  /api/chain/checkpoints

Estrategia:
- Se usa TestClient de FastAPI con dependency_overrides para reemplazar
  get_checkpoint_service por mocks sin necesitar MongoDB activo.
- Misma convención de test_chain_stats_endpoint.py:
  - app local, fixture client, helpers make_mock_service / override_service.
- Se testean los contratos de respuesta, los códigos HTTP y el paso correcto
  de parámetros al servicio.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.checkpoint_router import router as checkpoint_router
from src.api.checkpoint_router import get_checkpoint_service

app = FastAPI(title="UFROCoin Checkpoint Test App")
app.include_router(checkpoint_router, prefix="/api")

# ---------------------------------------------------------------------------
# Datos de prueba
# ---------------------------------------------------------------------------

SAMPLE_CHECKPOINT = {
    "from_block": 0,
    "to_block": 99,
    "merkle_root": "a" * 64,
    "last_block_hash": "b" * 64,
    "created_at": "2026-06-25T06:00:00Z",
    "status": "CREATED",
}

SAMPLE_CHECKPOINT_2 = {
    "from_block": 100,
    "to_block": 199,
    "merkle_root": "c" * 64,
    "last_block_hash": "d" * 64,
    "created_at": "2026-06-25T07:00:00Z",
    "status": "CREATED",
}

GENERATE_RESULT_ONE = {
    "generated": 1,
    "skipped": 0,
    "errors": 0,
    "data": [SAMPLE_CHECKPOINT],
}

GENERATE_RESULT_EMPTY = {
    "generated": 0,
    "skipped": 0,
    "errors": 0,
    "data": [],
}

GENERATE_RESULT_WITH_SKIP = {
    "generated": 1,
    "skipped": 1,
    "errors": 0,
    "data": [SAMPLE_CHECKPOINT_2],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_service(generate_result: dict, list_result: list | None = None) -> MagicMock:
    """Crea un mock de CheckpointService con respuestas configurables."""
    mock = MagicMock()
    mock.generate_checkpoints.return_value = generate_result
    mock.list_checkpoints.return_value = list_result or []
    return mock


def override_service(generate_result: dict, list_result: list | None = None):
    """Retorna un override callable para app.dependency_overrides."""
    mock = make_mock_service(generate_result, list_result)

    def _override():
        return mock

    return _override, mock


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """TestClient con dependency_overrides limpiados después de cada test."""
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests — POST /api/chain/checkpoints/generate
# ---------------------------------------------------------------------------


class TestGenerateCheckpointsEndpoint:
    """Tests para POST /api/chain/checkpoints/generate."""

    def test_returns_200_without_body(self, client):
        """Sin body, el endpoint debe responder 200."""
        override, _ = override_service(GENERATE_RESULT_ONE)
        app.dependency_overrides[get_checkpoint_service] = override

        response = client.post("/api/chain/checkpoints/generate")
        assert response.status_code == 200

    def test_response_has_correct_shape(self, client):
        """La respuesta debe incluir status, generated, skipped, errors y data."""
        override, _ = override_service(GENERATE_RESULT_ONE)
        app.dependency_overrides[get_checkpoint_service] = override

        body = client.post("/api/chain/checkpoints/generate").json()
        assert "status" in body
        assert "generated" in body
        assert "skipped" in body
        assert "errors" in body
        assert "data" in body
        assert body["status"] == "ok"

    def test_generated_count_matches_service_result(self, client):
        """generated debe reflejar el valor retornado por el servicio."""
        override, _ = override_service(GENERATE_RESULT_ONE)
        app.dependency_overrides[get_checkpoint_service] = override

        body = client.post("/api/chain/checkpoints/generate").json()
        assert body["generated"] == 1

    def test_empty_chain_returns_zero_generated(self, client):
        """Con cadena sin rangos completos, generated debe ser 0 y data vacío."""
        override, _ = override_service(GENERATE_RESULT_EMPTY)
        app.dependency_overrides[get_checkpoint_service] = override

        body = client.post("/api/chain/checkpoints/generate").json()
        assert body["generated"] == 0
        assert body["data"] == []

    def test_skipped_field_reflects_service_value(self, client):
        """skipped debe reflejar el valor retornado por el servicio."""
        override, _ = override_service(GENERATE_RESULT_WITH_SKIP)
        app.dependency_overrides[get_checkpoint_service] = override

        body = client.post("/api/chain/checkpoints/generate").json()
        assert body["skipped"] == 1
        assert body["generated"] == 1

    def test_with_frequency_body_passes_frequency_to_service(self, client):
        """Enviar frequency=50 debe pasar ese valor al servicio."""
        override, mock_svc = override_service(GENERATE_RESULT_ONE)
        app.dependency_overrides[get_checkpoint_service] = override

        client.post(
            "/api/chain/checkpoints/generate",
            json={"frequency": 50},
        )
        mock_svc.generate_checkpoints.assert_called_once_with(frequency=50)

    def test_without_body_passes_none_frequency_to_service(self, client):
        """Sin body, frequency debe ser None (usa el valor del ENV)."""
        override, mock_svc = override_service(GENERATE_RESULT_ONE)
        app.dependency_overrides[get_checkpoint_service] = override

        client.post("/api/chain/checkpoints/generate")
        mock_svc.generate_checkpoints.assert_called_once_with(frequency=None)

    def test_checkpoint_data_has_required_fields(self, client):
        """Cada checkpoint en data debe tener los 6 campos del contrato."""
        override, _ = override_service(GENERATE_RESULT_ONE)
        app.dependency_overrides[get_checkpoint_service] = override

        body = client.post("/api/chain/checkpoints/generate").json()
        cp = body["data"][0]
        required = {"from_block", "to_block", "merkle_root", "last_block_hash", "created_at", "status"}
        assert required.issubset(cp.keys())

    def test_checkpoint_status_is_created(self, client):
        """El campo status de cada checkpoint generado debe ser 'CREATED'."""
        override, _ = override_service(GENERATE_RESULT_ONE)
        app.dependency_overrides[get_checkpoint_service] = override

        body = client.post("/api/chain/checkpoints/generate").json()
        assert body["data"][0]["status"] == "CREATED"

    def test_invalid_frequency_returns_422(self, client):
        """frequency=0 es inválido (ge=1) — FastAPI debe retornar 422."""
        override, _ = override_service(GENERATE_RESULT_EMPTY)
        app.dependency_overrides[get_checkpoint_service] = override

        response = client.post(
            "/api/chain/checkpoints/generate",
            json={"frequency": 0},
        )
        assert response.status_code == 422

    def test_negative_frequency_returns_422(self, client):
        """frequency negativa debe retornar 422."""
        override, _ = override_service(GENERATE_RESULT_EMPTY)
        app.dependency_overrides[get_checkpoint_service] = override

        response = client.post(
            "/api/chain/checkpoints/generate",
            json={"frequency": -10},
        )
        assert response.status_code == 422

    def test_no_extra_fields_in_response(self, client):
        """La respuesta no debe incluir campos fuera del contrato."""
        override, _ = override_service(GENERATE_RESULT_ONE)
        app.dependency_overrides[get_checkpoint_service] = override

        body = client.post("/api/chain/checkpoints/generate").json()
        expected_keys = {"status", "generated", "skipped", "errors", "data"}
        assert set(body.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Tests — GET /api/chain/checkpoints
# ---------------------------------------------------------------------------


class TestListCheckpointsEndpoint:
    """Tests para GET /api/chain/checkpoints."""

    def test_returns_200(self, client):
        """El endpoint debe responder 200."""
        override, _ = override_service(
            GENERATE_RESULT_EMPTY,
            list_result=[SAMPLE_CHECKPOINT, SAMPLE_CHECKPOINT_2],
        )
        app.dependency_overrides[get_checkpoint_service] = override

        response = client.get("/api/chain/checkpoints")
        assert response.status_code == 200

    def test_response_has_correct_shape(self, client):
        """La respuesta debe incluir status y data."""
        override, _ = override_service(
            GENERATE_RESULT_EMPTY,
            list_result=[SAMPLE_CHECKPOINT],
        )
        app.dependency_overrides[get_checkpoint_service] = override

        body = client.get("/api/chain/checkpoints").json()
        assert "status" in body
        assert "data" in body
        assert body["status"] == "ok"

    def test_empty_checkpoints_returns_empty_list(self, client):
        """Sin checkpoints persistidos, data debe ser lista vacía."""
        override, _ = override_service(GENERATE_RESULT_EMPTY, list_result=[])
        app.dependency_overrides[get_checkpoint_service] = override

        body = client.get("/api/chain/checkpoints").json()
        assert body["status"] == "ok"
        assert body["data"] == []

    def test_returns_all_checkpoints(self, client):
        """Debe retornar todos los checkpoints disponibles."""
        override, _ = override_service(
            GENERATE_RESULT_EMPTY,
            list_result=[SAMPLE_CHECKPOINT, SAMPLE_CHECKPOINT_2],
        )
        app.dependency_overrides[get_checkpoint_service] = override

        body = client.get("/api/chain/checkpoints").json()
        assert len(body["data"]) == 2

    def test_checkpoints_ordered_by_from_block(self, client):
        """Los checkpoints deben estar en orden ascendente de from_block."""
        override, _ = override_service(
            GENERATE_RESULT_EMPTY,
            list_result=[SAMPLE_CHECKPOINT, SAMPLE_CHECKPOINT_2],
        )
        app.dependency_overrides[get_checkpoint_service] = override

        body = client.get("/api/chain/checkpoints").json()
        from_blocks = [cp["from_block"] for cp in body["data"]]
        assert from_blocks == sorted(from_blocks)

    def test_list_checkpoints_is_called_once(self, client):
        """El router debe invocar list_checkpoints exactamente una vez por petición."""
        override, mock_svc = override_service(
            GENERATE_RESULT_EMPTY, list_result=[]
        )
        app.dependency_overrides[get_checkpoint_service] = override

        client.get("/api/chain/checkpoints")
        mock_svc.list_checkpoints.assert_called_once()

    def test_no_extra_fields_in_response(self, client):
        """La respuesta no debe incluir campos fuera del contrato."""
        override, _ = override_service(GENERATE_RESULT_EMPTY, list_result=[])
        app.dependency_overrides[get_checkpoint_service] = override

        body = client.get("/api/chain/checkpoints").json()
        assert set(body.keys()) == {"status", "data"}

    def test_checkpoint_data_fields_are_correct(self, client):
        """Cada checkpoint en la lista debe incluir los 6 campos del contrato."""
        override, _ = override_service(
            GENERATE_RESULT_EMPTY, list_result=[SAMPLE_CHECKPOINT]
        )
        app.dependency_overrides[get_checkpoint_service] = override

        body = client.get("/api/chain/checkpoints").json()
        cp = body["data"][0]
        required = {"from_block", "to_block", "merkle_root", "last_block_hash", "created_at", "status"}
        assert required.issubset(cp.keys())
