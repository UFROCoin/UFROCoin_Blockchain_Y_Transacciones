import os
from importlib import import_module
from typing import Any


DEFAULT_MONGO_URI = "mongodb://localhost:27017/"
DEFAULT_DATABASE_NAME = "ufrocoin"

_mongo_client: Any | None = None
_database: Any | None = None


def _get_pymongo_module():
    try:
        pymongo = import_module("pymongo")
    except ImportError as exc:
        raise RuntimeError("pymongo is required to use MongoDB persistence") from exc
    return pymongo


def get_mongo_client() -> Any:
    global _mongo_client
    if _mongo_client is None:
        pymongo = _get_pymongo_module()
        mongo_uri = os.getenv("MONGODB_URI", DEFAULT_MONGO_URI)
        _mongo_client = pymongo.MongoClient(mongo_uri)
    return _mongo_client


def get_database() -> Any:
    global _database
    if _database is None:
        database_name = os.getenv("MONGODB_DB_NAME", DEFAULT_DATABASE_NAME)
        _database = get_mongo_client()[database_name]
    return _database


def get_blocks_collection() -> Any:
    return get_database()["blocks"]


def get_transactions_collection() -> Any:
    return get_database()["transactions"]


def get_chain_metadata_collection() -> Any:
    return get_database()["chain_metadata"]


def initialize_database() -> None:
    pymongo = _get_pymongo_module()
    get_mongo_client().admin.command("ping")
    get_blocks_collection().create_index(
        [("index", pymongo.ASCENDING)], unique=True, name="blocks_index_unique"
    )
    get_blocks_collection().create_index(
        [("hash", pymongo.ASCENDING)], unique=True, name="blocks_hash_unique"
    )
    get_blocks_collection().create_index(
        [("index", pymongo.DESCENDING)], name="blocks_index_desc"
    )


def close_database() -> None:
    global _mongo_client, _database
    if _mongo_client is not None:
        _mongo_client.close()
    _mongo_client = None
    _database = None
