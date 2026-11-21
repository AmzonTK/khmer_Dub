import {
  Captions,
  Download,
  Film,
  Headphones,
  Loader2,
  Music2,
  Play,
  Volume2,
} from 'lucide-react';
import { resolveApiUrl, VOICES, withVersion } from '../lib/api';
import { formatDuration } from '../lib/format';

function Waveform({ active = false }) {
  const heights = [18, 34, 54, 26, 68, 44, 78, 38, 58, 24, 64, 42, 74, 32, 50, 20, 60, 36, 46, 22];
  return (
    <div className="flex h-16 items-center gap-[3px]">
      {heights.map((height, index) => (
        <span
          key={index}
          className={`wave-bar w-[3px] rounded-full ${
            active ? 'bg-gold-400/80' : 'bg-slate-700'
          } ${active ? 'animate-soft-pulse' : ''}`}
          style={{
            height: `${height}%`,
            animationDelay: `${index * 55}ms`,
          }}
        />
      ))}
    </div>
  );
}

function VideoPane({ label, accent, src, fallback }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/[0.08] bg-black/40">
      <div className="flex items-center justify-between border-b border-white/[0.07] px-3.5 py-2.5">
        <span className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-300">
          <span className={`h-1.5 w-1.5 rounded-full ${accent}`} />
          {label}
        </span>
        <span className="text-[9px] font-medium uppercase tracking-wider text-slate-600">
          {src ? 'Video' : 'Waiting'}
        </span>
      </div>
      <div className="video-shell relative aspect-video">
        {src ? (
          <video key={src} src={src} controls playsInline preload="metadata" className="h-full w-full object-contain" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            {fallback}
          </div>
        )}
      </div>
    </div>
  );
}

export default function PreviewPanel({ job, originalUrl }) {
  const isCompleted = job?.status === 'completed';
  const isProcessing = job?.status === 'processing' || job?.status === 'queued';
  const videoUrl = isCompleted && job?.media?.video
    ? withVersion(resolveApiUrl(job.media.video), job.version)
    : '';
  const originalSource = originalUrl
    || (job?.media?.original ? resolveApiUrl(job.media.original) : '');
  const voice = VOICES.find((item) => item.id === job?.settings?.voice);
  const srtUrl = job?.downloads?.srt ? resolveApiUrl(job.downloads.srt) : '';
  const mp4Url = job?.downloads?.video ? resolveApiUrl(job.downloads.video) : '';

  return (
    <section className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] px-5 py-4 sm:px-6">
        <div>
          <p className="eyebrow">Studio preview</p>
          <h2 className="mt-0.5 text-lg font-bold tracking-tight text-white">Original vs. Khmer dub</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <a
            href={mp4Url || undefined}
            download
            aria-disabled={!mp4Url}
            className={`btn-ghost ${!mp4Url ? 'pointer-events-none opacity-40' : ''}`}
          >
            <Download className="h-3.5 w-3.5" />
            MP4
          </a>
          <a
            href={srtUrl || undefined}
            download
            aria-disabled={!srtUrl}
            className={`btn-ghost ${!srtUrl ? 'pointer-events-none opacity-40' : ''}`}
          >
            <Download className="h-3.5 w-3.5" />
            SRT
          </a>
        </div>
      </div>

      <div className="grid gap-3 p-4 sm:grid-cols-2 sm:p-5">
        <VideoPane
          label="Original · English"
          accent="bg-sky-400"
          src={originalSource}
          fallback={
            <>
              <span className="grid h-11 w-11 place-items-center rounded-full border border-white/10 bg-white/[0.04] text-slate-600">
                <Film className="h-5 w-5" />
              </span>
              <p className="text-[11px] font-medium text-slate-600">Your source video appears here</p>
            </>
          }
        />

        <VideoPane
          label="Khmer dub · ខ្មែរ"
          accent="bg-gold-400"
          src={videoUrl}
          fallback={
            isProcessing ? (
              <>
                <div className="relative grid h-12 w-12 place-items-center rounded-full border border-gold-400/25 bg-gold-400/10 text-gold-300">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span className="absolute inset-0 animate-ping rounded-full border border-gold-400/10" />
                </div>
                <div className="px-6">
                  <p className="text-[11px] font-semibold text-slate-300">{job.message}</p>
                  <p className="mt-1 text-[9px] uppercase tracking-[0.18em] text-slate-600">
                    Step {Math.min(job.step || 1, 4)} of 4
                  </p>
                </div>
              </>
            ) : (
              <>
                <Waveform />
                <p className="max-w-[230px] text-[11px] leading-relaxed text-slate-500">
                  Your synced Khmer voiceover and rendered video will appear here.
                </p>
              </>
            )
          }
        />
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-white/[0.07] px-5 py-3.5 sm:px-6">
        <span className="chip">
          <Headphones className="h-3 w-3 text-gold-300" />
          {voice ? `${voice.shortName} · ${voice.gender}` : 'Khmer narrator'}
        </span>
        <span className="chip">
          <Music2 className="h-3 w-3 text-sky-300" />
          Music ducked to 12%
        </span>
        <span className="chip">
          <Volume2 className="h-3 w-3 text-emerald-300" />
          Voice boosted 1.3×
        </span>
        {job?.settings?.burn_subtitles && (
          <span className="chip">
            <Captions className="h-3 w-3 text-rose-300" />
            Burned KH subs
          </span>
        )}
        {isCompleted && job?.duration ? (
          <span className="ml-auto text-[10px] font-medium tabular-nums text-slate-500">
            {formatDuration(job.duration)} runtime
          </span>
        ) : (
          <span className="ml-auto flex items-center gap-1.5 text-[10px] text-slate-600">
            <Play className="h-3 w-3" />
            H.264 · AAC · MP4
          </span>
        )}
      </div>
    </section>
  );
}
