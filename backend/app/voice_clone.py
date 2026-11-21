"""Reference-voice preparation and Seed-VC timbre cloning.

The "Free AI Voice Clone" mode works in two stages:

1. Build a clean ``reference_voice.wav``:
   - use the reference clip uploaded by the user, or
   - isolate vocals from the source track with Demucs, Audio Separator or an
     FFmpeg center-channel bandpass fallback, then slice a 10–12 second window
     that Gemini marked as active speech.
2. Convert every fitted Khmer Edge TTS clip with Seed-VC (Gradio Space or a
   local checkout) so it keeps the source speaker's timbre.

Every stage degrades gracefully: if cloning is unavailable the already generated
Edge TTS clips are used and a warning is attached to the job.
"""

from __future__ import annotations

import importlib.util
import logging
import math
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from pydub import AudioSegment
from pydub.silence import detect_leading_silence

from .config import (
    AUDIO_SEPARATOR_MODEL,
    DEMUCS_MODEL,
    FFMPEG_BIN,
    HF_TOKEN,
    MAX_ATEMPO,
    REFERENCE_MAX_SECONDS,
    REFERENCE_MIN_SECONDS,
    REFERENCE_WINDOW_MIN_SECONDS,
    REFERENCE_WINDOW_SECONDS,
    SEEDVC_API_NAME,
    SEEDVC_CFG_RATE,
    SEEDVC_CHECKPOINT,
    SEEDVC_CONCURRENCY,
    SEEDVC_DIFFUSION_STEPS,
    SEEDVC_LOCAL_DIR,
    SEEDVC_MAX_RETRIES,
    SEEDVC_SPACE,
    SEEDVC_TIMEOUT,
    VOCAL_ISOLATION_TIMEOUT,
)
from .media import MediaError, fit_audio_clip, probe_duration, run_command

logger = logging.getLogger(__name__)


class VoiceCloneError(RuntimeError):
    pass


