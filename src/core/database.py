import os
from functools import lru_cache

from pymongo import MongoClient


@lru_cache(maxsize=1)
def get_database_name() -> str:
    return os.getenv("MONGO_DB_NAME", "blockchain_db")


def _build_mongodb_uri() -> str:
    direct_uri = os.getenv("MONGODB_URI")
    if direct_uri:
        return direct_uri

    username = os.getenv("MONGO_INITDB_ROOT_USERNAME")
    password = os.getenv("MONGO_INITDB_ROOT_PASSWORD")
    host = os.getenv("MONGO_HOST", "mongodb")
    port = os.getenv("MONGO_PORT", "27017")
    database = get_database_name()

    if username and password:
        return (
            f"mongodb://{username}:{password}@{host}:{port}/{database}?authSource=admin"
        )

    return f"mongodb://{host}:{port}/{database}"


@lru_cache(maxsize=1)
def get_db_client() -> MongoClient:
    # Crea un cliente único reutilizable para toda la aplicación.
    mongodb_uri = _build_mongodb_uri()
    return MongoClient(mongodb_uri)


def close_db_client() -> None:
    # Cierra el cliente de MongoDB cuando la aplicación finaliza.
    try:
        client = get_db_client()
    except Exception:
        return

    client.close()
    get_db_client.cache_clear()
    get_database_name.cache_clear()
