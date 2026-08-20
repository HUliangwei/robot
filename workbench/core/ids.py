from __future__ import annotations
import uuid

def new_id(prefix: str) -> str:
    clean = prefix.strip().lower().replace(" ", "_")
    if not clean:
        raise ValueError("prefix must not be empty")
    return f"{clean}_{uuid.uuid4().hex[:12]}"