@dataclass
class ReferenceResult:
    path: Path
    source: str  # "uploaded" | "auto-extracted"
    isolation: str  # "upload" | "demucs" | "audio-separator" | "ffmpeg"
    duration: float
    window_start: float | None = None
    speech_seconds: float | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class CloneResult:
    clips: list[tuple[float, Path]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cloned: int = 0
    failed: int = 0


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def cloning_available() -> bool:
    """True when Seed-VC can be reached through Gradio or a local checkout."""
    if SEEDVC_LOCAL_DIR and (Path(SEEDVC_LOCAL_DIR) / "inference.py").exists():
        return True
    return _module_available("gradio_client")


def _copy_or_keep(path: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if path.resolve() == destination.resolve():
        return destination
    shutil.copy2(path, destination)
    return destination


# ---------------------------------------------------------------------------
# Stage 1 — vocal isolation
# ---------------------------------------------------------------------------


def _demucs_vocals(original_audio: Path, work_dir: Path) -> Path:
    if not _module_available("demucs"):
        raise VoiceCloneError("demucs is not installed in the backend environment.")
    output_dir = work_dir / "stems" / "demucs"
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Isolating vocals with Demucs model %s", DEMUCS_MODEL)
    run_command(
        [
            sys.executable,
            "-m",
            "demucs",
            "--two-stems=vocals",
            "-n",
            DEMUCS_MODEL,
            "-o",
            str(output_dir),
            str(original_audio),
        ],
        timeout=VOCAL_ISOLATION_TIMEOUT,
    )
    candidates = sorted(output_dir.glob("**/vocals.wav"), key=lambda item: item.stat().st_size, reverse=True)
    if not candidates:
        raise VoiceCloneError("Demucs finished but produced no vocals stem.")
    return candidates[0]


def _audio_separator_vocals(original_audio: Path, work_dir: Path) -> Path:
    executable = shutil.which("audio-separator") or shutil.which("audio-separator.exe")
    if executable is None:
        if not _module_available("audio_separator"):
            raise VoiceCloneError("audio-separator is not installed in the backend environment.")
        prefix = [sys.executable, "-m", "audio_separator"]
    else:
        prefix = [executable]

    output_dir = work_dir / "stems" / "audio-separator"
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Isolating vocals with Audio Separator model %s", AUDIO_SEPARATOR_MODEL)
    run_command(
        [
            *prefix,
            str(original_audio),
            "--model_filename",
            AUDIO_SEPARATOR_MODEL,
            "--output_dir",
            str(output_dir),
            "--single_stem",
            "Vocals",
        ],
        timeout=VOCAL_ISOLATION_TIMEOUT,
    )
    candidates = [
        path
        for path in output_dir.glob("*.wav")
        if "vocal" in path.name.lower()
    ]
    if not candidates:
        candidates = sorted(output_dir.glob("*.wav"), key=lambda item: item.stat().st_size, reverse=True)
    if not candidates:
        raise VoiceCloneError("Audio Separator finished but produced no vocals stem.")
    return max(candidates, key=lambda item: item.stat().st_size)


def _ffmpeg_vocals(original_audio: Path, work_dir: Path) -> Path:
    """Center-channel + bandpass fallback that needs nothing but FFmpeg.

    Vocals sit in the middle of a stereo mix, so averaging both channels keeps
    them while attenuating hard-panned music. A speech bandpass, light denoise
    and presence boost clean up the result enough for Seed-VC.
    """
    output_dir = work_dir / "stems"
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "ffmpeg_vocals.wav"
    logger.info("Isolating vocals with the FFmpeg vocal bandpass fallback")
    filter_graph = (
        "aformat=channel_layouts=stereo,"
        "pan=mono|c0=0.5*c0+0.5*c1,"
        "highpass=f=90,"
        "lowpass=f=9500,"
        "afftdn=nf=-25,"
        "equalizer=f=250:t=q:w=1.0:g=-2,"
        "equalizer=f=3000:t=q:w=1.2:g=3,"
        "dynaudnorm=f=150:g=15"
    )
    run_command(
        [
            FFMPEG_BIN,
            "-y",
            "-i",
            str(original_audio),
            "-vn",
            "-filter:a",
            filter_graph,
            "-ac",
            "1",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        timeout=VOCAL_ISOLATION_TIMEOUT,
    )
    return destination


def separate_vocals(original_audio: Path, work_dir: Path) -> tuple[Path, str, list[str]]:
    """Return ``(vocal_track, method, warnings)`` using the best tool available."""
    warnings: list[str] = []
    attempts: Sequence[tuple[str, Callable[[Path, Path], Path]]] = (
        ("demucs", _demucs_vocals),
        ("audio-separator", _audio_separator_vocals),
        ("ffmpeg", _ffmpeg_vocals),
    )
    for method, function in attempts:
        try:
            path = function(original_audio, work_dir)
            if path.exists() and path.stat().st_size > 1024:
                if method != "ffmpeg":
                    logger.info("Vocal isolation succeeded with %s", method)
                else:
                    warnings.append(
                        "Demucs / Audio Separator are not installed, so the reference voice was "
                        "isolated with the FFmpeg speech-band filter. Install demucs for cleaner cloning."
                    )
                return path, method, warnings
            logger.warning("%s produced an empty vocals file; trying the next method", method)
        except (VoiceCloneError, MediaError, OSError) as exc:
            logger.warning("Vocal isolation with %s failed: %s", method, exc)
        except subprocess.SubprocessError as exc:  # pragma: no cover - defensive
            logger.warning("Vocal isolation with %s crashed: %s", method, exc)

    raise VoiceCloneError(
        "Could not isolate vocals from the source video. Install demucs or upload a custom "
        "reference voice (.wav/.mp3, 5–15s)."
    )


# ---------------------------------------------------------------------------
# Stage 1b — slice the best active-speech window
# ---------------------------------------------------------------------------


def choose_speech_window(
    segments: Sequence[dict[str, Any]],
    duration: float,
    window_seconds: float = REFERENCE_WINDOW_SECONDS,
) -> tuple[float, float, float]:
    """Pick the densest active-speech window.

    Returns ``(start, length, speech_seconds)``. Candidate starts come from the
    Gemini speech timestamps so the reference never starts in the middle of a
    silent intro or a music-only montage.
    """
    if duration <= 0:
        raise VoiceCloneError("The source audio has no measurable duration.")

    length = min(max(window_seconds, REFERENCE_WINDOW_MIN_SECONDS), duration)
    if length <= 0:
        length = duration
    if duration <= length + 0.05:
        start = 0.0
        length = duration
        speech = sum(
            max(0.0, min(duration, float(seg["end"])) - max(0.0, float(seg["start"])))
            for seg in segments
        )
        return start, length, speech

    starts: set[float] = {0.0, max(0.0, duration - length)}
    for segment in segments:
        try:
            segment_start = float(segment["start"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(segment_start):
            continue
        candidate = max(0.0, min(segment_start - 0.1, duration - length))
        starts.add(round(candidate, 3))

    best_start = 0.0
    best_speech = -1.0
    for start in sorted(starts):
        end = start + length
        speech = 0.0
        for segment in segments:
            try:
                segment_start = float(segment["start"])
                segment_end = float(segment["end"])
            except (KeyError, TypeError, ValueError):
                continue
            speech += max(0.0, min(end, segment_end) - max(start, segment_start))
        # Prefer a cleanly covered window; later windows win exact ties so a
        # candidate anchored on a real speech onset beats a silent intro.
        if speech >= best_speech - 1e-6:
            best_speech = speech
            best_start = start

    return best_start, length, max(0.0, best_speech)


def _trim_silence(audio: AudioSegment, threshold: int = -40) -> AudioSegment:
    start_ms = detect_leading_silence(audio, silence_threshold=threshold, chunk_size=10)
    end_ms = detect_leading_silence(audio.reverse(), silence_threshold=threshold, chunk_size=10)
    trimmed = audio[start_ms : max(start_ms + 100, len(audio) - end_ms)]
    return trimmed if len(trimmed) > 0 else audio


def _normalise_reference(source: Path, destination: Path) -> Path:
    """Mono 44.1 kHz, loudness-normalised WAV that Seed-VC likes."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            FFMPEG_BIN,
            "-y",
            "-i",
            str(source),
            "-vn",
            "-af",
            "loudnorm=I=-18:TP=-1.5:LRA=11",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        timeout=600,
    )
    return destination


def _slice_reference(
    vocals: Path,
    destination: Path,
    start: float,
    length: float,
) -> Path:
    work_dir = destination.parent / "reference_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    raw = work_dir / "window_raw.wav"
    trimmed = work_dir / "window_trimmed.wav"

    run_command(
        [
            FFMPEG_BIN,
            "-y",
            "-ss",
            f"{max(0.0, start):.3f}",
            "-t",
            f"{max(0.5, length):.3f}",
            "-i",
            str(vocals),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(raw),
        ],
        timeout=600,
    )

    audio = AudioSegment.from_file(raw)
    cleaned = _trim_silence(audio)
    # Keep the raw window when aggressive trimming would leave too little voice.
    if len(cleaned) < REFERENCE_MIN_SECONDS * 1000 <= len(audio):
        cleaned = audio
    cleaned = cleaned.fade_in(30).fade_out(80)
    cleaned = cleaned.set_frame_rate(44100).set_channels(1).set_sample_width(2)
    cleaned.export(trimmed, format="wav")

    return _normalise_reference(trimmed, destination)


def prepare_reference_voice(
    *,
    original_audio: Path,
    work_dir: Path,
    segments: Sequence[dict[str, Any]],
    duration: float,
    destination: Path,
    custom_reference: Path | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> ReferenceResult:
    """Build ``reference_voice.wav`` from an upload or from the source track."""
    warnings: list[str] = []

    if custom_reference is not None and custom_reference.exists():
        if progress_callback:
            progress_callback("Normalising the uploaded reference voice…")
        raw_duration = probe_duration(custom_reference)
        if raw_duration < REFERENCE_MIN_SECONDS - 0.05:
            raise VoiceCloneError(
                f"The reference voice is {raw_duration:.1f}s long. Upload at least "
                f"{REFERENCE_MIN_SECONDS:.0f} seconds of clear speech."
            )
        normalised = _normalise_reference(custom_reference, destination)
        if raw_duration > REFERENCE_MAX_SECONDS + 0.5:
            warnings.append(
                f"The reference voice is {raw_duration:.1f}s; Seed-VC works best with "
                f"{REFERENCE_MIN_SECONDS:.0f}–{REFERENCE_MAX_SECONDS:.0f}s of clean speech."
            )
        return ReferenceResult(
            path=normalised,
            source="uploaded",
            isolation="upload",
            duration=probe_duration(normalised),
            warnings=warnings,
        )

    if progress_callback:
        progress_callback("Isolating clean vocals from the source audio for voice cloning…")
    vocals, method, isolation_warnings = separate_vocals(original_audio, work_dir)
    warnings.extend(isolation_warnings)

    if progress_callback:
        progress_callback("Selecting a clean 10–12 second speech segment for the reference…")
    start, length, speech = choose_speech_window(segments, duration)
    if speech < REFERENCE_WINDOW_MIN_SECONDS * 0.5:
        warnings.append(
            "Gemini found very little active speech for the reference window; "
            "the cloned voice may be less accurate."
        )

    reference = _slice_reference(vocals, destination, start, length)
    reference_duration = probe_duration(reference)
    if reference_duration < REFERENCE_MIN_SECONDS:
        warnings.append(
            f"The extracted reference is only {reference_duration:.1f}s long. "
            "Upload a custom 5–15s reference for the best clone."
        )

    if progress_callback:
        progress_callback(
            f"Reference voice ready: {reference_duration:.1f}s of isolated vocals ({method})."
        )

    return ReferenceResult(
        path=reference,
        source="auto-extracted",
        isolation=method,
        duration=reference_duration,
        window_start=round(start, 3),
        speech_seconds=round(speech, 3),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Stage 2 — Seed-VC timbre conversion
# ---------------------------------------------------------------------------

_thread_state = threading.local()

_FATAL_MARKERS = (
    "quota",
    "zerogpu",
    "authenticate",
    "unauthorized",
    "forbidden",
    "not installed",
    "not reachable",
    "invalid api key",
    "401",
    "403",
)


def _is_fatal_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _FATAL_MARKERS)


def _client() -> Any:
    client = getattr(_thread_state, "client", None)
    if client is None:
        try:
            from gradio_client import Client
        except ImportError as exc:  # pragma: no cover - depends on install
            raise VoiceCloneError(
                "gradio_client is not installed. Add it with: pip install gradio_client"
            ) from exc
        client = Client(
            SEEDVC_SPACE,
            hf_token=HF_TOKEN or None,
            verbose=False,
        )
        _thread_state.client = client
    return client


def _extract_result_path(result: Any) -> Path | None:
    """Gradio spaces return a path, a tuple, or a FileData dict."""
    if isinstance(result, dict):
        for key in ("path", "name", "url"):
            value = result.get(key)
            if isinstance(value, str) and value:
                path = Path(value)
                if path.exists():
                    return path
        return None
    if isinstance(result, (tuple, list)):
        for item in reversed(result):
            path = _extract_result_path(item)
            if path is not None:
                return path
        return None
    if isinstance(result, str):
        path = Path(result)
        if path.exists():
            return path
    return None


def _call_seedvc(source: Path, reference: Path, output_dir: Path, tag: str) -> Path:
    from gradio_client import handle_file

    client = _client()
    source_file = handle_file(str(source))
    reference_file = handle_file(str(reference))

    # The public Seed-VC Space exposes `/predict_1` (classic Seed-VC) and
    # `/predict` (newer intelligibility/similarity controls). Try both.
    attempts: list[tuple[str, dict[str, Any], tuple[Any, ...], str]] = [
        (
            "classic-keyword-args",
            {
                "source_audio_path": source_file,
                "target_audio_path": reference_file,
                "diffusion_steps": SEEDVC_DIFFUSION_STEPS,
                "length_adjust": 1.0,
                "inference_cfg_rate": SEEDVC_CFG_RATE,
                "f0_condition": False,
                "auto_f0_adjust": False,
                "pitch_shift": 0,
            },
            (),
            SEEDVC_API_NAME,
        ),
        (
            "classic-positional",
            {},
            (
                source_file,
                reference_file,
                SEEDVC_DIFFUSION_STEPS,
                1.0,
                SEEDVC_CFG_RATE,
                False,
                False,
                0,
            ),
            SEEDVC_API_NAME,
        ),
        (
            "newer-predict",
            {},
            (
                source_file,
                reference_file,
                SEEDVC_DIFFUSION_STEPS,
                1.0,
                SEEDVC_CFG_RATE,
                SEEDVC_CFG_RATE,
                0.95,
                1.0,
                1.0,
                False,
                False,
            ),
            "/predict",
        ),
        ("minimal-pair", {}, (source_file, reference_file), SEEDVC_API_NAME),
    ]

    last_error: Exception | None = None
    for label, kwargs, positional, api_name in attempts:
        try:
            if kwargs:
                result = client.predict(**kwargs, api_name=api_name)
            else:
                result = client.predict(*positional, api_name=api_name)
            path = _extract_result_path(result)
            if path is None:
                raise VoiceCloneError("Seed-VC returned no audio file.")
            destination = output_dir / f"{tag}{path.suffix or '.wav'}"
            return _copy_or_keep(path, destination)
        except Exception as exc:  # the Space raises many transport/tuple errors
            last_error = exc
            logger.debug("Seed-VC %s call failed for %s: %s", label, source.name, exc)

    detail = str(last_error) if last_error is not None else "Unknown Seed-VC error."
    if "zerogpu" in detail.lower() or "quota" in detail.lower() or "exceeded" in detail.lower():
        raise VoiceCloneError(
            "The hosted Seed-VC GPU quota is exhausted. Add a Hugging Face token as "
            "HF_TOKEN in backend/.env, try again later, or set SEEDVC_LOCAL_DIR to run "
            "Seed-VC locally."
        )
    raise VoiceCloneError(f"Seed-VC conversion failed: {detail}")


def _call_seedvc_local(source: Path, reference: Path, output_dir: Path, tag: str) -> Path:
    script = Path(SEEDVC_LOCAL_DIR) / "inference.py"
    if not script.exists():
        raise VoiceCloneError(f"Seed-VC inference.py was not found in {SEEDVC_LOCAL_DIR}.")
    output = output_dir / f"{tag}.wav"
    args = [
        sys.executable,
        str(script),
        "--source",
        str(source),
        "--target",
        str(reference),
        "--output",
        str(output),
        "--diffusion-steps",
        str(SEEDVC_DIFFUSION_STEPS),
        "--length-adjust",
        "1.0",
        "--inference-cfg-rate",
        str(SEEDVC_CFG_RATE),
        "--f0-condition",
        "False",
        "--auto-f0-adjust",
        "False",
        "--semi-tone-shift",
        "0",
    ]
    if SEEDVC_CHECKPOINT:
        args += ["--checkpoint", SEEDVC_CHECKPOINT]
    run_command(args, cwd=Path(SEEDVC_LOCAL_DIR), timeout=SEEDVC_TIMEOUT)
    if not output.exists():
        candidates = sorted(output_dir.glob(f"{tag}*.wav"))
        if not candidates:
            raise VoiceCloneError("Seed-VC local inference produced no audio file.")
        return candidates[0]
    return output


def _retime(converted: Path, original: Path, destination: Path) -> Path:
    """Keep the cloned clip inside the exact Edge TTS timing window."""
    try:
        target = probe_duration(original)
        actual = probe_duration(converted)
    except MediaError:
        return _copy_or_keep(converted, destination)
    if target <= 0 or actual <= 0:
        return _copy_or_keep(converted, destination)

    speed = actual / target
    if not math.isfinite(speed) or speed <= 0:
        speed = 1.0
    speed = min(MAX_ATEMPO, max(0.85, speed))
    fit_audio_clip(converted, destination, speed)
    return destination


def _convert_one(
    source: Path,
    reference: Path,
    output_dir: Path,
    tag: str,
    destination: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(SEEDVC_MAX_RETRIES):
        try:
            if SEEDVC_LOCAL_DIR and (Path(SEEDVC_LOCAL_DIR) / "inference.py").exists():
                converted = _call_seedvc_local(source, reference, output_dir, tag)
            else:
                converted = _call_seedvc(source, reference, output_dir, tag)
            return _retime(converted, source, destination)
        except Exception as exc:
            last_error = exc
            if _is_fatal_error(str(exc)):
                # No point retrying an exhausted quota / missing dependency.
                raise
            if attempt < SEEDVC_MAX_RETRIES - 1:
                time.sleep(2.0 * (attempt + 1))
    raise VoiceCloneError(str(last_error) if last_error else "Seed-VC conversion failed.")


def clone_clips(
    clips: Sequence[tuple[float, Path]],
    reference: Path,
    work_dir: Path,
    progress_callback: Callable[[str], None] | None = None,
) -> CloneResult:
    """Convert every fitted clip to the reference timbre with Seed-VC."""
    if not reference.exists():
        raise VoiceCloneError("The reference voice file is missing.")
    if not cloning_available():
        raise VoiceCloneError(
            "Seed-VC is not reachable. Install gradio_client (pip install gradio_client) or set "
            "SEEDVC_LOCAL_DIR to a local Seed-VC checkout."
        )
    if not clips:
        return CloneResult()

    output_dir = work_dir / "seedvc"
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination_dir = work_dir / "cloned"
    shutil.rmtree(destination_dir, ignore_errors=True)
    destination_dir.mkdir(parents=True, exist_ok=True)

    result = CloneResult()
    total = len(clips)
    completed = 0
    abort = threading.Event()
    fatal_reason: list[str] = []
    fatal_lock = threading.Lock()

    def worker(index: int, start: float, clip_path: Path) -> tuple[float, Path, bool]:
        if abort.is_set():
            return start, clip_path, False
        destination = destination_dir / f"segment_{index + 1:03d}.wav"
        try:
            converted = _convert_one(
                clip_path,
                reference,
                output_dir,
                f"segment_{index + 1:03d}",
                destination,
            )
            return start, converted, True
        except Exception as exc:
            message = str(exc)
            if _is_fatal_error(message):
                with fatal_lock:
                    if not fatal_reason:
                        fatal_reason.append(message)
                abort.set()
            raise

    try:
        with ThreadPoolExecutor(max_workers=SEEDVC_CONCURRENCY) as pool:
            futures = {
                pool.submit(worker, index, start, path): (index, start, path)
                for index, (start, path) in enumerate(clips)
            }
            for future in as_completed(futures):
                index, start, path = futures[future]
                completed += 1
                if future.cancelled():
                    result.clips.append((start, path))
                    continue
                try:
                    new_start, converted, cloned = future.result()
                    result.clips.append((new_start, converted))
                    if cloned:
                        result.cloned += 1
                except Exception as exc:
                    logger.warning("Seed-VC failed for clip %s: %s", index + 1, exc)
                    result.failed += 1
                    result.clips.append((start, path))
                    if abort.is_set():
                        # Drop the remaining queued conversions instead of hammering
                        # an exhausted quota / missing dependency for every clip.
                        for pending in futures:
                            pending.cancel()
                if progress_callback:
                    progress_callback(
                        f"Cloned Khmer clip {completed} of {total} with Seed-VC…"
                    )
    except Exception as exc:
        raise VoiceCloneError(f"Seed-VC conversion failed: {exc}") from exc

    if fatal_reason:
        raise VoiceCloneError(fatal_reason[0])

    result.clips.sort(key=lambda item: item[0])
    if result.failed:
        result.warnings.append(
            f"Seed-VC could not clone {result.failed} of {total} clips; those lines kept the "
            "standard Edge TTS voice."
        )
    return result
