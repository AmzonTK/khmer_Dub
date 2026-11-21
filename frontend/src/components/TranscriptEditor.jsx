import {
  AlertCircle,
  Clock3,
  Gauge,
  Languages,
  Loader2,
  PencilLine,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { formatSeconds } from '../lib/format';

function updateAt(items, index, patch) {
  return items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item));
}

export default function TranscriptEditor({
  transcript,
  setTranscript,
  onRerender,
  isBusy,
  canRerender,
  error,
}) {
  const hasRows = transcript.length > 0;
  const invalid = transcript.some((segment, index) => {
    const start = Number(segment.start);
    const end = Number(segment.end);
    const speed = Number(segment.speed);
    const previous = transcript[index - 1];
    const overlaps = index > 0 && previous && start < Number(previous.end) - 0.01;
    return (
      !Number.isFinite(start)
      || !Number.isFinite(end)
      || !Number.isFinite(speed)
      || start < 0
      || end <= start
      || speed < 1
      || speed > 1.35
      || !String(segment.khmer || '').trim()
      || overlaps
    );
  });

  return (
    <section id="transcript" className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/[0.07] px-5 py-4 sm:px-6">
        <div>
          <div className="flex items-center gap-2">
            <p className="eyebrow">Dubbing script</p>
            {hasRows && (
              <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[9px] font-semibold tabular-nums text-slate-400">
                {transcript.length} segments
              </span>
            )}
          </div>
          <h2 className="mt-1 flex items-center gap-2 text-lg font-bold tracking-tight text-white">
            <PencilLine className="h-4 w-4 text-gold-400" />
            Editable transcript
          </h2>
        </div>

        <button
          type="button"
          onClick={onRerender}
          disabled={!hasRows || isBusy || !canRerender || invalid}
          className="btn-gold px-4 py-2.5 text-xs"
        >
          {isBusy ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Re-rendering…
            </>
          ) : (
            <>
              <RefreshCw className="h-3.5 w-3.5" />
              Re-render Khmer dub
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="mx-5 mt-4 flex items-start gap-2 rounded-xl border border-rose-400/20 bg-rose-400/[0.07] px-3.5 py-2.5 text-[11px] leading-relaxed text-rose-200 sm:mx-6">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {error}
        </div>
      )}

      {!hasRows ? (
        <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
          <span className="grid h-12 w-12 place-items-center rounded-2xl border border-white/10 bg-white/[0.04] text-slate-500">
            <Languages className="h-5 w-5" />
          </span>
          <h3 className="mt-4 text-sm font-semibold text-slate-300">Your bilingual script will appear here</h3>
          <p className="mt-1.5 max-w-sm text-[11px] leading-relaxed text-slate-500">
            After Gemini finishes transcribing, every timed phrase becomes editable. Adjust the Khmer
            wording, timestamps, or playback speed, then re-render without re-uploading.
          </p>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1020px] border-collapse text-left">
              <thead>
                <tr className="border-b border-white/[0.07] bg-black/20 text-[9px] font-bold uppercase tracking-[0.16em] text-slate-500">
                  <th className="w-[58px] px-4 py-3 text-center">#</th>
                  <th className="w-[190px] px-3 py-3">
                    <span className="flex items-center gap-1.5">
                      <Clock3 className="h-3 w-3" />
                      Start – End
                    </span>
                  </th>
                  <th className="px-3 py-3">Original English</th>
                  <th className="px-3 py-3">
                    <span className="flex items-center gap-1.5 text-gold-300/80">
                      <Languages className="h-3 w-3" />
                      Khmer translation
                    </span>
                  </th>
                  <th className="w-[104px] px-3 py-3">
                    <span className="flex items-center gap-1.5">
                      <Gauge className="h-3 w-3" />
                      Speed
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {transcript.map((segment, index) => {
                  const start = Number(segment.start);
                  const end = Number(segment.end);
                  const previous = transcript[index - 1];
                  const overlaps = index > 0 && previous && start < Number(previous.end) - 0.01;
                  const rowIssue = !String(segment.khmer || '').trim() || end <= start || overlaps;
                  return (
                    <tr
                      key={segment.id ?? index}
                      className="border-b border-white/[0.055] align-top transition hover:bg-white/[0.018]"
                    >
                      <td className="px-4 py-4 text-center">
                        <span className="inline-grid h-6 w-6 place-items-center rounded-md border border-white/[0.07] bg-white/[0.03] font-mono text-[9px] text-slate-500">
                          {String(index + 1).padStart(2, '0')}
                        </span>
                      </td>

                      <td className="px-3 py-3.5">
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={segment.start}
                            onChange={(event) =>
                              setTranscript((current) =>
                                updateAt(current, index, { start: event.target.value }),
                              )
                            }
                            aria-label={`Segment ${index + 1} start time`}
                            className="w-[64px] rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 font-mono text-[10px] text-slate-200 outline-none transition focus:border-gold-400/50 focus:ring-2 focus:ring-gold-400/10"
                          />
                          <span className="text-slate-600">–</span>
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={segment.end}
                            onChange={(event) =>
                              setTranscript((current) =>
                                updateAt(current, index, { end: event.target.value }),
                              )
                            }
                            aria-label={`Segment ${index + 1} end time`}
                            className="w-[64px] rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 font-mono text-[10px] text-slate-200 outline-none transition focus:border-gold-400/50 focus:ring-2 focus:ring-gold-400/10"
                          />
                        </div>
                        <p className="mt-1.5 pl-0.5 font-mono text-[9px] text-slate-600">
                          {end > start ? `${formatSeconds(end - start)}s window` : 'invalid window'}
                        </p>
                      </td>

                      <td className="px-3 py-3.5">
                        <textarea
                          rows={2}
                          value={segment.original}
                          onChange={(event) =>
                            setTranscript((current) =>
                              updateAt(current, index, { original: event.target.value }),
                            )
                          }
                          className="min-h-[62px] w-full resize-y rounded-lg border border-transparent bg-transparent px-2 py-1.5 text-[11px] leading-relaxed text-slate-400 outline-none transition hover:border-white/10 hover:bg-white/[0.02] focus:border-white/15 focus:bg-black/20 focus:text-slate-200"
                          aria-label={`Segment ${index + 1} original English`}
                        />
                      </td>

                      <td className="px-3 py-3.5">
                        <textarea
                          rows={2}
                          value={segment.khmer}
                          onChange={(event) =>
                            setTranscript((current) =>
                              updateAt(current, index, { khmer: event.target.value }),
                            )
                          }
                          className={`khmer min-h-[62px] w-full resize-y rounded-lg border bg-black/20 px-2.5 py-2 text-[14px] leading-[1.8] outline-none transition focus:ring-2 focus:ring-gold-400/10 ${
                            rowIssue
                              ? 'border-rose-400/30 text-rose-100 focus:border-rose-400/50'
                              : 'border-white/[0.07] text-slate-100 focus:border-gold-400/40'
                          }`}
                          aria-label={`Segment ${index + 1} Khmer translation`}
                          spellCheck={false}
                        />
                      </td>

                      <td className="px-3 py-3.5">
                        <div className="flex items-center gap-1.5">
                          <input
                            type="number"
                            min="1"
                            max="1.35"
                            step="0.01"
                            value={segment.speed}
                            onChange={(event) =>
                              setTranscript((current) =>
                                updateAt(current, index, { speed: event.target.value }),
                              )
                            }
                            onBlur={(event) => {
                              const raw = Number(event.target.value);
                              const clamped = Number.isFinite(raw)
                                ? Math.min(1.35, Math.max(1, raw))
                                : 1;
                              setTranscript((current) =>
                                updateAt(current, index, { speed: clamped }),
                              );
                            }}
                            aria-label={`Segment ${index + 1} speed`}
                            className="w-[62px] rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 font-mono text-[10px] text-gold-300 outline-none transition focus:border-gold-400/50 focus:ring-2 focus:ring-gold-400/10"
                          />
                          <span className="font-mono text-[9px] text-slate-600">×</span>
                        </div>
                        <span className="mt-1.5 block text-[8px] font-semibold uppercase tracking-wider text-slate-600">
                          {Number(segment.speed) > 1.001 ? 'fitted' : 'natural'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.07] px-5 py-3.5 sm:px-6">
            <p className="flex items-start gap-2 text-[10px] leading-relaxed text-slate-500">
              <Sparkles className="mt-0.5 h-3 w-3 shrink-0 text-gold-400/70" />
              <span>
                Speed is auto-fitted against the next phrase start. Re-render regenerates every Khmer
                voice clip, mix, subtitles, and the final MP4.
              </span>
            </p>
            {invalid && (
              <span className="flex items-center gap-1.5 text-[10px] font-semibold text-rose-300">
                <AlertCircle className="h-3 w-3" />
                Fix highlighted timing or Khmer text
              </span>
            )}
          </div>
        </>
      )}
    </section>
  );
}
