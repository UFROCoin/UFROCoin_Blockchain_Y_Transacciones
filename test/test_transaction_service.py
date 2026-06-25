"""
Tests unitarios para TransactionService.get_transaction_by_id.

Cubren los escenarios documentados en TRANSACTION_DETAIL_HANDOFF.md § 2:
- Transacción encontrada en el mempool (colección transactions).
- Transacción encontrada dentro de un bloque confirmado.
- Transacción no encontrada en ningún lado.
- ID inválido (no es un ObjectId de MongoDB válido).
- Prioridad del mempool sobre los bloques.
"""

from unittest.mock import MagicMock
from bson import ObjectId

from conftest import (
    VALID_OBJECT_ID,
    NONEXISTENT_OBJECT_ID,
    SAMPLE_PENDING_TX_DOC,
    SAMPLE_CONFIRMED_TX_IN_BLOCK,
    SAMPLE_BLOCK,
)


# ---------------------------------------------------------------------------
# get_transaction_by_id — Buscar en mempool
# ---------------------------------------------------------------------------


class TestGetTransactionFromMempool:
    """Transacción encontrada en la colección `transactions` (mempool)."""

    def test_returns_transaction_dict_when_found_in_mempool(
        self, mock_transaction_service, mock_db_client
    ):
        """Debe retornar un dict con los campos mapeados correctamente."""
        mock_db_client["ufrocoin"].transactions.find_one.return_value = (
            SAMPLE_PENDING_TX_DOC.copy()
        )

        result = mock_transaction_service.get_transaction_by_id(VALID_OBJECT_ID)

        assert result is not None
        assert result["id"] == VALID_OBJECT_ID
        assert result["from"] == SAMPLE_PENDING_TX_DOC["from"]
        assert result["to"] == SAMPLE_PENDING_TX_DOC["to"]
        assert result["amount"] == SAMPLE_PENDING_TX_DOC["amount"]
        assert result["type"] == "TRANSFER"
        assert result["status"] == "PENDING"
        assert result["timestamp"] == SAMPLE_PENDING_TX_DOC["timestamp"]
        assert result["block_index"] is None

    def test_mempool_query_uses_object_id(
        self, mock_transaction_service, mock_db_client
    ):
        """Debe buscar en la colección con ObjectId, no con string."""
        mock_db_client["ufrocoin"].transactions.find_one.return_value = None
        mock_db_client["ufrocoin"].blocks.find.return_value = []

        mock_transaction_service.get_transaction_by_id(VALID_OBJECT_ID)

        call_args = mock_db_client["ufrocoin"].transactions.find_one.call_args
        query_filter = call_args[0][0]
        assert isinstance(query_filter["_id"], ObjectId)
        assert str(query_filter["_id"]) == VALID_OBJECT_ID


# ---------------------------------------------------------------------------
# get_transaction_by_id — Buscar en bloques confirmados
# ---------------------------------------------------------------------------


class TestGetTransactionFromConfirmedBlock:
    """Transacción no está en mempool pero sí embebida en un bloque."""

    def test_returns_confirmed_transaction_with_block_index(
        self, mock_transaction_service, mock_db_client
    ):
        """Debe retornar status=CONFIRMED y block_index del bloque contenedor."""
        # No está en mempool
        mock_db_client["ufrocoin"].transactions.find_one.return_value = None
        # Sí está en un bloque
        mock_db_client["ufrocoin"].blocks.find.return_value = [SAMPLE_BLOCK.copy()]

        result = mock_transaction_service.get_transaction_by_id(
            SAMPLE_CONFIRMED_TX_IN_BLOCK["id"]
        )

        assert result is not None
        assert result["id"] == SAMPLE_CONFIRMED_TX_IN_BLOCK["id"]
        assert result["status"] == "CONFIRMED"
        assert result["block_index"] == SAMPLE_BLOCK["index"]
        assert result["amount"] == SAMPLE_CONFIRMED_TX_IN_BLOCK["amount"]

    def test_searches_blocks_after_mempool_miss(
        self, mock_transaction_service, mock_db_client
    ):
        """Debe iterar sobre los bloques si la transacción no está en mempool."""
        mock_db_client["ufrocoin"].transactions.find_one.return_value = None
        mock_db_client["ufrocoin"].blocks.find.return_value = [SAMPLE_BLOCK.copy()]

        mock_transaction_service.get_transaction_by_id(
            SAMPLE_CONFIRMED_TX_IN_BLOCK["id"]
        )

        # Verifica que se consultaron los bloques
        mock_db_client["ufrocoin"].blocks.find.assert_called_once()


# ---------------------------------------------------------------------------
# get_transaction_by_id — Transacción no encontrada
# ---------------------------------------------------------------------------


