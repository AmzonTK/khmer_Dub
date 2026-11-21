export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export const VOICES = [
  {
    id: 'km-KH-SreymomNeural',
    shortName: 'Sreymom',
    gender: 'Female',
    description: 'Warm & dramatic narration',
  },
  {
    id: 'km-KH-PisethNeural',
    shortName: 'Piseth',
    gender: 'Male',
    description: 'Deep & cinematic delivery',
  },
];

export const STYLES = [
  {
    id: 'storytelling',
    label: 'Storytelling / Recap',
    hint: 'Cinematic Khmer narration',
  },
  {
    id: 'normal',
    label: 'Normal',
    hint: 'Clear & faithful translation',
  },
];

export function resolveApiUrl(path) {
  if (!path) return '';
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path}`;
}

export function withVersion(url, version) {
  if (!url) return '';
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}v=${encodeURIComponent(version || Date.now())}`;
}

async function parseResponse(response) {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    let message = payload?.detail || `Request failed (${response.status})`;
    if (Array.isArray(message)) {
      message = message.map((item) => item.msg || 'Invalid value').join(', ');
    }
    throw new Error(message);
  }
  return payload;
}

async function requestJson(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error(
      'Cannot reach the dubbing backend. Start FastAPI on port 8000, then try again. '
      + 'In a second terminal: cd backend; .\\.venv\\Scripts\\Activate.ps1; '
      + 'uvicorn app.main:app --reload --port 8000',
    );
  }
  return parseResponse(response);
}

export async function createJob({
  file,
  apiKey,
  voice,
  style,
  burnSubtitles,
  voiceClone = false,
  referenceFile = null,
}) {
  const form = new FormData();
  form.append('video', file);
  form.append('api_key', apiKey);
  form.append('voice', voice);
  form.append('style', style);
  form.append('burn_subtitles', String(burnSubtitles));
  form.append('voice_clone', String(Boolean(voiceClone) || Boolean(referenceFile)));
  if (referenceFile) {
    form.append('reference_voice', referenceFile);
  }

  return requestJson(`${API_BASE}/api/jobs`, {
    method: 'POST',
    body: form,
  });
}

export async function fetchJob(jobId) {
  return requestJson(`${API_BASE}/api/jobs/${jobId}`, {
    cache: 'no-store',
  });
}

export async function rerenderJob({ jobId, segments, voice, burnSubtitles, voiceClone = false }) {
  return requestJson(`${API_BASE}/api/jobs/${jobId}/rerender`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      segments: segments.map((segment) => ({
        start: Number(segment.start),
        end: Number(segment.end),
        original: segment.original,
        khmer: segment.khmer,
        speed: Number(segment.speed) || 1,
      })),
      voice,
      burn_subtitles: burnSubtitles,
      voice_clone: Boolean(voiceClone),
    }),
  });
}
