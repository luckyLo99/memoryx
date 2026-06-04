from __future__ import annotations

import uuid

def new_conflict_group_id() -> str:
    return f"cg_{uuid.uuid4().hex}"

def norm(value: object) -> str:
    return str(value or "").strip().lower()

def is_same_slot(existing: dict, incoming: dict) -> bool:
    if existing.get("subject") or incoming.get("subject"):
        return (
            existing.get("claim_type") == incoming.get("claim_type")
            and norm(existing.get("subject")) == norm(incoming.get("subject"))
            and norm(existing.get("predicate")) == norm(incoming.get("predicate"))
        )
    return existing.get("claim_type") == incoming.get("claim_type")

def should_reinforce(existing: dict, incoming: dict) -> bool:
    return norm(existing.get("content")) == norm(incoming.get("content"))

def should_supersede(existing: dict, incoming: dict) -> bool:
    if not is_same_slot(existing, incoming):
        return False
    return norm(existing.get("content")) != norm(incoming.get("content"))
