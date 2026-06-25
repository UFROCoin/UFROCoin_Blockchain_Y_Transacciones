SYSTEM_REWARD = 1_000_000
REWARD_POOL = "REWARD_POOL"
SYSTEM_ADDRESS = "SYSTEM"
GENESIS_BLOCK_INDEX = 0
GENESIS_PREVIOUS_HASH = "0" * 64
GENESIS_TRANSACTION_TYPE = "GENESIS_ISSUANCE"
CHAIN_METADATA_ID = "chain_state"
BLOCKCHAIN_EVENTS_EXCHANGE = "ufrocoin.blockchain.events"
GENESIS_EVENT_ROUTING_KEY = "genesis.created"
TRANSACTION_EVENT_ROUTING_KEY = "transaction.created"

# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------

# Frecuencia por defecto: se genera un checkpoint cada 100 bloques.
# Sobreescribible con la variable de entorno CHECKPOINT_FREQUENCY.
DEFAULT_CHECKPOINT_FREQUENCY = 100

# Nombre por defecto de la colección MongoDB para checkpoints.
# Sobreescribible con la variable de entorno MONGO_CHECKPOINTS_COLLECTION.
DEFAULT_CHECKPOINTS_COLLECTION_NAME = "checkpoints"
