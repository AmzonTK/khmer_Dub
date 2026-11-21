# KhmerDub Studio

English voiceover in. Naturally synced Khmer narration out.

A full-stack AI dubbing workspace for **English movie recaps and voiceover videos → Khmer speech (ភាសាខ្មែរ)**. The app transcribes with Gemini, produces a duration-aware Khmer dubbing script, synthesizes both available Khmer Edge neural voices, speed-fits each phrase to the next phrase start, ducks the original audio bed to 12%, and optionally burns Khmer subtitles with a black background.

![stack](https://img.shields.io/badge/React_18-Tailwind-0b0e14) ![stack](https://img.shields.io/badge/FastAPI-Python_3.10+-0b0e14) ![stack](https://img.shields.io/badge/FFmpeg-required-0b0e14)

---

## Features

- **MP4 / MOV dropzone** with upload progress state and validation.
- **Gemini API key** input — used in memory and never written to disk.
- **Khmer voice selector**
  - `km-KH-SreymomNeural` — Female
  - `km-KH-PisethNeural` — Male
- **Style modes** — `Storytelling / Recap` or `Normal`.
- **Free AI Voice Clone mode** — optional custom reference voice upload (`.wav`/`.mp3`, 5–15s) or fully automatic extraction. If no upload is provided, the backend isolates the source vocals with **Demucs** (falling back to **Audio Separator**, then an FFmpeg center-channel/speech-bandpass filter) and slices a clean 10–12s segment from Gemini's active-speech timestamps into `reference_voice.wav`. **Seed-VC** then clones that timbre onto every Khmer Edge TTS clip.
- **Burned Khmer subtitles** with a 50% black box (`BorderStyle=4`, `BackColour=&H80000000`).
- **Live 4-step pipeline** with polling progress.
- **Side-by-side video preview** — original vs. Khmer-dubbed render.
- **Editable timed transcript** — start/end, original English, Khmer translation, speed.
- **Re-render** without re-uploading or re-running Gemini.
- **MP4 and SRT downloads.**
- Bundled **Kantumruy Pro** font so Khmer subtitle burn-in works out of the box.

---

## Pipeline

1. **Extract audio**
   `ffmpeg` creates `original_audio.mp3` from the uploaded video.

2. **Transcribe + translate**
   Audio is uploaded to the Gemini Files API and sent to `gemini-2.5-flash` with a strict
   JSON schema:
   ```json
   [{"start": 0.0, "end": 4.2, "original": "...", "khmer": "..."}]
   ```
   The prompt enforces concise, duration-aware Khmer that fits each time window.

3. **Khmer TTS + dynamic speed sync**
   `edge-tts` generates a clip for every segment. For each clip:
   - `available_window = next_start - current_start`
   - if `tts_duration > available_window`, FFmpeg applies `atempo`
   - speed is clamped to **1.35×**
   - every fitted clip is overlaid onto a silent master at its exact `start` timestamp.

3b. **Free AI Voice Clone (optional)**
   - **Reference voice** — if the client uploaded one, it is loudness-normalised into
     `reference_voice.wav`. Otherwise the backend:
     1. isolates vocals with `demucs` (`--two-stems=vocals`), then `audio-separator`,
        then an FFmpeg fallback (`pan` mid-channel + high/low-pass + denoise + presence EQ);
     2. scores 11-second candidate windows from Gemini's `start`/`end` speech timestamps
        and picks the densest active-speech window;
     3. trims silence, applies fades, and writes a mono 44.1 kHz `reference_voice.wav`.
   - **Seed-VC** converts every fitted Edge TTS clip with that reference (Gradio Space via
     `gradio_client`, or a local checkout with `SEEDVC_LOCAL_DIR`), then re-times the output
     to the original clip window. If cloning fails, the Edge TTS clips are used and the job
     reports a warning instead of failing.

4. **Ducking + final render**
   The original audio is reduced to 12%, narration boosted to 1.3×, then mixed:
   ```
   [0:a]volume=0.12[bg];[1:a]volume=1.3[fg];[bg][fg]amix=inputs=2:duration=first[aout]
   ```
   If enabled, the SRT is burned using:
   ```
   FontName=Kantumruy Pro,BorderStyle=4,BackColour=&H80000000
   ```
   The final file is a browser-friendly H.264/AAC MP4.

---

## Requirements (Windows)

- Windows 10/11 with PowerShell
- **Python 3.10–3.12** (Python 3.12 recommended)
- **Node.js 20+** and npm
- **FFmpeg + FFprobe** on `PATH`
- A **Gemini API key** from <https://aistudio.google.com/app/apikey>
- Internet access for Gemini and Edge TTS

### Install FFmpeg (winget)

```powershell
winget install --id Gyan.FFmpeg -e
```

Close and reopen PowerShell, then verify:

```powershell
ffmpeg -version
ffprobe -version
```

> If `ffmpeg` is not recognized, add the FFmpeg `bin` folder to your user `PATH`.

---

## Windows local setup

### Terminal 1 — backend

```powershell
cd "C:\Users\YOUR_NAME\Desktop\khmer-dub\backend"

# Create and activate a virtual environment
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# If PowerShell blocks activation, allow it for this terminal only:
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

python -m pip install --upgrade pip
pip install -r requirements.txt

# Optional: better vocal isolation for auto-extracted reference voices.
# Without this the backend uses the FFmpeg speech-band fallback.
pip install -r requirements-voice-clone.txt

uvicorn app.main:app --reload --port 8000
```

The API is now at:

- <http://127.0.0.1:8000>
- Swagger docs: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/api/health>

### Terminal 2 — frontend

```powershell
cd "C:\Users\YOUR_NAME\Desktop\khmer-dub\frontend"
npm install
npm run dev
```

Open **<http://localhost:5173>**.

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`, so both services need to be
running.

### Production frontend build

```powershell
cd frontend
$env:VITE_API_BASE_URL="https://your-api.example.com"
npm run build
```

The build output is in `frontend/dist`. The API server needs to be reachable at that URL and
that origin must be listed in `ALLOWED_ORIGINS` on the backend.

---

## Getting a Gemini API key

1. Open <https://aistudio.google.com/app/apikey>.
2. Create an API key.
3. Paste it into the app's **Gemini API key** field.

The key is only held in the backend process for the initial transcription request. It is not
included in `job.json`, logs, or responses.

---

## Usage

1. Drop an `.mp4` or `.mov` file.
2. Paste the Gemini API key.
3. Pick Sreymom (female) or Piseth (male) — used as the Khmer performance/fallback voice.
4. Pick `Storytelling / Recap` or `Normal`.
5. Choose **Standard Khmer TTS** or **Free AI Voice Clone**:
   - Standard uses the Edge neural voice directly.
   - Clone keeps the original speaker's timbre via Seed-VC.
   - Optionally upload **Upload Custom Reference Voice (.wav/.mp3, 5-15s)**.
     Leave it empty to auto-extract a clean 10–12s vocal segment from the video.
6. Choose whether to burn Khmer subtitles.
7. Click **Start Khmer dubbing**.
8. Watch the four-step render progress.
9. Compare the original and Khmer previews.
10. Edit any timed line or speed in the transcript table.
11. Click **Re-render Khmer dub**, then download the `.mp4` and `.srt`.

> The first clone render can take several minutes: Seed-VC processes one clip at a time
> (two in parallel by default) through the public Space. Set `SEEDVC_CONCURRENCY=1` on
> slow connections or run a local Seed-VC checkout with `SEEDVC_LOCAL_DIR`.

> Gemini's timestamps are an AI estimate. Review the transcript table for timing quality on
> longer videos. The backend rejects overlapping segments and enforces the 1.35× speed ceiling.

---

## Project layout

```text
khmer-dub/
├── backend/
│   ├── app/
│   │   ├── config.py            # env, voices, limits, FFmpeg/font paths
│   │   ├── main.py              # FastAPI routes, uploads, downloads
│   │   ├── models.py            # Pydantic transcript/re-render validation
│   │   ├── store.py             # disk-persisted job state + client snapshots
│   │   ├── pipeline.py          # 4-step orchestration
│   │   ├── gemini_service.py    # Gemini Files API + structured JSON translation
│   │   ├── tts_service.py       # edge-tts generation + sync calculations
│   │   ├── voice_clone.py       # vocal isolation, reference slicing, Seed-VC cloning
│   │   └── media.py             # FFmpeg extraction, SRT, ducking, render
│   ├── assets/fonts/            # bundled Kantumruy Pro + OFL license
│   ├── storage/jobs/            # per-job working files (runtime)
│   ├── requirements.txt
│   ├── requirements-voice-clone.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/          # upload, progress, preview, transcript editor
│   │   ├── lib/api.js           # fetch client + voice/style constants
│   │   └── App.jsx
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.js
└── README.md
```

Each job is stored at:

```text
backend/storage/jobs/<job-id>/
├── source.mp4 / source.mov
├── original_audio.mp3
├── custom_reference.wav         # only when uploaded
├── stems/                       # isolated vocals (Demucs / Audio Separator / FFmpeg)
├── reference_voice.wav          # normalised 10–12s Seed-VC reference
├── tts/segment_001.mp3...
├── fitted/segment_001.wav...
├── seedvc/segment_001.wav...    # raw Seed-VC output
├── cloned/segment_001.wav...    # re-timed cloned clips
├── khmer_voice.wav
├── mixed_audio.wav
├── khmer.srt
├── dubbed.mp4
└── job.json
```

Completed jobs remain on disk. The **active render queue is in-process**, so restarting Uvicorn
during an active job will mark that job as failed at next startup; completed outputs remain
downloadable.

---

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | FFmpeg/model/voice health |
| `POST` | `/api/jobs` | Upload video + start pipeline (`multipart/form-data`) |
| `GET` | `/api/jobs/{id}` | Poll status, transcript, media URLs |
| `POST` | `/api/jobs/{id}/rerender` | Re-run TTS/render from edited segments |
| `GET` | `/api/jobs/{id}/download/video` | Download MP4 |
| `GET` | `/api/jobs/{id}/download/srt` | Download SRT |
| `GET` | `/api/jobs/{id}/download/reference` | Download the prepared reference voice |
| `GET` | `/api/jobs/{id}/media/video` | Inline video for preview |
| `GET` | `/api/jobs/{id}/media/reference` | Inline reference voice (audio preview) |
| `GET` | `/api/jobs/{id}/subtitles` | Inline SRT |

Initial job form fields:

```text
video=@recap.mp4
api_key=...
voice=km-KH-SreymomNeural
style=storytelling
burn_subtitles=true
voice_clone=true
# optional; omit to auto-extract from the video
reference_voice=@my-voice.wav
```

Re-render payload:

```json
{
  "segments": [
    {
      "start": 0.0,
      "end": 3.8,
      "original": "The city was never the same.",
      "khmer": "ទីក្រុងនេះមិនដែលដូចមុនទៀតទេ។",
      "speed": 1.0
    }
  ],
  "voice": "km-KH-PisethNeural",
  "burn_subtitles": true,
  "voice_clone": true
}
```

---

## Configuration

Copy `backend/.env.example` to `backend/.env` if you want to override defaults.

| Variable | Default | Notes |
| --- | --- | --- |
| `ALLOWED_ORIGINS` | localhost dev origins | Comma-separated CORS origins |
| `MAX_UPLOAD_MB` | `500` | Upload ceiling |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Must support audio + structured output |
| `MAX_ATEMPO` | `1.35` | Sync speed ceiling |
| `EDGE_TTS_CONCURRENCY` | `2` | Parallel TTS connections |
| `EDGE_TTS_ATTEMPTS` | `6` | Retries per clip for transient `NoAudioReceived` |
| `EDGE_TTS_RETRY_DELAY` | `1.2` | Base exponential backoff (seconds) |
| `SUBTITLE_FONT` | `Kantumruy Pro` | Bundled font |
| `SUBTITLE_STYLE` | `FontName=Kantumruy Pro,...` | libass style |
| `STORAGE_DIR` | `backend/storage` | Job workspace |
| `VOICE_CLONE_ENABLED` | `1` | Show/allow Free AI Voice Clone |
| `REFERENCE_MIN_SECONDS` / `REFERENCE_MAX_SECONDS` | `5` / `15` | Custom reference upload window |
| `REFERENCE_WINDOW_SECONDS` | `11` | Auto-extracted reference length |
| `DEMUCS_MODEL` | `htdemucs` | Demucs model for vocal isolation |
| `AUDIO_SEPARATOR_MODEL` | `UVR-MDX-NET-Inst_HQ_3.onnx` | Audio Separator fallback model |
| `SEEDVC_SPACE` | `Plachta/Seed-VC` | Gradio Space used for cloning |
| `SEEDVC_API_NAME` | `/predict_1` | Space API endpoint (`/predict` for the newer UI) |
| `HF_TOKEN` | *(empty)* | Optional Hugging Face token for more ZeroGPU quota |
| `SEEDVC_LOCAL_DIR` | *(empty)* | Local Seed-VC checkout instead of the Space |
| `SEEDVC_DIFFUSION_STEPS` | `25` | Seed-VC quality/speed trade-off |
| `SEEDVC_CFG_RATE` | `0.7` | Seed-VC guidance rate |
| `SEEDVC_CONCURRENCY` | `2` | Parallel Seed-VC conversions |

---

## Troubleshooting

**`ffmpeg was not found` / backend health shows degraded**

Install FFmpeg with winget and restart the terminal. Confirm `ffmpeg -version` and
`ffprobe -version` both work.

**Edge TTS says “No audio was received”**

- Microsoft's endpoint intermittently rejects valid requests. The backend retries each clip
  (`EDGE_TTS_ATTEMPTS`, default 6, exponential backoff) and then re-runs only the failed clips
  sequentially before reporting an error.
- Lower `EDGE_TTS_CONCURRENCY` (default 2) if failures cluster on long videos.
- Ensure the machine can reach Microsoft's Edge TTS endpoint.
- The two supported voices are listed by `edge-tts --list-voices`.

**Gemini 429 / RESOURCE_EXHAUSTED**

The API key's rate limit was hit. Wait and retry, or use a key with a higher quota.

**Khmer subtitles are not showing**

The font is bundled at `backend/assets/fonts/KantumruyPro.ttf`. The render step copies it next
to the video and uses `fontsdir`. If you override `SUBTITLE_FONT`, make sure that font is
installed or present in `assets/fonts` as `.ttf`/`.otf`.

**Free AI Voice Clone falls back to the Edge voice**

- `gradio_client` is missing → `pip install gradio_client`.
- **`You have exceeded your ZeroGPU runs limit`** → the public Space limits anonymous GPU
  usage. Create a token at <https://huggingface.co/settings/tokens> and set `HF_TOKEN` in
  `backend/.env`, or run Seed-VC locally with `SEEDVC_LOCAL_DIR`.
- The public Seed-VC Space is asleep or rate-limited → retry, set `SEEDVC_CONCURRENCY=1`, or
  point `SEEDVC_LOCAL_DIR` at a local Seed-VC checkout.
- The source has music/no speech under the vocals → upload a clean 5–15s reference voice.
- Check `/api/health` → `voice_clone.available` and the job `warnings` array for details.

**Auto-extracted reference voice sounds watery or contains music**

Install Demucs for the cleanest separation:

```powershell
pip install -r requirements-voice-clone.txt
```

Without it the FFmpeg mid-channel/bandpass fallback is used, which cannot fully remove
centred music. A custom 5–15s reference upload always wins over auto-extraction.

**A re-render is rejected**

- Segments must be in chronological order.
- Segments cannot overlap.
- Segments cannot end after the source video.
- Speed must be between `1.0` and `1.35`.
- Khmer text cannot be empty.

**Original MOV preview does not play in the browser**

The source preview uses the browser's native decoder. Some MOV codecs (e.g. ProRes/HEVC) are
not browser-supported. The final Khmer render is always re-encoded to H.264/AAC MP4.

---

## Security and limitations

- Videos are stored under `backend/storage/jobs`; delete old jobs when no longer needed.
- The Gemini key is never persisted by this app, but the extracted audio is uploaded to
  Gemini and synthesized audio goes through Microsoft Edge TTS.
- **Free AI Voice Clone** sends the prepared `reference_voice.wav` and the Khmer TTS clips to
  the configured Seed-VC Gradio Space (default `Plachta/Seed-VC`) unless `SEEDVC_LOCAL_DIR`
  points at a local checkout. Vocal isolation and reference slicing always run locally.
- Ducking lowers the entire original track to 12%. It does not isolate music from the
  original English narrator; use a source with music/SFX-only underneath if you need a clean bed.
- If a phrase still overruns after the 1.35× ceiling, the app reports a timing warning rather
  than cutting the voice mid-word. Edit that line shorter and re-render.
- Job execution is local and in-process; there is no distributed task queue or authentication.
  Do not expose this development server directly to the public internet.

---

## Credits

- Khmer voices via [edge-tts](https://github.com/rany2/edge-tts)
- Translation/transcription via [Google Gemini](https://ai.google.dev/)
- Media processing via [FFmpeg](https://ffmpeg.org/)
- Icons via [Lucide](https://lucide.dev/)
- Kantumruy Pro font under the SIL Open Font License 1.1

