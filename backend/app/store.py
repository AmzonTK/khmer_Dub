from __future__ import annotations

import json
import os
import re
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import JOBS_DIR

_JOB_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.RLock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def valid_job_id(job_id: str) -> bool:
    return bool(_JOB_ID_RE.fullmatch(job_id))


def job_dir(job_id: str) -> Path:
    if not valid_job_id(job_id):
        raise ValueError("Invalid job id.")
    return JOBS_DIR / job_id


def job_file(job_id: str) -> Path:
    return job_dir(job_id) / "job.json"


def _write(job: dict[str, Any]) -> None:
    directory = job_dir(job["id"])
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "job.json"
    temp = directory / "job.json.tmp"
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(job, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, target)


def _read(job_id: str) -> dict[str, Any] | None:
    path = job_file(job_id)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def create_job(job: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        _jobs[job["id"]] = deepcopy(job)
        job_dir(job["id"]).mkdir(parents=True, exist_ok=True)
        _write(job)
        return deepcopy(job)


def get_job(job_id: str) -> dict[str, Any] | None:
    if not valid_job_id(job_id):
        return None
    with _lock:
        cached = _jobs.get(job_id)
        if cached is None:
            cached = _read(job_id)
            if cached is not None:
                _jobs[job_id] = cached
        return deepcopy(cached) if cached is not None else None


def update_job(job_id: str, **changes: Any) -> dict[str, Any] | None:
    with _lock:
        current = get_job(job_id)
        if current is None:
            return None
        current.update(changes)
        current["updated_at"] = utc_now()
        _jobs[job_id] = current
        _write(current)
        return deepcopy(current)


def update_progress(
    job_id: str,
    *,
    step: int,
    progress: int,
    message: str,
    status: str = "processing",
) -> dict[str, Any] | None:
    return update_job(
        job_id,
        status=status,
        step=step,
        progress=max(0, min(100, int(progress))),
        message=message,
        error=None,
    )


def output_files(job: dict[str, Any]) -> dict[str, Path]:
    directory = job_dir(job["id"])
    files = {
        "video": directory / "dubbed.mp4",
        "srt": directory / "khmer.srt",
        "original": directory / f"source{job.get('source_ext', '.mp4')}",
        "audio": directory / "mixed_audio.wav",
    }
    return files


def source_path(job: dict[str, Any]) -> Path:
    return output_files(job)["original"]


def reference_upload_path(job: dict[str, Any]) -> Path | None:
    """The custom reference voice uploaded by the client, if any."""
    filename = job.get("reference_upload")
    if not filename:
        return None
    directory = job_dir(job["id"])
    candidate = (directory / str(filename)).resolve()
    if directory.resolve() not in candidate.parents:
        return None
    return candidate


def reference_voice_path(job: dict[str, Any]) -> Path:
    """The normalised 10–12s reference voice used by Seed-VC."""
    return job_dir(job["id"]) / "reference_voice.wav"


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    """Return a client-safe snapshot with relative media URLs."""
    snapshot = deepcopy(job)
    if snapshot.get("source_ext"):
        snapshot.pop("source_ext", None)
    snapshot.pop("reference_upload", None)
    files = output_files(job)
    base = f"/api/jobs/{job['id']}"
    media: dict[str, str] = {}
    downloads: dict[str, str] = {}
    if files["video"].exists():
        media["video"] = f"{base}/media/video"
        downloads["video"] = f"{base}/download/video"
    if files["srt"].exists():
        media["srt"] = f"{base}/subtitles"
        downloads["srt"] = f"{base}/download/srt"
    if files["original"].exists():
        media["original"] = f"{base}/media/original"
        downloads["original"] = f"{base}/download/original"
    reference = reference_voice_path(job)
    if reference.exists():
        media["reference"] = f"{base}/media/reference"
        downloads["reference"] = f"{base}/download/reference"
    snapshot["media"] = media
    snapshot["downloads"] = downloads
    snapshot["version"] = str(job.get("updated_at", "")).replace(":", "").replace(".", "")
    return snapshot


def recover_interrupted_jobs() -> int:
    """Mark jobs left mid-flight by a backend restart so the UI can recover."""
    recovered = 0
    for path in JOBS_DIR.glob("*/job.json"):
        job = _read(path.parent.name)
        if job and job.get("status") in {"queued", "processing"}:
            update_job(
                job["id"],
                status="failed",
                message="The backend restarted before this render finished.",
                error="This job was interrupted by a server restart. Re-run it to continue.",
            )
            recovered += 1
    return recovered
