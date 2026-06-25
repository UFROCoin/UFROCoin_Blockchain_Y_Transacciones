from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.core import database


@pytest.fixture(autouse=True)
def reset_database_state(monkeypatch):
    for name in (
        "MONGODB_URI",
        "MONGO_DB_NAME",
        "MONGODB_DB_NAME",
        "MONGO_INITDB_ROOT_USERNAME",
        "MONGO_INITDB_ROOT_PASSWORD",
        "MONGO_HOST",
        "MONGO_PORT",
        "MONGO_BLOCKS_COLLECTION",
        "MONGO_TRANSACTIONS_COLLECTION",
        "MONGO_CHAIN_METADATA_COLLECTION",
    ):
        monkeypatch.delenv(name, raising=False)

    database._mongo_client = None
    database._database = None
    database.get_database_name.cache_clear()
    yield
    database._mongo_client = None
    database._database = None
    database.get_database_name.cache_clear()


def test_get_database_name_prefers_mongo_db_name(monkeypatch):
    monkeypatch.setenv("MONGO_DB_NAME", "primary_db")
    monkeypatch.setenv("MONGODB_DB_NAME", "secondary_db")

    assert database.get_database_name() == "primary_db"


def test_get_database_name_uses_compatibility_env(monkeypatch):
    monkeypatch.setenv("MONGODB_DB_NAME", "compat_db")

    assert database.get_database_name() == "compat_db"


def test_get_database_name_uses_default_when_env_is_missing():
    assert database.get_database_name() == database.DEFAULT_DATABASE_NAME


def test_build_mongodb_uri_uses_direct_uri(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://mongo.example/ufrocoin")

    assert database._build_mongodb_uri() == "mongodb://mongo.example/ufrocoin"


def test_build_mongodb_uri_with_credentials(monkeypatch):
    monkeypatch.setenv("MONGO_INITDB_ROOT_USERNAME", "root")
    monkeypatch.setenv("MONGO_INITDB_ROOT_PASSWORD", "secret")
    monkeypatch.setenv("MONGO_HOST", "mongo")
    monkeypatch.setenv("MONGO_PORT", "27018")
    monkeypatch.setenv("MONGO_DB_NAME", "ufro_test")

    assert (
        database._build_mongodb_uri()
        == "mongodb://root:secret@mongo:27018/ufro_test?authSource=admin"
    )


def test_build_mongodb_uri_without_credentials_uses_host_port_and_database(monkeypatch):
    monkeypatch.setenv("MONGO_HOST", "mongo")
    monkeypatch.setenv("MONGO_PORT", "27018")
    monkeypatch.setenv("MONGO_DB_NAME", "ufro_test")

    assert database._build_mongodb_uri() == "mongodb://mongo:27018/ufro_test"


def test_get_pymongo_module_raises_clear_error_when_missing(monkeypatch):
    def raise_import_error(_name):
        raise ImportError("missing")

    monkeypatch.setattr(database, "import_module", raise_import_error)

    with pytest.raises(RuntimeError, match="pymongo is required"):
        database._get_pymongo_module()


def test_get_mongo_client_reuses_single_client(monkeypatch):
    created_clients = []

    class FakeMongoClient:
        def __init__(self, uri):
            self.uri = uri
            created_clients.append(self)

    monkeypatch.setenv("MONGODB_URI", "mongodb://example")
    monkeypatch.setattr(
        database,
        "_get_pymongo_module",
        lambda: SimpleNamespace(MongoClient=FakeMongoClient),
    )

    first = database.get_mongo_client()
    second = database.get_mongo_client()

    assert first is second
    assert len(created_clients) == 1
    assert first.uri == "mongodb://example"


def test_get_database_uses_configured_database_name(monkeypatch):
    client = MagicMock()
    selected_db = MagicMock()
    client.__getitem__.return_value = selected_db
    database._mongo_client = client
    monkeypatch.setenv("MONGO_DB_NAME", "configured_db")

    result = database.get_database()

    assert result is selected_db
    client.__getitem__.assert_called_once_with("configured_db")


def test_collection_name_helpers_use_env_overrides(monkeypatch):
    monkeypatch.setenv("MONGO_BLOCKS_COLLECTION", "custom_blocks")
    monkeypatch.setenv("MONGO_TRANSACTIONS_COLLECTION", "custom_transactions")
    monkeypatch.setenv("MONGO_CHAIN_METADATA_COLLECTION", "custom_metadata")

    assert database.get_blocks_collection_name() == "custom_blocks"
    assert database.get_transactions_collection_name() == "custom_transactions"
    assert database.get_chain_metadata_collection_name() == "custom_metadata"


def test_initialize_database_pings_and_creates_required_indexes(monkeypatch):
    fake_pymongo = SimpleNamespace(ASCENDING=1, DESCENDING=-1)
    blocks = MagicMock()
    transactions = MagicMock()
    client = MagicMock()
    client.admin.command = MagicMock()

    monkeypatch.setattr(database, "_get_pymongo_module", lambda: fake_pymongo)
    monkeypatch.setattr(database, "get_mongo_client", lambda: client)
    monkeypatch.setattr(database, "get_blocks_collection", lambda: blocks)
    monkeypatch.setattr(database, "get_transactions_collection", lambda: transactions)

    database.initialize_database()

    client.admin.command.assert_called_once_with("ping")
    blocks.create_index.assert_any_call(
        [("index", fake_pymongo.ASCENDING)], unique=True, name="blocks_index_unique"
    )
    blocks.create_index.assert_any_call(
        [("hash", fake_pymongo.ASCENDING)], unique=True, name="blocks_hash_unique"
    )
    blocks.create_index.assert_any_call(
        [("index", fake_pymongo.DESCENDING)], name="blocks_index_desc"
    )
    transactions.create_index.assert_any_call(
        [("status", fake_pymongo.ASCENDING)], name="transactions_status"
    )
    transactions.create_index.assert_any_call(
        [("from", fake_pymongo.ASCENDING), ("status", fake_pymongo.ASCENDING)],
        name="transactions_from_status",
    )
    transactions.create_index.assert_any_call(
        [("to", fake_pymongo.ASCENDING)], name="transactions_to"
    )
    transactions.create_index.assert_any_call(
        [("timestamp", fake_pymongo.DESCENDING)], name="transactions_timestamp_desc"
    )


def test_close_database_closes_client_and_clears_state():
    client = MagicMock()
    database._mongo_client = client
    database._database = MagicMock()
    database.get_database_name()

    database.close_database()

    client.close.assert_called_once()
    assert database._mongo_client is None
    assert database._database is None
