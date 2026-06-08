"""
Tests de regresión para endpoints existentes.

Documenta la sección 6 del TRANSACTION_DETAIL_HANDOFF.md:
- GET /health debe seguir respondiendo {"status": "ok"}.
- GET /api/transactions/pending debe seguir listando transacciones pendientes.

Nota: POST /api/transactions/ y GET /api/chain requieren mocks más complejos
(ExternalWalletService, BlockService con DB real) y quedan fuera del alcance
inmediato de este handoff. Se pueden agregar en una iteración futura.
"""


# ---------------------------------------------------------------------------
# GET /health — Healthcheck
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """El endpoint de salud debe seguir funcionando correctamente."""

    def test_health_returns_200(self, test_client):
        """GET /health debe retornar status code 200."""
        response = test_client.get("/health")

        assert response.status_code == 200

    def test_health_body_is_status_ok(self, test_client):
        """GET /health debe retornar {"status": "ok"}."""
        response = test_client.get("/health")

        assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /api/transactions/pending — Listar pendientes
# ---------------------------------------------------------------------------


class TestPendingTransactionsEndpoint:
    """El endpoint de transacciones pendientes no debe romperse."""

    def test_pending_returns_200(self, test_client, mock_transaction_service):
        """GET /api/transactions/pending debe retornar 200."""
        mock_transaction_service.get_pending_transactions = lambda: []

        response = test_client.get("/api/transactions/pending")

        assert response.status_code == 200

    def test_pending_body_structure(self, test_client, mock_transaction_service):
        """Debe retornar {"status": "ok", "data": [...]}."""
        mock_transaction_service.get_pending_transactions = lambda: []

        response = test_client.get("/api/transactions/pending")
        body = response.json()

        assert body["status"] == "ok"
        assert isinstance(body["data"], list)

    def test_pending_returns_transactions(self, test_client, mock_transaction_service):
        """Si hay transacciones pendientes, deben aparecer en data."""
        mock_transaction_service.get_pending_transactions = lambda: [
            {
                "id": "683f1a2b3c4d5e6f7a8b9c0d",
                "from": "sender_address",
                "to": "receiver_address",
                "amount": 10.0,
                "timestamp": "2026-06-03T22:45:00+00:00",
            }
        ]

        response = test_client.get("/api/transactions/pending")
        body = response.json()

        assert len(body["data"]) == 1
        assert body["data"][0]["id"] == "683f1a2b3c4d5e6f7a8b9c0d"


# ---------------------------------------------------------------------------
# Verificación de que el nuevo endpoint no rompe el routing existente
# ---------------------------------------------------------------------------


class TestRoutingNotBroken:
    """El nuevo endpoint /{transaction_id} no debe interferir con /pending."""

    def test_pending_is_not_treated_as_transaction_id(
        self, test_client, mock_transaction_service
    ):
        """
        La ruta /api/transactions/pending NO debe interpretarse como
        /api/transactions/{transaction_id} con transaction_id='pending'.
        Debe seguir retornando la lista de pendientes.
        """
        mock_transaction_service.get_pending_transactions = lambda: []

        response = test_client.get("/api/transactions/pending")
        body = response.json()

        # Si se interpretó como /{transaction_id}, retornaría un 404 o un objeto
        # con 'code': 'TRANSACTION_NOT_FOUND'. Verificamos que NO es eso.
        assert body.get("code") != "TRANSACTION_NOT_FOUND"
        assert body["status"] == "ok"
        assert "data" in body
