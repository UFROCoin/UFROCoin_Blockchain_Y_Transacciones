"""
Tests de integración para GET /api/chain/validate/fast.

Estrategia:
- Se usa TestClient de FastAPI con dependency_overrides para reemplazar
  get_checkpoint_service por mocks, sin requerir MongoDB activo.
- Misma convención que los demás tests de endpoint del proyecto.
- Se verifican los tres escenarios: sin checkpoints, íntegra, corrupta.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.checkpoint_router import router as checkpoint_router
from src.api.checkpoint_router import get_checkpoint_service

app = FastAPI(title="UFROCoin Fast Validation Test App")
app.include_router(checkpoint_router, prefix="/api")

# ---------------------------------------------------------------------------
# Datos de resultado de ejemplo
# ---------------------------------------------------------------------------

RESULT_VALID = {
    "valid": True,
    "message": "Blockchain integrity verified using checkpoints and hash tree",
    "reason": None,
    "corrupted_range": None,
    "first_corrupted_block": None,
    "expected_root": None,
    "actual_root": None,
}

RESULT_NO_CHECKPOINTS = {
    "valid": False,
    "message": None,
    "reason": "CHECKPOINTS_NOT_FOUND",
    "corrupted_range": None,
    "first_corrupted_block": None,
    "expected_root": None,
    "actual_root": None,
}

RESULT_CORRUPTED = {
    "valid": False,
    "message": None,
    "reason": "MERKLE_ROOT_MISMATCH",
    "corrupted_range": {"from_block": 301, "to_block": 400},
    "first_corrupted_block": 347,
    "expected_root": "abc123" + "a" * 58,
    "actual_root": "def456" + "b" * 58,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_service(validate_fast_result: dict) -> MagicMock:
    """Crea un mock de CheckpointService con el resultado de validate_fast configurado."""
    mock = MagicMock()
    mock.validate_fast.return_value = validate_fast_result
    return mock


def override_service(validate_fast_result: dict):
    """Retorna un override callable y el mock para app.dependency_overrides."""
    mock = make_mock_service(validate_fast_result)

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
# Tests — GET /api/chain/validate/fast — cadena íntegra
# ---------------------------------------------------------------------------


class TestFastValidationValid:
    """Escenario: todos los Merkle roots coinciden."""

    def test_returns_200(self, client):
        """El endpoint debe responder 200."""
        override, _ = override_service(RESULT_VALID)
        app.dependency_overrides[get_checkpoint_service] = override
        response = client.get("/api/chain/validate/fast")
        assert response.status_code == 200

    def test_valid_true_in_response(self, client):
        """La respuesta debe incluir valid=True."""
        override, _ = override_service(RESULT_VALID)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["valid"] is True

    def test_message_present_when_valid(self, client):
        """La respuesta debe incluir el mensaje de éxito definido en los criterios."""
        override, _ = override_service(RESULT_VALID)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["message"] == "Blockchain integrity verified using checkpoints and hash tree"

    def test_corrupted_range_null_when_valid(self, client):
        """corrupted_range debe ser null cuando la cadena es íntegra."""
        override, _ = override_service(RESULT_VALID)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["corrupted_range"] is None

    def test_first_corrupted_block_null_when_valid(self, client):
        """first_corrupted_block debe ser null cuando la cadena es íntegra."""
        override, _ = override_service(RESULT_VALID)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["first_corrupted_block"] is None

    def test_reason_null_when_valid(self, client):
        """reason debe ser null cuando la cadena es íntegra."""
        override, _ = override_service(RESULT_VALID)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["reason"] is None

    def test_service_called_once(self, client):
        """El router debe invocar validate_fast exactamente una vez."""
        override, mock_svc = override_service(RESULT_VALID)
        app.dependency_overrides[get_checkpoint_service] = override
        client.get("/api/chain/validate/fast")
        mock_svc.validate_fast.assert_called_once()


# ---------------------------------------------------------------------------
# Tests — GET /api/chain/validate/fast — sin checkpoints
# ---------------------------------------------------------------------------


class TestFastValidationNoCheckpoints:
    """Escenario: no existen checkpoints registrados."""

    def test_returns_200(self, client):
        """El endpoint debe responder 200 incluso sin checkpoints."""
        override, _ = override_service(RESULT_NO_CHECKPOINTS)
        app.dependency_overrides[get_checkpoint_service] = override
        response = client.get("/api/chain/validate/fast")
        assert response.status_code == 200

    def test_valid_false_when_no_checkpoints(self, client):
        """Sin checkpoints, valid debe ser False."""
        override, _ = override_service(RESULT_NO_CHECKPOINTS)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["valid"] is False

    def test_reason_is_checkpoints_not_found(self, client):
        """reason debe ser CHECKPOINTS_NOT_FOUND."""
        override, _ = override_service(RESULT_NO_CHECKPOINTS)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["reason"] == "CHECKPOINTS_NOT_FOUND"

    def test_corrupted_range_null_when_no_checkpoints(self, client):
        """corrupted_range debe ser null cuando no hay checkpoints."""
        override, _ = override_service(RESULT_NO_CHECKPOINTS)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["corrupted_range"] is None


# ---------------------------------------------------------------------------
# Tests — GET /api/chain/validate/fast — corrupción detectada
# ---------------------------------------------------------------------------


class TestFastValidationCorrupted:
    """Escenario: se detecta discrepancia de Merkle root."""

    def test_returns_200(self, client):
        """El endpoint debe responder 200 incluso con corrupción detectada."""
        override, _ = override_service(RESULT_CORRUPTED)
        app.dependency_overrides[get_checkpoint_service] = override
        response = client.get("/api/chain/validate/fast")
        assert response.status_code == 200

    def test_valid_false_when_corrupted(self, client):
        """Con corrupción detectada, valid debe ser False."""
        override, _ = override_service(RESULT_CORRUPTED)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["valid"] is False

    def test_reason_is_merkle_root_mismatch(self, client):
        """reason debe ser MERKLE_ROOT_MISMATCH."""
        override, _ = override_service(RESULT_CORRUPTED)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["reason"] == "MERKLE_ROOT_MISMATCH"

    def test_corrupted_range_present(self, client):
        """corrupted_range debe incluir from_block y to_block."""
        override, _ = override_service(RESULT_CORRUPTED)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["corrupted_range"] is not None
        assert body["corrupted_range"]["from_block"] == 301
        assert body["corrupted_range"]["to_block"] == 400

    def test_first_corrupted_block_present(self, client):
        """first_corrupted_block debe contener el índice del bloque alterado."""
        override, _ = override_service(RESULT_CORRUPTED)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["first_corrupted_block"] == 347

    def test_expected_root_present(self, client):
        """expected_root debe ser el Merkle root del checkpoint."""
        override, _ = override_service(RESULT_CORRUPTED)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["expected_root"] == RESULT_CORRUPTED["expected_root"]

    def test_actual_root_present(self, client):
        """actual_root debe ser el Merkle root recalculado."""
        override, _ = override_service(RESULT_CORRUPTED)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        assert body["actual_root"] == RESULT_CORRUPTED["actual_root"]

    def test_all_required_fields_present(self, client):
        """La respuesta debe incluir todos los campos del contrato."""
        override, _ = override_service(RESULT_CORRUPTED)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        required = {
            "valid",
            "message",
            "reason",
            "corrupted_range",
            "first_corrupted_block",
            "expected_root",
            "actual_root",
        }
        assert required.issubset(body.keys())

    def test_no_extra_fields_in_response(self, client):
        """La respuesta no debe incluir campos fuera del contrato."""
        override, _ = override_service(RESULT_CORRUPTED)
        app.dependency_overrides[get_checkpoint_service] = override
        body = client.get("/api/chain/validate/fast").json()
        expected_keys = {
            "valid",
            "message",
            "reason",
            "corrupted_range",
            "first_corrupted_block",
            "expected_root",
            "actual_root",
        }
        assert set(body.keys()) == expected_keys
