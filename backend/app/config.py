from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", BASE_DIR / "storage")).resolve()
JOBS_DIR = STORAGE_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

APP_NAME = "KhmerDub Studio"
APP_VERSION = "1.0.0"

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
EDGE_TTS_CONCURRENCY = max(1, int(os.getenv("EDGE_TTS_CONCURRENCY", "2")))
EDGE_TTS_ATTEMPTS = max(1, int(os.getenv("EDGE_TTS_ATTEMPTS", "6")))
EDGE_TTS_RETRY_DELAY = max(0.2, float(os.getenv("EDGE_TTS_RETRY_DELAY", "1.2")))
EDGE_TTS_TIMEOUT = max(10, int(os.getenv("EDGE_TTS_TIMEOUT", "60")))
MAX_ATEMPO = float(os.getenv("MAX_ATEMPO", "1.35"))
MIN_ATEMPO = 1.0

SUBTITLE_FONT = os.getenv("SUBTITLE_FONT", "Kantumruy Pro")
SUBTITLE_STYLE = os.getenv(
    "SUBTITLE_STYLE",
    f"FontName={SUBTITLE_FONT},BorderStyle=4,BackColour=&H80000000,Outline=1,Shadow=0,MarginV=30",
)
FONT_DIR = BASE_DIR / "assets" / "fonts"

VOICES = {
    "km-KH-SreymomNeural": {
        "label": "Sreymom",
        "gender": "Female",
        "description": "Warm, expressive Khmer female narrator",
    },
    "km-KH-PisethNeural": {
        "label": "Piseth",
        "gender": "Male",
        "description": "Deep, cinematic Khmer male narrator",
    },
}

DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", DEFAULT_ORIGINS).split(",")
    if origin.strip()
]

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE_BIN = shutil.which("ffprobe") or "ffprobe"

# --- Free AI voice cloning (Seed-VC + vocal isolation) -------------------------

VOICE_CLONE_ENABLED = os.getenv("VOICE_CLONE_ENABLED", "1").lower() not in {"0", "false", "no", "off"}

# Custom reference upload constraints (the UI asks for 5–15 seconds).
REFERENCE_MIN_SECONDS = float(os.getenv("REFERENCE_MIN_SECONDS", "5"))
REFERENCE_MAX_SECONDS = float(os.getenv("REFERENCE_MAX_SECONDS", "15"))
REFERENCE_MIN_BYTES = 8 * 1024
REFERENCE_MAX_MB = int(os.getenv("REFERENCE_MAX_MB", "25"))
REFERENCE_MAX_BYTES = REFERENCE_MAX_MB * 1024 * 1024

# Auto-extraction: length of the clean vocal window sliced out of the source.
REFERENCE_WINDOW_SECONDS = float(os.getenv("REFERENCE_WINDOW_SECONDS", "11"))
REFERENCE_WINDOW_MIN_SECONDS = float(os.getenv("REFERENCE_WINDOW_MIN_SECONDS", "5"))
DEMUCS_MODEL = os.getenv("DEMUCS_MODEL", "htdemucs")
AUDIO_SEPARATOR_MODEL = os.getenv("AUDIO_SEPARATOR_MODEL", "UVR-MDX-NET-Inst_HQ_3.onnx")
VOCAL_ISOLATION_TIMEOUT = int(os.getenv("VOCAL_ISOLATION_TIMEOUT", "1800"))

# Seed-VC. Either a Gradio Space (default) or a local checkout (SEEDVC_LOCAL_DIR).
SEEDVC_SPACE = os.getenv("SEEDVC_SPACE", "Plachta/Seed-VC")
SEEDVC_API_NAME = os.getenv("SEEDVC_API_NAME", "/predict_1")
SEEDVC_LOCAL_DIR = os.getenv("SEEDVC_LOCAL_DIR", "")
SEEDVC_CHECKPOINT = os.getenv("SEEDVC_CHECKPOINT", "")
SEEDVC_DIFFUSION_STEPS = int(os.getenv("SEEDVC_DIFFUSION_STEPS", "25"))
SEEDVC_CFG_RATE = float(os.getenv("SEEDVC_CFG_RATE", "0.7"))
SEEDVC_CONCURRENCY = max(1, int(os.getenv("SEEDVC_CONCURRENCY", "2")))
SEEDVC_TIMEOUT = int(os.getenv("SEEDVC_TIMEOUT", "1800"))
SEEDVC_MAX_RETRIES = max(1, int(os.getenv("SEEDVC_MAX_RETRIES", "2")))
# Optional Hugging Face token. The public ZeroGPU Space gives more quota when
# authenticated; also required if the Space is rate-limited for anonymous calls.
HF_TOKEN = (
    os.getenv("HF_TOKEN")
    or os.getenv("HUGGINGFACE_TOKEN")
    or os.getenv("HF_API_TOKEN")
    or ""
)
