import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {
            key: _normalize_value(inner_value)
            for key, inner_value in value.items()
            if key not in {"_id", "hash"}
        }
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def serialize_block_for_hash(block_data: dict[str, Any]) -> str:
    normalized_block = _normalize_value(block_data)
    return json.dumps(normalized_block, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def calculate_block_hash(block_data: dict[str, Any]) -> str:
    serialized_block = serialize_block_for_hash(block_data)
    return hashlib.sha256(serialized_block.encode("utf-8")).hexdigest()
