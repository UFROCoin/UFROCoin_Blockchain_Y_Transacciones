import os
from functools import lru_cache
from importlib import import_module
from typing import Any


DEFAULT_MONGO_URI = "mongodb://localhost:27017/"
DEFAULT_DATABASE_NAME = "ufrocoin"

_mongo_client: Any | None = None
_database: Any | None = None


def _get_pymongo_module():
    """
    Importa pymongo de forma segura.
    Esto evita errores si pymongo no está instalado y entrega un mensaje claro.
    """
    try:
        return import_module("pymongo")
    except ImportError as exc:
        raise RuntimeError("pymongo is required to use MongoDB persistence") from exc


@lru_cache(maxsize=1)
def get_database_name() -> str:
    """
    Obtiene el nombre de la base de datos.

    Soporta ambas variables:
    - MONGO_DB_NAME
    - MONGODB_DB_NAME

    Si no existe ninguna, usa DEFAULT_DATABASE_NAME.
    """
    return (
        os.getenv("MONGO_DB_NAME")
        or os.getenv("MONGODB_DB_NAME")
        or DEFAULT_DATABASE_NAME
    )


def _build_mongodb_uri() -> str:
    """
    Construye la URI de MongoDB.

    Prioridad:
    1. MONGODB_URI directa.
    2. URI construida con usuario/password/host/port.
    3. URI local por defecto.
    """
    direct_uri = os.getenv("MONGODB_URI")
    if direct_uri:
        return direct_uri

    username = os.getenv("MONGO_INITDB_ROOT_USERNAME")
    password = os.getenv("MONGO_INITDB_ROOT_PASSWORD")
    host = os.getenv("MONGO_HOST", "localhost")
    port = os.getenv("MONGO_PORT", "27017")
    database = get_database_name()

    if username and password:
        return (
            f"mongodb://{username}:{password}@{host}:{port}/{database}"
            f"?authSource=admin"
        )

    return f"mongodb://{host}:{port}/{database}"


def get_mongo_client() -> Any:
    """
    Retorna un cliente MongoDB reutilizable.

    Compatible con el primer código.
    """
    global _mongo_client

    if _mongo_client is None:
        pymongo = _get_pymongo_module()
        mongodb_uri = _build_mongodb_uri()
        _mongo_client = pymongo.MongoClient(mongodb_uri)

    return _mongo_client


def get_db_client() -> Any:
    """
    Alias compatible con el segundo código.

    Usa el mismo cliente que get_mongo_client().
    """
    return get_mongo_client()


def get_database() -> Any:
    """
    Retorna la base de datos MongoDB configurada.
    """
    global _database

    if _database is None:
        _database = get_mongo_client()[get_database_name()]

    return _database


def get_blocks_collection() -> Any:
    return get_database()["blocks"]


def get_transactions_collection() -> Any:
    return get_database()["transactions"]


def get_chain_metadata_collection() -> Any:
    return get_database()["chain_metadata"]


def initialize_database() -> None:
    """
    Inicializa la conexión y crea índices necesarios para blockchain.

    Índices:
    - blocks.index único
    - blocks.hash único
    - blocks.index descendente
    """
    pymongo = _get_pymongo_module()

    get_mongo_client().admin.command("ping")

    blocks = get_blocks_collection()

    blocks.create_index(
        [("index", pymongo.ASCENDING)],
        unique=True,
        name="blocks_index_unique",
    )

    blocks.create_index(
        [("hash", pymongo.ASCENDING)],
        unique=True,
        name="blocks_hash_unique",
    )

    blocks.create_index(
        [("index", pymongo.DESCENDING)],
        name="blocks_index_desc",
    )


def close_database() -> None:
    """
    Cierra la conexión a MongoDB y limpia las referencias globales/cacheadas.
    """
    global _mongo_client, _database

    if _mongo_client is not None:
        _mongo_client.close()

    _mongo_client = None
    _database = None

    get_database_name.cache_clear()


def close_db_client() -> None:
    """
    Alias compatible con el segundo código.
    """
    close_database()