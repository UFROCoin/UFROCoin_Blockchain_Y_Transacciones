"""
Tests unitarios para src.services.genesis_service.GenesisService.

Estrategia:
- Se mockean BlockService, la colección chain_metadata y publish_event para
  evitar dependencia de MongoDB y RabbitMQ.
- Se verifica la lógica de control de flujo (idempotencia del génesis,
  sincronización de metadata, manejo de errores de publicación).
- Se testean build_genesis_transaction y build_genesis_block de forma aislada
  verificando sus valores criptográficos.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.constants import (
    GENESIS_BLOCK_INDEX,
    GENESIS_PREVIOUS_HASH,
    GENESIS_TRANSACTION_TYPE,
    REWARD_POOL,
    SYSTEM_ADDRESS,
    SYSTEM_REWARD,
)
from src.utils.hash_utils import calculate_concatenated_block_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_genesis_service(
    metadata_doc=None,
    last_block=None,
    insert_raises=None,
) -> "GenesisService":  # noqa: F821
    """
    Construye un GenesisService con todas las dependencias externas mockeadas.

    Parámetros:
        metadata_doc: documento retornado por chain_metadata.find_one.
        last_block: documento retornado por BlockService.get_last_block.
        insert_raises: excepción que lanza BlockService.create_genesis_block.
    """
    with (
        patch("src.services.genesis_service.get_chain_metadata_collection") as mock_meta_col,
        patch("src.services.genesis_service.BlockService") as MockBlockService,
        patch("src.services.genesis_service.publish_event"),
    ):
        # Configurar chain_metadata mock
        meta_collection = MagicMock()
        meta_collection.find_one.return_value = metadata_doc
        mock_meta_col.return_value = meta_collection

        # Configurar BlockService mock
        mock_bs_instance = MagicMock()
        mock_bs_instance.get_last_block.return_value = last_block
        mock_bs_instance.blocks_collection.count_documents.return_value = 1

        if insert_raises:
            mock_bs_instance.create_genesis_block.side_effect = insert_raises
        else:
            # save devuelve un documento simulado con hash
            mock_bs_instance.create_genesis_block.side_effect = lambda block: None

        MockBlockService.return_value = mock_bs_instance

        from src.services.genesis_service import GenesisService

        service = GenesisService()
        # Inyectar los mocks en el servicio para que los tests puedan inspeccionarlos
        service._mock_meta_collection = meta_collection
        service._mock_block_service = mock_bs_instance
        return service


# ---------------------------------------------------------------------------
# Tests: create_genesis_if_needed — control de flujo
# ---------------------------------------------------------------------------


class TestCreateGenesisIfNeeded:
    """GenesisService.create_genesis_if_needed — lógica de idempotencia."""

    def test_returns_none_when_genesis_already_created(self):
        """Si metadata indica genesis_created=True, no crea nada y retorna None."""
        with (
            patch("src.services.genesis_service.get_chain_metadata_collection") as mock_meta,
            patch("src.services.genesis_service.BlockService") as MockBS,
            patch("src.services.genesis_service.publish_event"),
        ):
            mock_meta.return_value.find_one.return_value = {"genesis_created": True}
            from src.services.genesis_service import GenesisService

            service = GenesisService()
            result = service.create_genesis_if_needed()

            assert result is None
            MockBS.return_value.create_genesis_block.assert_not_called()

    def test_returns_none_when_chain_already_has_blocks(self):
        """Si ya existe un bloque en la cadena, sincroniza metadata y retorna None."""
        existing_block = {
            "index": 5,
            "hash": "e" * 64,
            "timestamp": "2026-04-09T12:00:00Z",
        }
        with (
            patch("src.services.genesis_service.get_chain_metadata_collection") as mock_meta,
            patch("src.services.genesis_service.BlockService") as MockBS,
            patch("src.services.genesis_service.publish_event"),
        ):
            mock_meta.return_value.find_one.return_value = None  # sin metadata
            mock_bs = MagicMock()
            mock_bs.get_last_block.return_value = existing_block
            mock_bs.blocks_collection.count_documents.return_value = 6
            MockBS.return_value = mock_bs

            from src.services.genesis_service import GenesisService

            service = GenesisService()
            result = service.create_genesis_if_needed()

            assert result is None
            mock_bs.create_genesis_block.assert_not_called()

    def test_creates_genesis_block_when_chain_is_empty(self):
        """Si no hay metadata ni bloques, debe crear el bloque génesis."""
        captured_block = {}

        def fake_create(block):
            captured_block["block"] = block

        with (
            patch("src.services.genesis_service.get_chain_metadata_collection") as mock_meta,
            patch("src.services.genesis_service.BlockService") as MockBS,
            patch("src.services.genesis_service.publish_event"),
        ):
            mock_meta.return_value.find_one.return_value = None
            mock_bs = MagicMock()
            mock_bs.get_last_block.return_value = None
            mock_bs.create_genesis_block.side_effect = fake_create
            MockBS.return_value = mock_bs

            from src.services.genesis_service import GenesisService

            service = GenesisService()
            result = service.create_genesis_if_needed()

            # Debe haber llamado create_genesis_block
            assert mock_bs.create_genesis_block.called

    def test_handles_duplicate_key_error_gracefully(self):
        """Si create_genesis_block lanza DuplicateKeyError, retorna None sin relanzar."""
        try:
            from pymongo.errors import DuplicateKeyError
            dup_error = DuplicateKeyError("duplicate", code=11000)
        except ImportError:
            pytest.skip("pymongo no disponible")

        with (
            patch("src.services.genesis_service.get_chain_metadata_collection") as mock_meta,
            patch("src.services.genesis_service.BlockService") as MockBS,
            patch("src.services.genesis_service.publish_event"),
        ):
            mock_meta.return_value.find_one.return_value = None
            mock_bs = MagicMock()
            mock_bs.get_last_block.return_value = None
            mock_bs.create_genesis_block.side_effect = dup_error
            MockBS.return_value = mock_bs

            from src.services.genesis_service import GenesisService

            service = GenesisService()
            # No debe lanzar excepción
            result = service.create_genesis_if_needed()
            assert result is None

    def test_rabbitmq_failure_does_not_propagate(self):
        """Si publish_event falla, el error se silencia y el método retorna igualmente."""
        with (
            patch("src.services.genesis_service.get_chain_metadata_collection") as mock_meta,
            patch("src.services.genesis_service.BlockService") as MockBS,
            patch("src.services.genesis_service.publish_event", side_effect=RuntimeError("RabbitMQ down")),
        ):
            mock_meta.return_value.find_one.return_value = None
            mock_bs = MagicMock()
            mock_bs.get_last_block.return_value = None
            MockBS.return_value = mock_bs

            from src.services.genesis_service import GenesisService

            service = GenesisService()
            # No debe propagar la excepción de RabbitMQ
            try:
                service.create_genesis_if_needed()
            except RuntimeError:
                pytest.fail("publish_event failure was not silenced")

    def test_metadata_is_updated_after_genesis_creation(self):
        """Después de crear el génesis, se llama update_one en chain_metadata."""
        with (
            patch("src.services.genesis_service.get_chain_metadata_collection") as mock_meta,
            patch("src.services.genesis_service.BlockService") as MockBS,
            patch("src.services.genesis_service.publish_event"),
        ):
            mock_meta.return_value.find_one.return_value = None
            mock_bs = MagicMock()
            mock_bs.get_last_block.return_value = None
            MockBS.return_value = mock_bs

            from src.services.genesis_service import GenesisService

            service = GenesisService()
            service.create_genesis_if_needed()

            mock_meta.return_value.update_one.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: build_genesis_transaction
# ---------------------------------------------------------------------------


class TestBuildGenesisTransaction:
    """GenesisService.build_genesis_transaction — estructura de la transacción inicial."""

    def _get_service(self):
        with (
            patch("src.services.genesis_service.get_chain_metadata_collection"),
            patch("src.services.genesis_service.BlockService"),
        ):
            from src.services.genesis_service import GenesisService
            return GenesisService()

    def test_type_is_genesis_issuance(self):
        """El tipo debe ser GENESIS_ISSUANCE."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        assert tx["type"] == GENESIS_TRANSACTION_TYPE

    def test_from_address_is_system(self):
        """La dirección de origen debe ser SYSTEM."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        assert tx["from_address"] == SYSTEM_ADDRESS

    def test_to_address_is_reward_pool(self):
        """La dirección de destino debe ser REWARD_POOL."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        assert tx["to_address"] == REWARD_POOL

    def test_amount_is_system_reward(self):
        """El monto debe ser el SYSTEM_REWARD (1_000_000)."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        assert tx["amount"] == SYSTEM_REWARD

    def test_has_tx_id(self):
        """La transacción debe incluir un tx_id generado dinámicamente."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        assert "tx_id" in tx
        assert tx["tx_id"].startswith("genesis-")

    def test_tx_id_is_unique(self):
        """Cada llamada genera un tx_id único."""
        service = self._get_service()
        tx1 = service.build_genesis_transaction()
        tx2 = service.build_genesis_transaction()
        assert tx1["tx_id"] != tx2["tx_id"]

    def test_has_timestamp(self):
        """La transacción debe incluir un timestamp ISO 8601 terminando en Z."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        assert "timestamp" in tx
        assert tx["timestamp"].endswith("Z")

    def test_metadata_has_reason(self):
        """El campo metadata debe contener la razón initial_system_issuance."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        assert tx.get("metadata", {}).get("reason") == "initial_system_issuance"


