"""Helpers for writing runtime status snapshots for the local UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jober.core.config import ensure_profile_dirs


STATUS_FILENAME = "runtime_status.json"


@dataclass
class StatusPaths:
    profile_id: str
    status_path: Path


def _get_paths(profile_id: str | None) -> StatusPaths:
    paths = ensure_profile_dirs(profile_id)
    return StatusPaths(profile_id=paths.profile_id, status_path=paths.profile_dir / STATUS_FILENAME)


def load_status(profile_id: str | None = None) -> dict:
    paths = _get_paths(profile_id)
    if not paths.status_path.exists():
        return {}
    try:
        return json.loads(paths.status_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_status(payload: dict, profile_id: str | None = None) -> Path:
    paths = _get_paths(profile_id)
    paths.status_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return paths.status_path


def update_status(profile_id: str | None = None, **fields) -> dict:
    status = load_status(profile_id)
    paths = _get_paths(profile_id)
    status["profile_id"] = paths.profile_id
    status.update(fields)
    status["updated_at"] = datetime.now().isoformat()
    save_status(status, profile_id)
    return status


def upsert_job(profile_id: str | None, job_update: dict) -> dict:
    status = load_status(profile_id)
    jobs = status.get("jobs", [])
    url = job_update.get("url")
    if not url:
        return status

    updated = False
    for idx, job in enumerate(jobs):
        if job.get("url") == url:
            merged = {**job, **job_update}
            merged["updated_at"] = datetime.now().isoformat()
            jobs[idx] = merged
            updated = True
            break

    if not updated:
        job_update["updated_at"] = datetime.now().isoformat()
        jobs.insert(0, job_update)

    status["jobs"] = jobs[:80]
    save_status(status, profile_id)
    return status
