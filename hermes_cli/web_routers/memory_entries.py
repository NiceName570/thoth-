"""Memories page routes: list, edit and delete the built-in MEMORY.md / USER.md entries.

Edits go through ``MemoryStore`` (file lock, drift guard, char limits, content scan) with the
full entry pinned, so a page opened before the agent rewrote an entry can never clobber the
newer one. The write-approval gate is skipped on purpose: the person editing IS the approver.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from hermes_cli.web_models import MemoryEntryEdit
from hermes_cli.web_routers._common import config_scoped_to_thread, destructive_profile

router = APIRouter()

_TARGETS = ("memory", "user")


def _target_snapshot(store, target: str) -> dict:
    return {"entries": list(store._entries_for(target)), "chars": store._char_count(target),
            "limit": store._char_limit(target), "enabled": store.target_enabled(target)}


@router.get("/api/memory/entries")
async def list_memory_entries(profile: Optional[str] = None):
    def _run():
        from tools.memory_tool import load_on_disk_store

        store = load_on_disk_store()
        return {target: _target_snapshot(store, target) for target in _TARGETS}

    return await config_scoped_to_thread(profile, _run)


@router.post("/api/memory/entries")
async def edit_memory_entry(body: MemoryEntryEdit, profile: Optional[str] = None):
    if body.target not in _TARGETS:
        raise HTTPException(status_code=400, detail="target must be memory or user")
    profile = destructive_profile(profile, "POST /api/memory/entries")

    def _run():
        from tools.memory_tool import load_on_disk_store

        store = load_on_disk_store()
        if body.content is None:
            result = store.remove(body.target, body.entry, matched_entry=body.entry)
        else:
            result = store.replace(body.target, body.entry, body.content, matched_entry=body.entry)
        if not result.get("success"):
            raise HTTPException(status_code=409, detail=result.get("error") or "Memory edit failed")
        return _target_snapshot(store, body.target)

    return await config_scoped_to_thread(profile, _run)
