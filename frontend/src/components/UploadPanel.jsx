import { useRef, useState } from 'react';
import {
  ArrowRight,
  Captions,
  Check,
  Eye,
  EyeOff,
  FileAudio,
  FileVideo,
  KeyRound,
  Loader2,
  Mic,
  Sparkles,
  UploadCloud,
  Wand2,
  X,
} from 'lucide-react';
import { STYLES, VOICES } from '../lib/api';
import { formatBytes } from '../lib/format';

export default function UploadPanel({
  file,
  apiKey,
  voice,
  style,
  burnSubtitles,
  voiceClone,
  referenceVoice,
  isStarting,
  isJobBusy,
  error,
  onFileChange,
  onApiKeyChange,
  onVoiceChange,
  onStyleChange,
  onBurnSubtitlesChange,
  onVoiceCloneChange,
  onReferenceVoiceChange,
  onSubmit,
}) {
  const inputRef = useRef(null);
  const referenceInputRef = useRef(null);
  const [dragActive, setDragActive] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [referenceError, setReferenceError] = useState('');

  const pickFile = (nextFile) => {
    if (!nextFile) return;
    onFileChange(nextFile);
  };

  const pickReference = (nextFile) => {
    setReferenceError('');
    if (!nextFile) return;
    const extension = nextFile.name.split('.').pop()?.toLowerCase();
    if (!['wav', 'mp3'].includes(extension)) {
      setReferenceError('Choose a .wav or .mp3 reference voice.');
      return;
    }
    onReferenceVoiceChange(nextFile);
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setDragActive(false);
    pickFile(event.dataTransfer.files?.[0]);
  };

  const canSubmit = Boolean(file && apiKey.trim()) && !isStarting && !isJobBusy;

  return (
    <aside className="panel overflow-hidden">
      <div className="border-b border-white/[0.07] px-5 py-5 sm:px-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="eyebrow">New dub</p>
            <h2 className="mt-1 text-xl font-bold tracking-tight text-white">Source & voice</h2>
          </div>
          <span className="grid h-10 w-10 place-items-center rounded-xl border border-gold-400/20 bg-gold-400/10 text-gold-300">
            <Mic className="h-5 w-5" />
          </span>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-slate-500">
          English voiceover in. Naturally timed Khmer narration out.
        </p>
      </div>

      <form
        className="space-y-6 px-5 py-5 sm:px-6"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <div>
          <div className="label">
            <span>01 · Video file</span>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".mp4,.mov,video/mp4,video/quicktime"
            className="hidden"
            onChange={(event) => {
              pickFile(event.target.files?.[0]);
              event.target.value = '';
            }}
          />

          {file ? (
            <div className="flex items-center gap-3 rounded-2xl border border-gold-400/25 bg-gold-400/[0.06] p-3.5">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-gold-400/15 text-gold-300">
                <FileVideo className="h-5 w-5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-white">{file.name}</p>
                <p className="mt-0.5 text-[11px] text-slate-400">
                  {formatBytes(file.size)} · {file.name.split('.').pop()?.toUpperCase()}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  onFileChange(null);
                  if (inputRef.current) inputRef.current.value = '';
                }}
                className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition hover:bg-white/10 hover:text-white"
                aria-label="Remove video"
                disabled={isStarting || isJobBusy}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              onDragOver={(event) => {
                event.preventDefault();
                setDragActive(true);
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              className={`group flex w-full flex-col items-center justify-center rounded-2xl border border-dashed px-4 py-8 text-center transition ${
                dragActive
                  ? 'border-gold-400 bg-gold-400/10'
                  : 'border-white/15 bg-black/20 hover:border-gold-400/50 hover:bg-gold-400/[0.04]'
              }`}
            >
              <span className="grid h-11 w-11 place-items-center rounded-full border border-white/10 bg-white/[0.05] text-slate-300 transition group-hover:scale-105 group-hover:border-gold-400/30 group-hover:text-gold-300">
                <UploadCloud className="h-5 w-5" />
              </span>
              <span className="mt-3 text-sm font-semibold text-slate-200">Drop your video here</span>
              <span className="mt-1 text-[11px] text-slate-500">or click to browse · MP4 / MOV</span>
            </button>
          )}
        </div>

        <div>
          <label htmlFor="api-key" className="label">
            <KeyRound className="h-3.5 w-3.5 text-gold-400" />
            <span>02 · Gemini API key</span>
          </label>
          <div className="relative">
            <input
              id="api-key"
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(event) => onApiKeyChange(event.target.value)}
              placeholder="AIza…"
              autoComplete="off"
              spellCheck={false}
              className="field pr-11"
            />
            <button
              type="button"
              onClick={() => setShowKey((value) => !value)}
              className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-slate-500 transition hover:text-white"
              aria-label={showKey ? 'Hide API key' : 'Show API key'}
            >
              {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
            Used only for this transcription request and never written to disk.
          </p>
        </div>

        <div>
          <div className="label">
            <Mic className="h-3.5 w-3.5 text-gold-400" />
            <span>03 · Khmer voice</span>
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            {VOICES.map((option) => {
              const selected = voice === option.id;
              return (
                <button
                  type="button"
                  key={option.id}
                  onClick={() => onVoiceChange(option.id)}
                  aria-pressed={selected}
                  className={`relative rounded-2xl border p-3 text-left transition ${
                    selected
                      ? 'border-gold-400/50 bg-gold-400/[0.08]'
                      : 'border-white/10 bg-black/20 hover:border-white/20'
                  }`}
                >
                  {selected && (
                    <span className="absolute right-2.5 top-2.5 grid h-4 w-4 place-items-center rounded-full bg-gold-400 text-ink-950">
                      <Check className="h-2.5 w-2.5" strokeWidth={3} />
                    </span>
                  )}
                  <span className="block text-sm font-bold text-white">{option.shortName}</span>
                  <span className="mt-0.5 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    {option.gender}
                  </span>
                  <span className="mt-2 block text-[10px] leading-snug text-slate-400">
                    {option.description}
                  </span>
                  <span className="mt-2 block truncate font-mono text-[8px] text-slate-600">
                    {option.id}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <div className="label">
            <Wand2 className="h-3.5 w-3.5 text-gold-400" />
            <span>04 · Voice engine</span>
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            <button
              type="button"
              onClick={() => onVoiceCloneChange(false)}
              aria-pressed={!voiceClone}
              className={`relative rounded-2xl border p-3 text-left transition ${
                !voiceClone
                  ? 'border-gold-400/50 bg-gold-400/[0.08]'
                  : 'border-white/10 bg-black/20 hover:border-white/20'
              }`}
            >
              {!voiceClone && (
                <span className="absolute right-2.5 top-2.5 grid h-4 w-4 place-items-center rounded-full bg-gold-400 text-ink-950">
                  <Check className="h-2.5 w-2.5" strokeWidth={3} />
                </span>
              )}
              <Mic className="h-4 w-4 text-gold-300" />
              <span className="mt-2 block text-sm font-bold text-white">Standard Khmer TTS</span>
              <span className="mt-1 block text-[10px] leading-snug text-slate-400">
                Edge neural narration voice
              </span>
            </button>

            <button
              type="button"
              onClick={() => onVoiceCloneChange(true)}
              aria-pressed={voiceClone}
              className={`relative rounded-2xl border p-3 text-left transition ${
                voiceClone
                  ? 'border-gold-400/50 bg-gold-400/[0.08]'
                  : 'border-white/10 bg-black/20 hover:border-white/20'
              }`}
            >
              {voiceClone && (
                <span className="absolute right-2.5 top-2.5 grid h-4 w-4 place-items-center rounded-full bg-gold-400 text-ink-950">
                  <Check className="h-2.5 w-2.5" strokeWidth={3} />
                </span>
              )}
              <Sparkles className="h-4 w-4 text-gold-300" />
              <span className="mt-2 block text-sm font-bold text-white">Free AI Voice Clone</span>
              <span className="mt-1 block text-[10px] leading-snug text-slate-400">
                Seed-VC timbre · keeps the original speaker
              </span>
            </button>
          </div>

          {voiceClone && (
            <div className="mt-3">
              <input
                ref={referenceInputRef}
                type="file"
                accept=".wav,.mp3,audio/wav,audio/mpeg"
                className="hidden"
                onChange={(event) => {
                  pickReference(event.target.files?.[0]);
                  event.target.value = '';
                }}
              />

              {referenceVoice ? (
                <div className="flex items-center gap-3 rounded-2xl border border-gold-400/25 bg-gold-400/[0.06] p-3">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gold-400/15 text-gold-300">
                    <FileAudio className="h-5 w-5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-semibold text-white">{referenceVoice.name}</p>
                    <p className="mt-0.5 text-[10px] text-slate-400">
                      {formatBytes(referenceVoice.size)} · REFERENCE VOICE
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      onReferenceVoiceChange(null);
                      if (referenceInputRef.current) referenceInputRef.current.value = '';
                    }}
                    className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition hover:bg-white/10 hover:text-white"
                    aria-label="Remove reference voice"
                    disabled={isStarting || isJobBusy}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => referenceInputRef.current?.click()}
                  disabled={isStarting || isJobBusy}
                  className="group flex w-full items-center gap-3 rounded-2xl border border-dashed border-white/15 bg-black/20 p-3 text-left transition hover:border-gold-400/50 hover:bg-gold-400/[0.04]"
                >
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-white/10 bg-white/[0.05] text-slate-300 transition group-hover:text-gold-300">
                    <FileAudio className="h-4 w-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-xs font-semibold text-slate-200">
                      Upload Custom Reference Voice
                    </span>
                    <span className="mt-0.5 block text-[10px] text-slate-500">
                      .wav / .mp3, 5-15s · leave empty to auto-extract from video
                    </span>
                  </span>
                </button>
              )}

              <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
                Upload Custom Reference Voice (.wav/.mp3, 5-15s) - Leave empty to auto-extract
                from video. Auto mode isolates the vocals with Demucs/Audio Separator (or an FFmpeg
                speech filter) and slices a clean 10-12s speech segment.
              </p>
              {referenceError && (
                <p className="mt-1.5 text-[10px] font-semibold text-rose-300">{referenceError}</p>
              )}
            </div>
          )}
        </div>

        <div>
          <div className="label">
            <Sparkles className="h-3.5 w-3.5 text-gold-400" />
            <span>05 · Translation style</span>
          </div>
          <div className="grid grid-cols-2 gap-2 rounded-2xl border border-white/10 bg-black/25 p-1">
            {STYLES.map((option) => {
              const selected = style === option.id;
              return (
                <button
                  type="button"
                  key={option.id}
                  onClick={() => onStyleChange(option.id)}
                  aria-pressed={selected}
                  className={`rounded-xl px-3 py-2.5 text-left transition ${
                    selected
                      ? 'bg-white/[0.09] text-white shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <span className="block text-[11px] font-bold leading-tight">{option.label}</span>
                  <span className="mt-0.5 block text-[9px] leading-tight opacity-60">{option.hint}</span>
                </button>
              );
            })}
          </div>
        </div>

        <label className="group flex cursor-pointer items-start gap-3 rounded-2xl border border-white/10 bg-black/20 p-3.5 transition hover:border-white/20">
          <input
            type="checkbox"
            checked={burnSubtitles}
            onChange={(event) => onBurnSubtitlesChange(event.target.checked)}
            className="sr-only"
          />
          <span
            className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md border transition ${
              burnSubtitles
                ? 'border-gold-400 bg-gold-400 text-ink-950'
                : 'border-white/20 bg-black/30 text-transparent'
            }`}
          >
            <Check className="h-3 w-3" strokeWidth={3} />
          </span>
          <span>
            <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
              <Captions className="h-3.5 w-3.5 text-gold-300" />
              Burn Khmer subtitles with black box
            </span>
            <span className="mt-1 block text-[10px] leading-relaxed text-slate-500">
              Uses Kantumruy Pro with a 50% black background to cover hardcoded English text.
            </span>
          </span>
        </label>

        {error && (
          <div className="rounded-xl border border-rose-400/20 bg-rose-400/[0.07] px-3.5 py-3 text-xs leading-relaxed text-rose-200">
            {error}
          </div>
        )}

        <button type="submit" disabled={!canSubmit} className="btn-gold w-full">
          {isStarting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Uploading video…
            </>
          ) : isJobBusy ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Dubbing in progress…
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4" />
              {file ? 'Start Khmer dubbing' : 'Choose a video to start'}
              <ArrowRight className="ml-auto h-4 w-4" />
            </>
          )}
        </button>

        <p className="text-center text-[10px] leading-relaxed text-slate-600">
          Your video stays on this machine. Audio is sent to Gemini and Edge TTS only during processing.
        </p>
      </form>
    </aside>
  );
}
