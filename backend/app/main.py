from __future__ import annotations

import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import (
    ALLOWED_ORIGINS,
    APP_NAME,
    APP_VERSION,
    FFMPEG_BIN,
    GEMINI_MODEL,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    REFERENCE_MAX_BYTES,
    REFERENCE_MAX_MB,
    REFERENCE_MAX_SECONDS,
    REFERENCE_MIN_SECONDS,
    VOICE_CLONE_ENABLED,
    VOICES,
)
from .models import RenderRequest
from .pipeline import run_initial_pipeline, run_rerender_pipeline
from .media import MediaError, probe_duration
from .store import (
    create_job,
    get_job,
    job_dir,
    output_files,
    public_job,
    recover_interrupted_jobs,
    reference_upload_path,
    reference_voice_path,
    source_path,
    update_job,
    utc_now,
)
from .voice_clone import cloning_available

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    recovered = recover_interrupted_jobs()
    if recovered:
        logger.warning("Marked %s interrupted job(s) as failed after restart.", recovered)
    yield


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="English-to-Khmer AI video dubbing with Gemini and Edge TTS.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length", "Accept-Ranges", "Content-Range"],
)

CHUNK_SIZE = 1024 * 1024
ALLOWED_EXTENSIONS = {".mp4", ".mov"}
ALLOWED_STYLES = {"storytelling", "normal"}
ALLOWED_REFERENCE_EXTENSIONS = {".wav", ".mp3"}
REFERENCE_MIN_TOUCHED = max(0.0, REFERENCE_MIN_SECONDS - 0.5)
REFERENCE_MAX_TOUCHED = REFERENCE_MAX_SECONDS + 0.5


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health() -> dict[str, object]:
    ffmpeg_ready = bool(shutil.which("ffmpeg") or Path(FFMPEG_BIN).exists())
    ffprobe_ready = bool(shutil.which("ffprobe"))
    return {
        "status": "ok" if ffmpeg_ready and ffprobe_ready else "degraded",
        "ffmpeg": ffmpeg_ready,
        "ffprobe": ffprobe_ready,
        "gemini_model": GEMINI_MODEL,
        "max_upload_mb": MAX_UPLOAD_MB,
        "voices": list(VOICES),
        "voice_clone": {
            "enabled": VOICE_CLONE_ENABLED,
            "available": VOICE_CLONE_ENABLED and cloning_available(),
            "reference_seconds": [REFERENCE_MIN_SECONDS, REFERENCE_MAX_SECONDS],
            "max_reference_mb": REFERENCE_MAX_MB,
        },
    }


async def _save_upload(
    upload: UploadFile,
    destination: Path,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
    max_mb: int = MAX_UPLOAD_MB,
    empty_detail: str = "The uploaded video is empty.",
    too_large_detail: str | None = None,
) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    total = 0
    try:
        with temporary.open("wb") as handle:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=too_large_detail
                        or f"The upload is larger than the {max_mb} MB limit.",
                    )
                handle.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail=empty_detail)
        temporary.replace(destination)
        return total
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


@app.post("/api/jobs", status_code=202)
async def create_dubbing_job(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    api_key: str = Form(...),
    voice: str = Form("km-KH-SreymomNeural"),
    style: str = Form("storytelling"),
    burn_subtitles: bool = Form(True),
    voice_clone: bool = Form(False),
    reference_voice: UploadFile | None = File(None),
) -> dict:
    if not api_key.strip():
        raise HTTPException(status_code=400, detail="A Gemini API key is required.")
    if voice not in VOICES:
        raise HTTPException(status_code=400, detail="Choose a supported Khmer voice.")
    if style not in ALLOWED_STYLES:
        raise HTTPException(status_code=400, detail="Style must be 'storytelling' or 'normal'.")

    original_name = Path(video.filename or "video.mp4").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Upload an .mp4 or .mov video file.")

    has_reference = reference_voice is not None and bool(reference_voice.filename)
    reference_suffix = ""
    if has_reference:
        reference_name = Path(reference_voice.filename or "").name
        reference_suffix = Path(reference_name).suffix.lower()
        if reference_suffix not in ALLOWED_REFERENCE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="The reference voice must be a .wav or .mp3 file.",
            )
        if not VOICE_CLONE_ENABLED:
            raise HTTPException(
                status_code=400,
                detail="Voice cloning is disabled on this server. Remove the reference voice and try again.",
            )
        voice_clone = True

    if voice_clone and not VOICE_CLONE_ENABLED:
        voice_clone = False

    job_id = str(uuid.uuid4())
    directory = job_dir(job_id)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"source{suffix}"
    reference_destination = directory / f"custom_reference{reference_suffix}" if has_reference else None

    try:
        await _save_upload(
            video,
            destination,
            empty_detail="The uploaded video is empty.",
            too_large_detail=f"The video is larger than the {MAX_UPLOAD_MB} MB upload limit.",
        )

        if reference_destination is not None and reference_voice is not None:
            await _save_upload(
                reference_voice,
                reference_destination,
                max_bytes=REFERENCE_MAX_BYTES,
                max_mb=REFERENCE_MAX_MB,
                empty_detail="The uploaded reference voice is empty.",
                too_large_detail=(
                    f"The reference voice is larger than the {REFERENCE_MAX_MB} MB limit."
                ),
            )
            try:
                reference_duration = probe_duration(reference_destination)
            except MediaError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Could not read the reference voice. Upload a valid .wav or .mp3 file.",
                ) from exc
            if not REFERENCE_MIN_TOUCHED <= reference_duration <= REFERENCE_MAX_TOUCHED:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"The reference voice is {reference_duration:.1f}s long. "
                        f"Upload {REFERENCE_MIN_SECONDS:.0f}–{REFERENCE_MAX_SECONDS:.0f} "
                        "seconds of clear, music-free speech."
                    ),
                )
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise

    created_at = utc_now()
    job = {
        "id": job_id,
        "status": "queued",
        "step": 0,
        "progress": 2,
        "message": "Upload received. Queued for processing…",
        "error": None,
        "warnings": [],
        "created_at": created_at,
        "updated_at": created_at,
        "duration": None,
        "source_filename": original_name,
        "source_ext": suffix,
        "reference_upload": reference_destination.name if reference_destination else None,
        "reference": None,
        "settings": {
            "voice": voice,
            "style": style,
            "burn_subtitles": burn_subtitles,
            "voice_clone": bool(voice_clone),
        },
        "transcript": [],
    }
    create_job(job)
    logger.info(
        "Created job %s for %s (%s style, %s, voice clone: %s)",
        job_id,
        original_name,
        style,
        voice,
        "custom reference" if has_reference else ("auto" if voice_clone else "off"),
    )
    background_tasks.add_task(run_initial_pipeline, job_id, api_key)
    return public_job(job)


