from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from .config import GEMINI_MODEL

logger = logging.getLogger(__name__)

_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


class GeminiError(RuntimeError):
    pass


_STYLE_GUIDE = {
    "storytelling": (
        "Cinematic movie-recap storytelling. Sound like a professional Khmer movie narrator: "
        "dramatic but natural, suspenseful pacing, vivid verbs, and idiomatic spoken Khmer. "
        "It is fine to condense redundant English, but never invent story details."
    ),
    "normal": (
        "Natural, clear, faithful spoken Khmer. Keep the meaning, tone, names, and key details "
        "of the English narration. Avoid stiff word-for-word phrasing."
    ),
}


def _response_schema() -> dict[str, Any]:
    return {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "start": {"type": "NUMBER"},
                "end": {"type": "NUMBER"},
                "original": {"type": "STRING"},
                "khmer": {"type": "STRING"},
            },
            "required": ["start", "end", "original", "khmer"],
        },
    }


def _build_prompt(duration: float, style: str) -> str:
    style_guide = _STYLE_GUIDE.get(style, _STYLE_GUIDE["storytelling"])
    return f"""
You are an expert English-to-Khmer audiovisual translator and dubbing script supervisor.

Listen to the complete audio track. It is a continuous English voiceover, likely from a movie
recap or narrated video. Transcribe every spoken phrase, then translate it into spoken Khmer
(ភាសាខ្មែរ) for a Khmer voice actor.

VIDEO DURATION: {duration:.2f} seconds
DELIVERY STYLE: {style_guide}

RETURN FORMAT — return ONLY a JSON array, with no markdown, commentary, or wrapper object.
Each item must contain exactly these keys:
[
  {{"start": 0.0, "end": 4.2, "original": "English transcript", "khmer": "ការបកប្រែជាភាសាខ្មែរ"}}
]

TRANSCRIPTION AND TIMING RULES:
1. `start` and `end` are absolute seconds from the beginning of the audio, with decimals.
2. Segment on natural sentence or clause boundaries. Do not produce tiny fragments.
3. Timestamps must be chronological and must NOT overlap. The final `end` must not exceed
   {duration:.2f}.
4. `original` must be an accurate English transcript of what is spoken in that window. Do not
   paraphrase the English.
5. `khmer` must be natural spoken Khmer, written in Khmer script. Do not use romanization.
   Do not add a narrator introduction or invent content that is not in the source.
6. STRICT DURATION-AWARE TRANSLATION: the Khmer line will be synthesized and must finish within
   the same window. Normal Khmer TTS pace should read the translation in 85–100% of
   (end - start). Condense aggressively when English takes more time than Khmer; never produce a
   translation that obviously needs more time than its window.
7. Target roughly 2–8 seconds per segment. Split long sentences so the dubbing can breathe.
8. The dubbing engine may increase speed to a maximum of 1.35x, but do not rely on that. Prefer
   naturally concise Khmer.
9. Keep proper names, brands, and numbers recognizable. Use natural Khmer pronunciation rather
   than literal letter-by-letter transliteration.
10. Do not include sound-effect descriptions, speaker labels, brackets, or timestamp text inside
   `original` or `khmer`.

Before answering, review the whole JSON for gaps, overlaps, and lines that are too long to fit
their time windows. Return valid JSON only.
""".strip()


def _extract_json(text: str) -> Any:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = _JSON_ARRAY_RE.search(cleaned)
    if not match:
        raise GeminiError("Gemini returned an unreadable transcript. Please try again.")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise GeminiError("Gemini returned malformed JSON for the transcript.") from exc


def _normalise_segments(data: Any, duration: float) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        data = data.get("segments") or data.get("transcript") or data.get("items")
    if not isinstance(data, list):
        raise GeminiError("Gemini did not return a transcript list.")

    cleaned: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        original = " ".join(str(item.get("original", "")).split()).strip()
        khmer = " ".join(str(item.get("khmer", "")).split()).strip()
        if not khmer:
            continue
        try:
            start = float(item.get("start"))
            end = float(item.get("end"))
        except (TypeError, ValueError):
            continue
        if start >= duration or end <= 0:
            continue

        start = max(0.0, min(start, max(0.0, duration - 0.2)))
        end = max(start + 0.2, min(end, duration))

        # Keep the timeline non-overlapping. Timestamp inaccuracies from the model are
        # nudged forward rather than allowed to create impossible dubbing windows.
        if cleaned and start < cleaned[-1]["end"]:
            start = min(cleaned[-1]["end"], max(0.0, duration - 0.2))
            end = max(start + 0.25, min(end, duration))
        if end <= start + 0.15:
            continue
        if end > duration:
            end = duration
        if end <= start + 0.15:
            continue

        cleaned.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "original": original,
                "khmer": khmer,
                "speed": 1.0,
            }
        )

    if not cleaned:
        raise GeminiError(
            "No usable speech was found in this video. Check that the file contains an English voiceover."
        )

    if len(cleaned) > 1000:
        cleaned = cleaned[:1000]
    for index, segment in enumerate(cleaned, start=1):
        segment["id"] = index
    return cleaned


def _wait_for_file(client: genai.Client, uploaded: Any, timeout_seconds: int = 300) -> Any:
    deadline = time.monotonic() + timeout_seconds
    while True:
        state = getattr(uploaded, "state", None)
        state_name = getattr(state, "name", str(state)).upper()
        if "ACTIVE" in state_name or state_name in {"2", "STATE_ACTIVE"}:
            return uploaded
        if "FAILED" in state_name:
            raise GeminiError("Gemini could not process the uploaded audio file.")
        if time.monotonic() > deadline:
            raise GeminiError("Timed out while Gemini was processing the uploaded audio.")
        time.sleep(2)
        uploaded = client.files.get(name=uploaded.name)


def transcribe_and_translate(
    audio_path: Path,
    api_key: str,
    duration: float,
    style: str,
) -> list[dict[str, Any]]:
    if not api_key or not api_key.strip():
        raise GeminiError("A Gemini API key is required.")

    client = genai.Client(api_key=api_key.strip())
    uploaded = None
    try:
        uploaded = client.files.upload(file=str(audio_path))
        uploaded = _wait_for_file(client, uploaded)

        config = types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=_response_schema(),
            max_output_tokens=65535,
        )

        last_error: Exception | None = None
        response = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[uploaded, _build_prompt(duration, style)],
                    config=config,
                )
                break
            except Exception as exc:  # SDK raises several transport/API error types
                last_error = exc
                if attempt < 2:
                    logger.warning("Gemini generation attempt %s failed: %s", attempt + 1, exc)
                    time.sleep(2 * (attempt + 1))
        if response is None:
            raise GeminiError(f"Gemini request failed: {last_error}")

        text = getattr(response, "text", None)
        if not text:
            raise GeminiError("Gemini returned an empty response. Your API key may not have access to this model.")
        payload = _extract_json(text)
        return _normalise_segments(payload, duration)
    except GeminiError:
        raise
    except Exception as exc:
        message = str(exc)
        if "API key" in message or "API_KEY" in message or "PERMISSION_DENIED" in message or "401" in message:
            raise GeminiError("Gemini rejected the API key. Check that the key is valid and has Gemini API access.") from exc
        if "429" in message or "RESOURCE_EXHAUSTED" in message:
            raise GeminiError("Gemini rate limit reached. Wait a moment and try again.") from exc
        logger.exception("Gemini request failed")
        raise GeminiError(f"Gemini request failed: {message[:500]}") from exc
    finally:
        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                logger.debug("Could not delete Gemini upload", exc_info=True)