# ---------------------------------------------------------------------------
# Tests: build_genesis_block
# ---------------------------------------------------------------------------


class TestBuildGenesisBlock:
    """GenesisService.build_genesis_block — construcción criptográfica del bloque génesis."""

    def _get_service(self):
        with (
            patch("src.services.genesis_service.get_chain_metadata_collection"),
            patch("src.services.genesis_service.BlockService"),
        ):
            from src.services.genesis_service import GenesisService
            return GenesisService()

    def test_index_is_genesis_block_index(self):
        """El índice del bloque génesis debe ser GENESIS_BLOCK_INDEX (0)."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        block = service.build_genesis_block(tx)
        assert block.index == GENESIS_BLOCK_INDEX

    def test_previous_hash_is_genesis_previous_hash(self):
        """El previous_hash del génesis debe ser 64 ceros."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        block = service.build_genesis_block(tx)
        assert block.previous_hash == GENESIS_PREVIOUS_HASH

    def test_hash_is_not_none(self):
        """El bloque génesis debe tener un hash calculado (no None)."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        block = service.build_genesis_block(tx)
        assert block.hash is not None

    def test_hash_matches_concatenated_hash(self):
        """El hash del bloque debe coincidir con calculate_concatenated_block_hash."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        block = service.build_genesis_block(tx)

        expected_hash = calculate_concatenated_block_hash(block.model_dump(exclude_none=True))
        assert block.hash == expected_hash

    def test_hash_is_64_hex_chars(self):
        """El hash debe ser una cadena hexadecimal de exactamente 64 caracteres."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        block = service.build_genesis_block(tx)

        assert len(block.hash) == 64
        assert all(c in "0123456789abcdef" for c in block.hash)

    def test_nonce_is_zero(self):
        """El nonce del bloque génesis debe ser 0."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        block = service.build_genesis_block(tx)
        assert block.nonce == 0

    def test_contains_genesis_transaction(self):
        """El bloque génesis debe contener exactamente una transacción (la génesis)."""
        service = self._get_service()
        tx = service.build_genesis_transaction()
        block = service.build_genesis_block(tx)
        assert len(block.transactions) == 1
        assert block.transactions[0] == tx
