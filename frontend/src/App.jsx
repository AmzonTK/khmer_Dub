import { useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  Captions,
  Gauge,
  Languages,
  ShieldCheck,
  Sparkles,
  Wand2,
} from 'lucide-react';
import Header from './components/Header';
import PipelineProgress from './components/PipelineProgress';
import PreviewPanel from './components/PreviewPanel';
import TranscriptEditor from './components/TranscriptEditor';
import UploadPanel from './components/UploadPanel';
import { createJob, fetchJob, rerenderJob, VOICES } from './lib/api';

const BUSY_STATUSES = new Set(['queued', 'processing']);

function normalizedTranscript(segments = []) {
  return segments.map((segment, index) => ({
    id: segment.id ?? index + 1,
    start: segment.start,
    end: segment.end,
    original: segment.original || '',
    khmer: segment.khmer || '',
    speed: segment.speed ?? 1,
  }));
}

export default function App() {
  const [file, setFile] = useState(null);
  const [originalUrl, setOriginalUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [voice, setVoice] = useState(VOICES[0].id);
  const [style, setStyle] = useState('storytelling');
  const [burnSubtitles, setBurnSubtitles] = useState(true);
  const [voiceClone, setVoiceClone] = useState(false);
  const [referenceVoice, setReferenceVoice] = useState(null);

  const [job, setJob] = useState(null);
  const [transcript, setTranscript] = useState([]);
  const [isStarting, setIsStarting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [rerenderError, setRerenderError] = useState('');
  const [connectionError, setConnectionError] = useState('');
  const pollTimer = useRef(null);

  const isJobBusy = Boolean(job && BUSY_STATUSES.has(job.status));
  const canRerender = Boolean(job && !isJobBusy && transcript.length > 0);

  useEffect(() => {
    return () => {
      if (originalUrl) URL.revokeObjectURL(originalUrl);
    };
  }, [originalUrl]);

  useEffect(() => {
    if (job?.settings && typeof job.settings.voice_clone === 'boolean') {
      setVoiceClone(job.settings.voice_clone);
    }
  }, [job?.id, job?.settings?.voice_clone]);

  useEffect(() => {
    if (!job?.id || !job || !BUSY_STATUSES.has(job.status)) return undefined;

    let cancelled = false;
    const jobId = job.id;

    const poll = async () => {
      try {
        const next = await fetchJob(jobId);
        if (cancelled) return;
        setConnectionError('');
        setJob(next);

        if (next.status === 'completed' || next.status === 'failed') {
          if (next.transcript?.length) {
            setTranscript(normalizedTranscript(next.transcript));
          }
          if (next.status === 'failed' && next.error) {
            setRerenderError(next.transcript?.length ? next.error : '');
          }
          return;
        }
        pollTimer.current = setTimeout(poll, 1600);
      } catch (error) {
        if (cancelled) return;
        setConnectionError(error.message);
        pollTimer.current = setTimeout(poll, 3000);
      }
    };

    pollTimer.current = setTimeout(poll, 900);
    return () => {
      cancelled = true;
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [job?.id, job?.status]);

  const handleFileChange = (nextFile) => {
    setSubmitError('');
    setConnectionError('');
    if (!nextFile) {
      setFile(null);
      setOriginalUrl('');
      setJob(null);
      setTranscript([]);
      return;
    }

    const extension = nextFile.name.split('.').pop()?.toLowerCase();
    if (!['mp4', 'mov'].includes(extension)) {
      setSubmitError('Choose an .mp4 or .mov video file.');
      return;
    }

    setFile(nextFile);
    setOriginalUrl(URL.createObjectURL(nextFile));
    setJob(null);
    setTranscript([]);
    setRerenderError('');
  };

  const handleStart = async () => {
    setSubmitError('');
    setConnectionError('');
    setRerenderError('');

    if (!file) {
      setSubmitError('Choose an MP4 or MOV video first.');
      return;
    }
    if (!apiKey.trim()) {
      setSubmitError('Enter your Gemini API key.');
      return;
    }

    setIsStarting(true);
    try {
      const created = await createJob({
        file,
        apiKey: apiKey.trim(),
        voice,
        style,
        burnSubtitles,
        voiceClone,
        referenceFile: referenceVoice,
      });
      setJob(created);
      setTranscript([]);
    } catch (error) {
      setSubmitError(error.message);
    } finally {
      setIsStarting(false);
    }
  };

  const handleRerender = async () => {
    if (!job) return;
    setRerenderError('');
    setConnectionError('');
    try {
      const updated = await rerenderJob({
        jobId: job.id,
        segments: transcript,
        voice,
        burnSubtitles,
        voiceClone,
      });
      setJob(updated);
    } catch (error) {
      setRerenderError(error.message);
    }
  };

  return (
    <div className="relative min-h-screen overflow-x-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[620px] bg-grid" />
      <Header />

      <main className="relative mx-auto max-w-7xl px-4 pb-14 pt-10 sm:px-6 lg:px-8 lg:pt-14">
        <section className="mb-9 grid items-end gap-8 lg:grid-cols-[1fr_auto]">
          <div className="animate-fade-up">
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-gold-400/25 bg-gold-400/[0.08] px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-gold-300">
                <Sparkles className="h-3 w-3" />
                English → Khmer AI dubbing
              </span>
              <span className="khmer rounded-full border border-white/10 bg-white/[0.035] px-3 py-1.5 text-[11px] text-slate-400">
                ភាសាខ្មែរ
              </span>
            </div>
            <h1 className="max-w-3xl text-balance text-4xl font-extrabold leading-[1.02] tracking-[-0.04em] text-white sm:text-5xl lg:text-[58px]">
              English stories.
              <br />
              <span className="bg-gradient-to-r from-gold-300 via-gold-400 to-amber-600 bg-clip-text text-transparent">
                Khmer voices.
              </span>{' '}
              In sync.
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-relaxed text-slate-400 sm:text-[15px]">
              Turn English voiceover and movie-recap videos into naturally timed Khmer dubbing.
              Gemini writes a duration-aware script, Edge neural voices perform it, and FFmpeg keeps
              every phrase locked to the picture.
            </p>
          </div>

          <div className="animate-fade-up grid grid-cols-2 gap-2 sm:grid-cols-4 lg:max-w-[440px] lg:grid-cols-2">
            {[
              { icon: Languages, label: 'Gemini 2.5 Flash', hint: 'translate' },
              { icon: Wand2, label: 'Khmer neural TTS', hint: 'edge-tts' },
              { icon: Gauge, label: 'Dynamic 1.35×', hint: 'atempo sync' },
              { icon: Captions, label: 'Burned subtitles', hint: 'black box' },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-xl border border-white/[0.07] bg-white/[0.025] px-3 py-2.5"
              >
                <item.icon className="h-3.5 w-3.5 text-gold-400" />
                <p className="mt-2 text-[10px] font-bold text-slate-300">{item.label}</p>
                <p className="text-[8px] uppercase tracking-[0.14em] text-slate-600">{item.hint}</p>
              </div>
            ))}
          </div>
        </section>

        {connectionError && (
          <div className="mb-4 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-4 py-3 text-xs text-amber-200">
            Backend connection issue: {connectionError}. Retrying…
          </div>
        )}

        <div
          id="studio"
          className="grid items-start gap-5 lg:grid-cols-[minmax(340px,390px)_minmax(0,1fr)]"
        >
          <UploadPanel
            file={file}
            apiKey={apiKey}
            voice={voice}
            style={style}
            burnSubtitles={burnSubtitles}
            voiceClone={voiceClone}
            referenceVoice={referenceVoice}
            isStarting={isStarting}
            isJobBusy={isJobBusy}
            error={submitError}
            onFileChange={handleFileChange}
            onApiKeyChange={setApiKey}
            onVoiceChange={setVoice}
            onStyleChange={setStyle}
            onBurnSubtitlesChange={setBurnSubtitles}
            onVoiceCloneChange={(enabled) => {
              setVoiceClone(enabled);
              if (!enabled) setReferenceVoice(null);
            }}
            onReferenceVoiceChange={setReferenceVoice}
            onSubmit={handleStart}
          />

          <div className="min-w-0 space-y-5">
            <PipelineProgress job={job} />
            <PreviewPanel job={job} originalUrl={originalUrl} />
          </div>
        </div>

        <div className="mt-5">
          <TranscriptEditor
            transcript={transcript}
            setTranscript={setTranscript}
            onRerender={handleRerender}
            isBusy={isJobBusy || isStarting}
            canRerender={canRerender}
            error={rerenderError}
          />
        </div>

        <section className="mt-10 grid gap-3 border-t border-white/[0.07] pt-8 sm:grid-cols-3">
          {[
            {
              icon: Languages,
              title: 'Duration-aware writing',
              text: 'Gemini condenses each Khmer line to fit its exact source window — not a literal subtitle translation.',
            },
            {
              icon: Gauge,
              title: 'Next-phrase sync',
              text: 'Each TTS clip is measured against the next segment start. Only when needed, atempo speeds it up to 1.35×.',
            },
            {
              icon: ShieldCheck,
              title: 'Local-first workflow',
              text: 'Files stay on your machine. The Gemini key is used in-memory and is never persisted by the backend.',
            },
          ].map((item) => (
            <div key={item.title} className="flex gap-3 rounded-2xl p-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-white/[0.08] bg-white/[0.035] text-gold-400">
                <item.icon className="h-4 w-4" />
              </span>
              <div>
                <h3 className="text-xs font-bold text-slate-200">{item.title}</h3>
                <p className="mt-1 text-[10px] leading-relaxed text-slate-500">{item.text}</p>
              </div>
            </div>
          ))}
        </section>

        <footer className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.07] pt-6 text-[10px] text-slate-600">
          <span className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-gold-400" />
            KhmerDub Studio · React + FastAPI local pipeline
          </span>
          <span className="flex items-center gap-2">
            FFmpeg
            <ArrowRight className="h-3 w-3" />
            Gemini
            <ArrowRight className="h-3 w-3" />
            Edge TTS
            <ArrowRight className="h-3 w-3" />
            MP4
          </span>
        </footer>
      </main>
    </div>
  );
}
