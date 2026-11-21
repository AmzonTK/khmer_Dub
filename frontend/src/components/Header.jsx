import { Clapperboard, Sparkles } from 'lucide-react';

export default function Header() {
  return (
    <header className="relative z-20 border-b border-white/[0.07] bg-ink-950/55 backdrop-blur-xl">
      <div className="mx-auto flex h-[72px] max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <a href="#" className="group flex items-center gap-3">
          <span className="relative grid h-10 w-10 place-items-center overflow-hidden rounded-xl border border-gold-400/25 bg-gradient-to-br from-gold-300 to-gold-500 text-ink-950 shadow-glow">
            <Clapperboard className="h-5 w-5" strokeWidth={2.4} />
            <span className="absolute inset-x-0 top-0 h-1/2 bg-white/25" />
          </span>
          <span>
            <span className="flex items-center gap-1.5 text-[15px] font-extrabold tracking-tight text-white">
              KhmerDub
              <span className="text-gold-400">Studio</span>
            </span>
            <span className="block text-[9px] font-semibold uppercase tracking-[0.22em] text-slate-500">
              AI dubbing workspace
            </span>
          </span>
        </a>

        <nav className="hidden items-center gap-8 text-xs font-semibold text-slate-400 md:flex">
          <a className="transition hover:text-white" href="#studio">
            Studio
          </a>
          <a className="transition hover:text-white" href="#pipeline">
            Pipeline
          </a>
          <a className="transition hover:text-white" href="#transcript">
            Transcript
          </a>
        </nav>

        <div className="flex items-center gap-2">
          <span className="hidden items-center gap-1.5 rounded-full border border-emerald-400/20 bg-emerald-400/[0.07] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300 sm:inline-flex">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            Local pipeline
          </span>
          <a
            href="https://ai.google.dev/gemini-api/docs/api-key"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold text-slate-300 transition hover:border-gold-400/30 hover:text-white"
          >
            <Sparkles className="h-3.5 w-3.5 text-gold-400" />
            <span className="hidden sm:inline">Get API key</span>
          </a>
        </div>
      </div>
    </header>
  );
}
