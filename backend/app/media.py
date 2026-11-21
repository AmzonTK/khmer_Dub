from __future__ import annotations

import logging
import math
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

from pydub import AudioSegment

from .config import FFMPEG_BIN, FFPROBE_BIN, FONT_DIR, SUBTITLE_STYLE

logger = logging.getLogger(__name__)
AudioSegment.converter = FFMPEG_BIN


class MediaError(RuntimeError):
    pass


def run_command(args: Iterable[str], *, cwd: Path | None = None, timeout: int = 60 * 60) -> subprocess.CompletedProcess:
    command = [str(part) for part in args]
    logger.debug("Running: %s", shlex.join(command))
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MediaError(
            "FFmpeg was not found. Install it and make sure ffmpeg.exe and ffprobe.exe are on PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError("A media operation timed out. Try a shorter video.") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Unknown FFmpeg error").strip()
        logger.error("FFmpeg failed (%s): %s", result.returncode, detail[-6000:])
        raise MediaError(f"FFmpeg failed. {detail[-1800:]}")
    return result


def probe_duration(path: Path) -> float:
    result = run_command(
        [
            FFPROBE_BIN,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=60,
    )
    try:
        duration = float((result.stdout or "").strip())
    except ValueError as exc:
        raise MediaError(f"Could not read media duration for {path.name}.") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise MediaError(f"Invalid media duration for {path.name}.")
    return duration


def extract_audio(source: Path, destination: Path) -> Path:
    """Step 1: extract a high-quality mp3 used by Gemini and the final mix."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            FFMPEG_BIN,
            "-y",
            "-i",
            str(source),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            str(destination),
        ]
    )
    return destination


def _srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(segments: list[dict[str, Any]], destination: Path) -> Path:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        start = max(0.0, float(segment["start"]))
        end = max(start + 0.05, float(segment["end"]))
        text = " ".join(str(segment["khmer"]).split())
        if not text:
            continue
        lines.extend(
            [
                str(index),
                f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}",
                text,
                "",
            ]
        )
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def fit_audio_clip(raw_clip: Path, destination: Path, speed: float) -> Path:
    """Convert a clip to a 44.1 kHz mono WAV, optionally using atempo.

    Seed-VC output can be slightly shorter or longer than the Edge TTS clip it
    replaced, so this also supports slowing a clip down (atempo < 1) to protect
    the sync window.
    """
    filters = []
    if abs(speed - 1.0) > 0.001:
        filters.append(f"atempo={min(2.0, max(0.5, speed)):.4f}")
    args = [FFMPEG_BIN, "-y", "-i", str(raw_clip)]
    if filters:
        args += ["-filter:a", ",".join(filters)]
    args += ["-vn", "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(destination)]
    run_command(args, timeout=300)
    return destination


def build_voice_track(
    clips: list[tuple[float, Path]],
    total_duration: float,
    destination: Path,
) -> Path:
    """Overlay already-fitted TTS clips onto a silent master at exact timestamps."""
    total_ms = max(1000, int(math.ceil(total_duration * 1000)))
    master = AudioSegment.silent(duration=total_ms, frame_rate=44100).set_channels(1).set_sample_width(2)

    for start, clip_path in sorted(clips, key=lambda item: item[0]):
        clip = AudioSegment.from_file(clip_path)
        clip = clip.set_frame_rate(44100).set_channels(1).set_sample_width(2)
        # Normalize each narration clip gently while keeping the voice natural.
        if clip.max_dBFS < -1.0:
            clip = clip.apply_gain(min(12.0, -1.0 - clip.max_dBFS))
        position_ms = max(0, int(round(start * 1000)))
        master = master.overlay(clip, position=position_ms)

    # Always keep the final track equal to the source video length.
    if len(master) > total_ms:
        master = master[:total_ms]
    master.export(destination, format="wav")
    return destination


def mix_with_original(original_audio: Path, voice_track: Path, destination: Path) -> Path:
    """Duck the original music bed to 12% and mix the Khmer narration at 130%."""
    filter_graph = (
        "[0:a]volume=0.12[bg];"
        "[1:a]volume=1.3[fg];"
        "[bg][fg]amix=inputs=2:duration=first[aout]"
    )
    run_command(
        [
            FFMPEG_BIN,
            "-y",
            "-i",
            str(original_audio),
            "-i",
            str(voice_track),
            "-filter_complex",
            filter_graph,
            "-map",
            "[aout]",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ]
    )
    return destination


def _prepare_fonts(destination: Path) -> bool:
    """Copy the bundled OFL Khmer font next to the render so libass can find it."""
    if not FONT_DIR.exists():
        return False
    fonts_dir = destination.parent / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    copied = False
    for font_file in FONT_DIR.glob("*.[to]tf"):
        shutil.copy2(font_file, fonts_dir / font_file.name)
        copied = True
    return copied


def render_video(
    source: Path,
    mixed_audio: Path,
    destination: Path,
    *,
    burn_subtitles: bool = False,
) -> Path:
    """Encode a browser-friendly H.264/AAC MP4 and optionally burn Khmer subs."""
    args: list[str] = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(source),
        "-i",
        str(mixed_audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
    ]
    if burn_subtitles:
        has_fonts = _prepare_fonts(destination)
        font_option = ":fontsdir=fonts" if has_fonts else ""
        args += [
            "-vf",
            f"subtitles=khmer.srt{font_option}:force_style='{SUBTITLE_STYLE}'",
        ]
    args += [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    run_command(args, cwd=destination.parent)
    return destination


def find_audio_stream(path: Path) -> bool:
    result = run_command(
        [
            FFPROBE_BIN,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=60,
    )
    return "audio" in (result.stdout or "").lower()


def clean_partial_files(directory: Path, names: Iterable[str]) -> None:
    for name in names:
        path = directory / name
        try:
            if path.exists():
                path.unlink()
        except OSError:
            logger.warning("Could not delete partial file %s", path)
