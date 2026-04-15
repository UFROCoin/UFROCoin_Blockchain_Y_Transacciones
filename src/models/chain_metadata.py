from pydantic import BaseModel, ConfigDict


class ChainMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    genesis_created: bool
    last_block_index: int
    last_block_hash: str
    total_blocks: int