class TestGetTransactionNotFound:
    """Transacción no existe ni en mempool ni en bloques."""

    def test_returns_none_when_not_found(
        self, mock_transaction_service, mock_db_client
    ):
        """Debe retornar None si la transacción no existe en ningún lado."""
        mock_db_client["ufrocoin"].transactions.find_one.return_value = None
        mock_db_client["ufrocoin"].blocks.find.return_value = []

        result = mock_transaction_service.get_transaction_by_id(NONEXISTENT_OBJECT_ID)

        assert result is None

    def test_returns_none_for_block_without_matching_tx(
        self, mock_transaction_service, mock_db_client
    ):
        """Debe retornar None si hay bloques pero ninguno contiene el ID buscado."""
        mock_db_client["ufrocoin"].transactions.find_one.return_value = None

        block_with_other_tx = {
            "index": 1,
            "transactions": [{"id": "otro_id_diferente", "from": "x", "to": "y", "amount": 10}],
        }
        mock_db_client["ufrocoin"].blocks.find.return_value = [block_with_other_tx]

        result = mock_transaction_service.get_transaction_by_id(NONEXISTENT_OBJECT_ID)

        assert result is None


# ---------------------------------------------------------------------------
# get_transaction_by_id — ID inválido
# ---------------------------------------------------------------------------


class TestGetTransactionInvalidId:
    """ID que no es un ObjectId válido de MongoDB."""

    def test_invalid_id_does_not_raise_exception(
        self, mock_transaction_service, mock_db_client
    ):
        """No debe lanzar excepción con un ID inválido; simplemente busca en bloques."""
        mock_db_client["ufrocoin"].blocks.find.return_value = []

        # No debería lanzar excepción
        result = mock_transaction_service.get_transaction_by_id("esto-no-es-objectid")

        assert result is None

    def test_invalid_id_skips_mempool_query(
        self, mock_transaction_service, mock_db_client
    ):
        """Con un ID inválido no debe intentar consultar mempool con ObjectId."""
        mock_db_client["ufrocoin"].blocks.find.return_value = []

        mock_transaction_service.get_transaction_by_id("not-valid!")

        # find_one NO debe haberse llamado porque el ObjectId fue inválido
        mock_db_client["ufrocoin"].transactions.find_one.assert_not_called()

    def test_invalid_id_still_searches_blocks(
        self, mock_transaction_service, mock_db_client
    ):
        """Con ID inválido debe buscar igualmente en bloques por coincidencia de string."""
        mock_db_client["ufrocoin"].blocks.find.return_value = []

        mock_transaction_service.get_transaction_by_id("invalid-but-search-blocks")

        mock_db_client["ufrocoin"].blocks.find.assert_called_once()


# ---------------------------------------------------------------------------
# get_transaction_by_id — Prioridad del mempool
# ---------------------------------------------------------------------------


class TestMempoolPriority:
    """Si la transacción existe en mempool, no debe buscar en bloques."""

    def test_mempool_result_takes_priority(
        self, mock_transaction_service, mock_db_client
    ):
        """Si la transacción se encuentra en mempool, retorna esa sin buscar en bloques."""
        mock_db_client["ufrocoin"].transactions.find_one.return_value = (
            SAMPLE_PENDING_TX_DOC.copy()
        )

        result = mock_transaction_service.get_transaction_by_id(VALID_OBJECT_ID)

        assert result is not None
        assert result["status"] == "PENDING"
        # No se deben haber consultado los bloques
        mock_db_client["ufrocoin"].blocks.find.assert_not_called()


class TestCalculateBalance:
    """Cálculo de saldo usando transacciones confirmadas y pendientes."""

    def test_counts_genesis_address_fields(self, mock_transaction_service, mock_db_client):
        """Debe considerar transacciones históricas con from_address/to_address."""
        mock_db_client["ufrocoin"].blocks.find.return_value = [
            {
                "transactions": [
                    {
                        "from_address": "SYSTEM",
                        "to_address": "REWARD_POOL",
                        "amount": 1000000.0,
                    }
                ]
            }
        ]
        mock_db_client["ufrocoin"].transactions.find.return_value = []

        result = mock_transaction_service.calculate_balance("REWARD_POOL")

        assert result == 1000000.0

    def test_counts_offchain_genesis_credit(self, mock_transaction_service, mock_db_client):
        """Un crédito wallet.credit.issued (CONFIRMED, block_index None) suma al saldo."""
        wallet = "a1b2c3d4e5f678901234567890abcdef12345678"
        mock_db_client["ufrocoin"].blocks.find.return_value = []
        # find() se llama 1) para créditos off-chain, 2) para pendientes.
        mock_db_client["ufrocoin"].transactions.find.side_effect = [
            [{"to": wallet, "amount": 100.0, "status": "CONFIRMED", "block_index": None}],
            [],
        ]

        result = mock_transaction_service.calculate_balance(wallet)

        assert result == 100.0

    def test_offchain_credit_minus_pending_transfer(
        self, mock_transaction_service, mock_db_client
    ):
        """El crédito off-chain suma y la transferencia pendiente resta."""
        wallet = "a1b2c3d4e5f678901234567890abcdef12345678"
        mock_db_client["ufrocoin"].blocks.find.return_value = []
        mock_db_client["ufrocoin"].transactions.find.side_effect = [
            [{"to": wallet, "amount": 100.0, "status": "CONFIRMED", "block_index": None}],
            [{"from": wallet, "amount": 30.0, "status": "PENDING"}],
        ]

        result = mock_transaction_service.calculate_balance(wallet)

        assert result == 70.0
