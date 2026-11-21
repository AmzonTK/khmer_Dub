import {
  AlertCircle,
  Captions,
  Check,
  Languages,
  Loader2,
  Mic,
  Volume2,
} from 'lucide-react';

const STEPS = [
  {
    number: 1,
    title: 'Extract audio',
    detail: 'FFmpeg · original_audio.mp3',
    icon: Volume2,
  },
  {
    number: 2,
    title: 'Transcribe & translate',
    detail: 'Gemini 2.5 Flash · duration-aware Khmer',
    icon: Languages,
  },
  {
    number: 3,
    title: 'Khmer TTS & sync',
    detail: 'Edge TTS · atempo up to 1.35×',
    icon: Mic,
  },
  {
    number: 4,
    title: 'Duck, mix & render',
    detail: '12% music bed · subtitles · MP4',
    icon: Captions,
  },
];

function statusFor(stepNumber, job) {
  if (!job) return 'idle';
  if (job.status === 'completed') return 'done';
  if (job.status === 'failed') {
    if (stepNumber < job.step) return 'done';
    if (stepNumber === job.step) return 'failed';
    return 'idle';
  }
  if (stepNumber < job.step) return 'done';
  if (stepNumber === job.step) return 'active';
  return 'idle';
}

const STATUS_META = {
  queued: { label: 'Queued', tone: 'text-slate-300 border-white/10 bg-white/5' },
  processing: { label: 'Rendering', tone: 'text-gold-300 border-gold-400/20 bg-gold-400/10' },
  completed: { label: 'Ready', tone: 'text-emerald-300 border-emerald-400/20 bg-emerald-400/10' },
  failed: { label: 'Failed', tone: 'text-rose-300 border-rose-400/20 bg-rose-400/10' },
};

export default function PipelineProgress({ job }) {
  const progress = job?.progress || 0;
  const status = job?.status || 'idle';
  const meta = STATUS_META[status] || { label: 'Standby', tone: 'text-slate-400 border-white/10 bg-white/5' };

  return (
    <section id="pipeline" className="panel overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-4 px-5 pt-5 sm:px-6">
        <div>
          <p className="eyebrow">Render pipeline</p>
          <h2 className="mt-1 text-lg font-bold tracking-tight text-white">
            {job?.status === 'completed'
              ? 'Your Khmer dub is ready'
              : job?.status === 'failed'
                ? 'Render stopped'
                : job
                  ? 'Building your Khmer dub'
                  : 'Ready when you are'}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {job && (
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ${meta.tone}`}
            >
              {job.status === 'processing' && (
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
              )}
              {meta.label}
            </span>
          )}
          <span className="text-2xl font-black tabular-nums tracking-tight text-white">
            {progress}
            <span className="ml-0.5 text-sm font-semibold text-slate-500">%</span>
          </span>
        </div>
      </div>

      <div className="px-5 pt-4 sm:px-6">
        <div className="relative h-2 overflow-hidden rounded-full bg-white/[0.06]">
          <div
            className={`absolute inset-y-0 left-0 rounded-full transition-[width] duration-700 ease-out ${
              job?.status === 'failed'
                ? 'bg-gradient-to-r from-rose-500 to-rose-400'
                : 'bg-gradient-to-r from-gold-500 via-gold-400 to-gold-300'
            }`}
            style={{ width: `${Math.max(progress, job ? 3 : 0)}%` }}
          >
            {job?.status === 'processing' && (
              <span className="absolute inset-0 animate-pulse bg-gradient-to-r from-transparent via-white/40 to-transparent" />
            )}
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between gap-4 text-[11px]">
          <p className={`truncate ${job?.status === 'failed' ? 'text-rose-300' : 'text-slate-400'}`}>
            {job?.message || 'Upload a video and choose a voice to begin.'}
          </p>
          {job?.duration ? (
            <span className="shrink-0 font-mono text-[10px] text-slate-500">
              {Math.round(job.duration)}s source
            </span>
          ) : null}
        </div>
        {job?.reference?.status === 'ready' && (
          <div className="mt-2 flex items-center gap-1.5 text-[10px] text-slate-500">
            <Volume2 className="h-3 w-3 shrink-0 text-gold-400" />
            <span className="truncate">
              Reference voice:{' '}
              {job.reference.source === 'uploaded'
                ? 'custom upload'
                : `auto-extracted (${job.reference.isolation || 'vocals'})`}
              {job.reference.duration ? ` · ${job.reference.duration}s` : ''}
              {job.reference.cloned_clips ? ` · ${job.reference.cloned_clips} clips cloned` : ''}
            </span>
          </div>
        )}
      </div>

      <div className="grid gap-2 px-5 py-5 sm:grid-cols-2 sm:px-6">
        {STEPS.map((step) => {
          const state = statusFor(step.number, job);
          const Icon = step.icon;
          const detail =
            step.number === 3 && job?.settings?.voice_clone
              ? 'Edge TTS → Seed-VC voice clone'
              : step.detail;
          return (
            <div
              key={step.number}
              className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 transition ${
                state === 'active'
                  ? 'border-gold-400/30 bg-gold-400/[0.07]'
                  : state === 'done'
                    ? 'border-emerald-400/10 bg-emerald-400/[0.025]'
                    : state === 'failed'
                      ? 'border-rose-400/25 bg-rose-400/[0.06]'
                      : 'border-white/[0.06] bg-black/10'
              }`}
            >
              <span
                className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg border ${
                  state === 'active'
                    ? 'border-gold-400/30 bg-gold-400/15 text-gold-300'
                    : state === 'done'
                      ? 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300'
                      : state === 'failed'
                        ? 'border-rose-400/20 bg-rose-400/10 text-rose-300'
                        : 'border-white/[0.07] bg-white/[0.03] text-slate-600'
                }`}
              >
                {state === 'done' ? (
                  <Check className="h-4 w-4" strokeWidth={2.5} />
                ) : state === 'active' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : state === 'failed' ? (
                  <AlertCircle className="h-4 w-4" />
                ) : (
                  <Icon className="h-4 w-4" />
                )}
              </span>
              <div className="min-w-0">
                <p
                  className={`text-[11px] font-bold ${
                    state === 'idle' ? 'text-slate-500' : 'text-slate-100'
                  }`}
                >
                  {step.number}. {step.title}
                </p>
                <p className="truncate text-[9px] text-slate-500">{detail}</p>
              </div>
            </div>
          );
        })}
      </div>

      {job?.status === 'failed' && job.error && (
        <div className="mx-5 mb-5 flex gap-2.5 rounded-xl border border-rose-400/20 bg-rose-400/[0.07] px-3.5 py-3 text-[11px] leading-relaxed text-rose-200 sm:mx-6">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{job.error}</span>
        </div>
      )}

      {job?.warnings?.length > 0 && job.status === 'completed' && (
        <div className="mx-5 mb-5 rounded-xl border border-amber-400/15 bg-amber-400/[0.05] px-3.5 py-3 text-[10px] leading-relaxed text-amber-200/80 sm:mx-6">
          {job.warnings[0]}
          {job.warnings.length > 1 ? ` (+${job.warnings.length - 1} more notes)` : ''}
        </div>
      )}
    </section>
  );
}
