from __future__ import annotations

import logging
import os
import shutil
from typing import Any

from .config import VOICES
from .gemini_service import transcribe_and_translate
from .media import (
    MediaError,
    build_srt,
    build_voice_track,
    extract_audio,
    mix_with_original,
    probe_duration,
    render_video,
)
from .store import (
    get_job,
    job_dir,
    output_files,
    reference_upload_path,
    reference_voice_path,
    source_path,
    update_job,
    update_progress,
)
from .tts_service import TTSError, synthesize_synced
from .voice_clone import VoiceCloneError, clone_clips, prepare_reference_voice

logger = logging.getLogger(__name__)


def _fail(job_id: str, exc: Exception, step: int) -> None:
    logger.error("Job %s failed at step %s: %s", job_id, step, exc, exc_info=True)
    latest = get_job(job_id)
    failed_step = int((latest or {}).get("step") or step)
    update_job(
        job_id,
        status="failed",
        step=failed_step,
        message="Dubbing failed. Review the error below and try again.",
        error=str(exc),
    )


def _transcript_for_client(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = ("id", "start", "end", "original", "khmer", "speed")
    return [{key: segment.get(key) for key in fields} for segment in segments]


def _render(
    job_id: str,
    segments: list[dict[str, Any]],
    voice: str,
    burn_subtitles: bool,
    voice_clone: bool = False,
) -> None:
    job = get_job(job_id)
    if job is None:
        return
    directory = job_dir(job_id)
    files = output_files(job)
    source = source_path(job)
    original_audio = files["original"].parent / "original_audio.mp3"
    settings = job.get("settings") or {}
    requested_voice_clone = bool(voice_clone or settings.get("voice_clone"))
    voice_clone = requested_voice_clone
    warnings: list[str] = []

    if not source.exists():
        raise MediaError("The uploaded source video is no longer available.")
    if not original_audio.exists():
        update_progress(job_id, step=1, progress=8, message="Restoring the source audio…")
        extract_audio(source, original_audio)

    video_duration = float(job.get("duration") or 0)
    if video_duration <= 0:
        video_duration = probe_duration(source)
        update_job(job_id, duration=round(video_duration, 3))

    update_progress(
        job_id,
        step=3,
        progress=50,
        message="Preparing the Khmer narration workspace…",
    )
    shutil.rmtree(directory / "tts", ignore_errors=True)
    shutil.rmtree(directory / "fitted", ignore_errors=True)
    shutil.rmtree(directory / "cloned", ignore_errors=True)
    shutil.rmtree(directory / "seedvc", ignore_errors=True)
    shutil.rmtree(directory / "stems", ignore_errors=True)
    shutil.rmtree(directory / "reference_work", ignore_errors=True)

    # ------------------------------------------------------------------
    # Free AI Voice Clone — reference voice (uploaded or auto-extracted)
    # ------------------------------------------------------------------
    reference = reference_voice_path(job)
    custom_reference = reference_upload_path(job)
    if voice_clone:
        previous_reference = job.get("reference") or {}
        reuse = (
            reference.exists()
            and reference.stat().st_size > 10_000
            and previous_reference.get("status") == "ready"
        )
        if reuse:
            update_progress(
                job_id,
                step=3,
                progress=53,
                message="Reusing the prepared reference voice for cloning…",
            )
            warnings.extend(previous_reference.get("warnings") or [])
        else:
            update_progress(
                job_id,
                step=3,
                progress=51,
                message=(
                    "Normalising your uploaded reference voice…"
                    if custom_reference is not None
                    else "Isolating clean vocals and slicing a 10–12s reference segment…"
                ),
            )
            try:
                prepared = prepare_reference_voice(
                    original_audio=original_audio,
                    work_dir=directory,
                    segments=segments,
                    duration=video_duration,
                    destination=reference,
                    custom_reference=custom_reference,
                    progress_callback=lambda message: update_job(job_id, message=message),
                )
            except VoiceCloneError as exc:
                if custom_reference is not None:
                    raise
                logger.warning("Auto reference extraction failed: %s", exc)
                warnings.append(
                    f"Voice cloning skipped: {exc} The standard Edge TTS voice was used instead."
                )
                voice_clone = False
                update_job(
                    job_id,
                    reference={
                        "source": "auto-extracted",
                        "status": "failed",
                        "error": str(exc),
                    },
                )
            else:
                warnings.extend(prepared.warnings)
                update_job(
                    job_id,
                    reference={
                        "source": prepared.source,
                        "status": "ready",
                        "isolation": prepared.isolation,
                        "duration": round(prepared.duration, 3),
                        "window_start": prepared.window_start,
                        "speech_seconds": prepared.speech_seconds,
                        "warnings": list(prepared.warnings),
                    },
                )
                update_progress(
                    job_id,
                    step=3,
                    progress=53,
                    message=(
                        f"Reference voice ready ({prepared.duration:.1f}s, "
                        f"{prepared.isolation}). Generating Khmer clips…"
                    ),
                )

    update_progress(
        job_id,
        step=3,
        progress=54,
        message=f"Generating {len(segments)} Khmer voice clips with Edge TTS…",
    )

    synced_clips = 0
    last_tts_progress = 54

    def tts_progress(message: str) -> None:
        nonlocal synced_clips, last_tts_progress
        if message.startswith("Synced Khmer clip"):
            synced_clips += 1
            next_progress = 55 + int(13 * synced_clips / max(1, len(segments)))
            if next_progress > last_tts_progress or synced_clips == len(segments):
                last_tts_progress = next_progress
                update_progress(
                    job_id,
                    step=3,
                    progress=min(68, next_progress),
                    message=message,
                )
        else:
            update_job(job_id, message=message)

    try:
        synthesis = synthesize_synced(
            segments=segments,
            voice=voice,
            work_dir=directory,
            video_duration=video_duration,
            progress_callback=tts_progress,
        )
    except TTSError as exc:
        raise TTSError(str(exc)) from exc
    warnings.extend(synthesis.warnings)

    clips = synthesis.clips

    # ------------------------------------------------------------------
    # Free AI Voice Clone — Seed-VC timbre conversion
    # ------------------------------------------------------------------
    if voice_clone and reference.exists():
        update_progress(
            job_id,
            step=3,
            progress=71,
            message=(
                f"Cloning the voice timbre on {len(clips)} Khmer clips with Seed-VC "
                "(this can take a few minutes)…"
            ),
        )
        completed = 0
        last_clone_progress = 71

        def clone_progress(message: str) -> None:
            nonlocal completed, last_clone_progress
            if message.startswith("Cloned Khmer clip"):
                completed += 1
                next_progress = 72 + int(11 * completed / max(1, len(clips)))
                if next_progress > last_clone_progress or completed == len(clips):
                    last_clone_progress = next_progress
                    update_progress(
                        job_id,
                        step=3,
                        progress=min(83, next_progress),
                        message=message,
                    )
            else:
                update_job(job_id, message=message)

        try:
            cloned = clone_clips(
                clips=clips,
                reference=reference,
                work_dir=directory,
                progress_callback=clone_progress,
            )
            clips = cloned.clips
            warnings.extend(cloned.warnings)
            if cloned.cloned:
                update_job(
                    job_id,
                    reference={
                        **(get_job(job_id) or {}).get("reference", {}),
                        "cloned_clips": cloned.cloned,
                    },
                )
        except VoiceCloneError as exc:
            logger.warning("Seed-VC cloning failed: %s", exc)
            warnings.append(
                f"Seed-VC voice cloning failed: {exc} The standard Edge TTS voice was used instead."
            )
    else:
        voice_clone = False
        latest_reference = (get_job(job_id) or {}).get("reference") or {}
        if (
            settings.get("voice_clone")
            and not reference.exists()
            and latest_reference.get("status") != "failed"
        ):
            warnings.append(
                "The reference voice is missing, so the standard Edge TTS voice was used."
            )

    update_progress(
        job_id,
        step=3,
        progress=84,
        message="Aligning each Khmer clip to its start timestamp…",
    )
    voice_track = directory / "khmer_voice.wav"
    build_voice_track(clips, video_duration, voice_track)

    update_progress(
        job_id,
        step=4,
        progress=88,
        message="Ducking the original music bed to 12% and mixing the Khmer narration…",
    )
    mixed_audio = files["audio"]
    mix_with_original(original_audio, voice_track, mixed_audio)

    srt_path = build_srt(segments, files["srt"])

    update_progress(
        job_id,
        step=4,
        progress=91,
        message=(
            "Burning Khmer subtitles and rendering the final MP4…"
            if burn_subtitles
            else "Rendering the final Khmer-dubbed MP4…"
        ),
    )
    temp_video = directory / "dubbed.next.mp4"
    try:
        render_video(
            source,
            mixed_audio,
            temp_video,
            burn_subtitles=burn_subtitles,
        )
        os.replace(temp_video, files["video"])
    finally:
        if temp_video.exists():
            temp_video.unlink(missing_ok=True)

    transcript = _transcript_for_client(segments)
    update_job(
        job_id,
        settings={
            **(job.get("settings") or {}),
            "voice": voice,
            "burn_subtitles": burn_subtitles,
            "voice_clone": requested_voice_clone,
        },
        transcript=transcript,
        progress=100,
        step=5,
        status="completed",
        message="Khmer dub is ready.",
        error=None,
        warnings=warnings,
        srt_path=srt_path.name,
    )


def run_initial_pipeline(job_id: str, api_key: str) -> None:
    """Step 1 + 2 + 3 + 4 for a newly uploaded video."""
    job = get_job(job_id)
    if job is None:
        return

    step = 1
    try:
        files = output_files(job)
        source = source_path(job)
        if not source.exists():
            raise MediaError("The uploaded video could not be found on disk.")

        step = 1
        update_job(job_id, status="processing", warnings=[])
        update_progress(job_id, step=1, progress=7, message="Extracting the original audio track…")
        duration = probe_duration(source)
        update_job(job_id, duration=round(duration, 3))
        original_audio = files["original"].parent / "original_audio.mp3"
        extract_audio(source, original_audio)
        update_progress(
            job_id,
            step=1,
            progress=24,
            message="Original audio extracted. Sending it to Gemini…",
        )

        step = 2
        update_progress(
            job_id,
            step=2,
            progress=29,
            message="Gemini is listening, transcribing, and translating into Khmer…",
        )
        settings = job.get("settings") or {}
        segments = transcribe_and_translate(
            original_audio,
            api_key=api_key,
            duration=duration,
            style=str(settings.get("style", "storytelling")),
        )
        for index, segment in enumerate(segments, start=1):
            segment["id"] = index

        update_job(
            job_id,
            transcript=_transcript_for_client(segments),
            progress=50,
            message=f"Translated {len(segments)} segments. Starting Khmer narration…",
        )
        update_progress(
            job_id,
            step=2,
            progress=50,
            message=f"Translated {len(segments)} segments. Starting Khmer narration…",
        )

        _render(
            job_id,
            segments,
            voice=str(settings.get("voice", "km-KH-SreymomNeural")),
            burn_subtitles=bool(settings.get("burn_subtitles", True)),
            voice_clone=bool(settings.get("voice_clone", False)),
        )
    except Exception as exc:
        _fail(job_id, exc, step)


def run_rerender_pipeline(job_id: str) -> None:
    """Re-run TTS, sync, mix, and encoding from an edited transcript."""
    job = get_job(job_id)
    if job is None:
        return

    step = 3
    try:
        settings = job.get("settings") or {}
        voice = str(settings.get("voice", "km-KH-SreymomNeural"))
        if voice not in VOICES:
            raise TTSError("Unsupported Khmer voice.")
        segments = list(job.get("transcript") or [])
        if not segments:
            raise TTSError("The transcript is empty. Add at least one Khmer segment.")

        _render(
            job_id,
            segments,
            voice=voice,
            burn_subtitles=bool(settings.get("burn_subtitles", True)),
            voice_clone=bool(settings.get("voice_clone", False)),
        )
    except Exception as exc:
        _fail(job_id, exc, step)