@app.get("/api/jobs/{job_id}")
def read_job(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Dubbing job not found.")
    return public_job(job)


@app.post("/api/jobs/{job_id}/rerender", status_code=202)
def rerender_job(job_id: str, payload: RenderRequest, background_tasks: BackgroundTasks) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Dubbing job not found.")
    if job.get("status") in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="This job is already rendering. Please wait.")
    if not source_path(job).exists():
        raise HTTPException(status_code=409, detail="The source video is no longer available on disk.")

    duration = float(job.get("duration") or 0)
    if duration > 0:
        for index, segment in enumerate(payload.segments, start=1):
            if segment.end > duration + 0.25:
                raise HTTPException(
                    status_code=422,
                    detail=f"Segment {index} ends after the video ({segment.end:.2f}s > {duration:.2f}s).",
                )

    segments = []
    for index, segment in enumerate(payload.segments, start=1):
        item = segment.model_dump()
        item["id"] = index
        segments.append(item)

    settings = {
        **(job.get("settings") or {}),
        "voice": payload.voice,
        "burn_subtitles": payload.burn_subtitles,
        "voice_clone": (
            bool(payload.voice_clone)
            if payload.voice_clone is not None
            else bool((job.get("settings") or {}).get("voice_clone"))
        ),
    }
    update_job(
        job_id,
        settings=settings,
        transcript=segments,
        status="processing",
        step=3,
        progress=52,
        message=(
            "Preparing the reference voice and a fresh Khmer voice track…"
            if settings["voice_clone"]
            else "Preparing a fresh Khmer voice track…"
        ),
        error=None,
        warnings=[],
    )
    background_tasks.add_task(run_rerender_pipeline, job_id)
    updated = get_job(job_id)
    assert updated is not None
    return public_job(updated)


def _get_output(job_id: str, kind: str, *, inline: bool = False) -> FileResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Dubbing job not found.")
    files = output_files(job)
    if kind == "video":
        path = files["video"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="The dubbed video is not ready yet.")
        response = FileResponse(
            path,
            media_type="video/mp4",
            filename=f"khmer-dubbed-{job_id[:8]}.mp4",
            headers={"Cache-Control": "no-store"},
        )
    elif kind == "srt":
        path = files["srt"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="The subtitle file is not ready yet.")
        response = FileResponse(
            path,
            media_type="text/plain; charset=utf-8" if inline else "application/x-subrip; charset=utf-8",
            filename=f"khmer-subtitles-{job_id[:8]}.srt",
            headers={"Cache-Control": "no-store"},
        )
    elif kind == "reference":
        path = reference_voice_path(job)
        if not path.exists():
            path = reference_upload_path(job) or path
        if not path.exists():
            raise HTTPException(status_code=404, detail="The reference voice is not ready yet.")
        response = FileResponse(
            path,
            media_type="audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg",
            filename=f"reference-voice-{job_id[:8]}{path.suffix.lower()}",
            headers={"Cache-Control": "no-store"},
        )
    elif kind == "original":
        path = files["original"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="The source video is not available.")
        media_type = "video/quicktime" if path.suffix.lower() == ".mov" else "video/mp4"
        response = FileResponse(
            path,
            media_type=media_type,
            filename=job.get("source_filename", f"original{path.suffix}"),
            headers={"Cache-Control": "no-store"},
        )
    else:
        raise HTTPException(status_code=404, detail="Unknown download type.")

    if inline:
        response.headers["Content-Disposition"] = "inline"
    return response


@app.get("/api/jobs/{job_id}/media/video")
def stream_video(job_id: str) -> FileResponse:
    return _get_output(job_id, "video", inline=True)


@app.get("/api/jobs/{job_id}/media/original")
def stream_original(job_id: str) -> FileResponse:
    return _get_output(job_id, "original", inline=True)


@app.get("/api/jobs/{job_id}/media/reference")
def stream_reference(job_id: str) -> FileResponse:
    return _get_output(job_id, "reference", inline=True)


@app.get("/api/jobs/{job_id}/subtitles")
def subtitles(job_id: str) -> FileResponse:
    return _get_output(job_id, "srt", inline=True)


@app.get("/api/jobs/{job_id}/download/video")
def download_video(job_id: str) -> FileResponse:
    return _get_output(job_id, "video")


@app.get("/api/jobs/{job_id}/download/srt")
def download_srt(job_id: str) -> FileResponse:
    return _get_output(job_id, "srt")


@app.get("/api/jobs/{job_id}/download/original")
def download_original(job_id: str) -> FileResponse:
    return _get_output(job_id, "original")


@app.get("/api/jobs/{job_id}/download/reference")
def download_reference(job_id: str) -> FileResponse:
    return _get_output(job_id, "reference")
