from __future__ import annotations

import asyncio
import logging
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import edge_tts

from .config import (
    EDGE_TTS_ATTEMPTS,
    EDGE_TTS_CONCURRENCY,
    EDGE_TTS_RETRY_DELAY,
    EDGE_TTS_TIMEOUT,
    MAX_ATEMPO,
)
from .media import fit_audio_clip, probe_duration

logger = logging.getLogger(__name__)


class TTSError(RuntimeError):
    pass


@dataclass
class SynthesisResult:
    clips: list[tuple[float, Path]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _retry_delay(attempt: int) -> float:
    """Exponential backoff with jitter so parallel workers do not retry in lockstep."""
    base = EDGE_TTS_RETRY_DELAY * (2 ** attempt)
    return min(15.0, base) + random.uniform(0, 0.8)


async def _synthesize_attempt(text: str, voice: str, destination: Path) -> None:
    destination.unlink(missing_ok=True)
    communicator = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate="+0%",
        volume="+0%",
    )
    await asyncio.wait_for(communicator.save(str(destination)), timeout=EDGE_TTS_TIMEOUT)
    if not destination.exists() or destination.stat().st_size <= 1024:
        raise TTSError("Edge TTS returned an empty audio clip.")


async def _synthesize_one(text: str, voice: str, destination: Path, label: str) -> None:
    last_error: Exception | None = None
    for attempt in range(EDGE_TTS_ATTEMPTS):
        try:
            await _synthesize_attempt(text, voice, destination)
            if attempt:
                logger.info("Edge TTS recovered %s on attempt %s.", label, attempt + 1)
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Edge TTS attempt %s/%s failed for %s: %s",
                attempt + 1,
                EDGE_TTS_ATTEMPTS,
                label,
                exc,
            )
            if attempt < EDGE_TTS_ATTEMPTS - 1:
                await asyncio.sleep(_retry_delay(attempt))
    destination.unlink(missing_ok=True)
    raise TTSError(f"Edge TTS failed for {label}: {last_error}")


async def _synthesize_wave(
    jobs: list[tuple[dict[str, Any], Path]],
    voice: str,
    concurrency: int,
) -> list[tuple[dict[str, Any], Path, Exception]]:
    """Run one pass and return every failure instead of aborting the whole batch."""
    semaphore = asyncio.Semaphore(concurrency)

    async def worker(segment: dict[str, Any], destination: Path):
        async with semaphore:
            label = f"segment {segment.get('id') or '?'}"
            try:
                await _synthesize_one(str(segment["khmer"]), voice, destination, label)
            except Exception as exc:
                return segment, destination, exc
            return None

    results = await asyncio.gather(*(worker(segment, path) for segment, path in jobs))
    return [result for result in results if result is not None]


async def _synthesize_all(
    jobs: list[tuple[dict[str, Any], Path]],
    voice: str,
    concurrency: int,
) -> None:
    """Synthesize every clip, retrying failures in increasingly cautious waves.

    Microsoft's Edge endpoint occasionally returns ``NoAudioReceived`` for a
    perfectly valid request. A failed phrase used to abort the whole job, so we
    now collect the failures and retry them sequentially before giving up.
    """
    pending = list(jobs)
    for wave, wave_concurrency in enumerate((concurrency, 1)):
        if not pending:
            return
        if wave:
            logger.info(
                "Retrying %s Edge TTS clip(s) sequentially after a partial wave failure.",
                len(pending),
            )
            await asyncio.sleep(2.0)
        failures = await _synthesize_wave(pending, voice, wave_concurrency)
        pending = [(segment, path) for segment, path, _ in failures]
        if not pending:
            return
        if len(pending) < len(jobs):
            logger.warning("%s Edge TTS clip(s) still failing; retrying.", len(pending))

    if pending:
        numbers = sorted(str(segment.get("id") or "?") for segment, _ in pending)
        raise TTSError(
            "Edge TTS could not synthesize segment(s) "
            f"{', '.join(numbers[:8])}"
            f"{'…' if len(numbers) > 8 else ''} after {EDGE_TTS_ATTEMPTS} attempts each. "
            "Microsoft's speech endpoint is temporarily refusing requests — wait a minute and retry."
        )


def synthesize_synced(
    segments: list[dict[str, Any]],
    voice: str,
    work_dir: Path,
    video_duration: float,
    progress_callback: Callable[[str], None] | None = None,
) -> SynthesisResult:
    """Generate TTS clips and fit each clip to its next-phrase window with atempo."""
    raw_dir = work_dir / "tts"
    fitted_dir = work_dir / "fitted"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fitted_dir.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[dict[str, Any], Path]] = []
    for index, segment in enumerate(segments):
        text = " ".join(str(segment.get("khmer", "")).split()).strip()
        if not text:
            continue
        segment["khmer"] = text
        raw_path = raw_dir / f"segment_{index + 1:03d}.mp3"
        jobs.append((segment, raw_path))

    if not jobs:
        raise TTSError("There is no Khmer text to synthesize.")

    if progress_callback:
        progress_callback(f"Generating {len(jobs)} Khmer voice clips with Edge TTS…")
    try:
        asyncio.run(_synthesize_all(jobs, voice, EDGE_TTS_CONCURRENCY))
    except TTSError:
        raise
    except Exception as exc:
        raise TTSError(f"Edge TTS failed: {exc}") from exc

    result = SynthesisResult()
    for index, (segment, raw_path) in enumerate(jobs):
        start = float(segment["start"])
        if index + 1 < len(jobs):
            # The exact sync window specified by the pipeline: until the next phrase begins.
            available_window = float(jobs[index + 1][0]["start"]) - start
        else:
            available_window = float(segment["end"]) - start
        available_window = max(0.25, min(available_window, max(0.25, video_duration - start)))

        try:
            tts_duration = probe_duration(raw_path)
        except Exception as exc:
            raise TTSError("Could not measure a generated Khmer voice clip.") from exc

        needed_speed = tts_duration / available_window
        requested_speed = float(segment.get("speed", 1.0) or 1.0)
        speed = max(1.0, requested_speed, min(needed_speed, MAX_ATEMPO))
        speed = min(MAX_ATEMPO, max(1.0, speed))
        if not math.isfinite(speed):
            speed = 1.0

        fitted_path = fitted_dir / f"segment_{index + 1:03d}.wav"
        fit_audio_clip(raw_path, fitted_path, speed)

        fitted_duration = probe_duration(fitted_path)
        if fitted_duration > available_window + 0.08:
            result.warnings.append(
                f"Segment {index + 1} is still slightly longer than its window after {speed:.2f}x speed-up."
            )

        segment["speed"] = round(speed, 3)
        segment["tts_duration"] = round(tts_duration, 3)
        segment["fitted_duration"] = round(fitted_duration, 3)
        result.clips.append((start, fitted_path))

        if progress_callback:
            progress_callback(f"Synced Khmer clip {index + 1} of {len(jobs)}…")

    return result
