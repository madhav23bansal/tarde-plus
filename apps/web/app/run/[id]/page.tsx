"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { CycleDetailSkeleton } from "@/components/skeleton";
import { cn } from "@/lib/cn";
import { Tip } from "@/components/tip";
import {
  ArrowLeft, CheckCircle2, XCircle, TrendingUp, TrendingDown, Minus,
  AlertTriangle, Zap, BarChart3, Gem, CircleDot, Landmark, Globe,
  ChevronRight, Clock, Layers, Brain, Activity,
} from "lucide-react";

// ── Instrument meta ─────────────────────────────────────────────

const INST: Record<string, { label: string; icon: typeof Globe; color: string }> = {
  NIFTYBEES: { label: "Nifty 50", icon: BarChart3, color: "blue" },
  GOLDBEES: { label: "Gold", icon: Gem, color: "amber" },
  SILVERBEES: { label: "Silver", icon: CircleDot, color: "slate" },
  BANKBEES: { label: "Bank Nifty", icon: Landmark, color: "purple" },
};

// ── Indicator context engine ────────────────────────────────────

type Indicator = { label: string; value: string; status: "bullish" | "bearish" | "neutral" | "warning"; zone: string; tip: string };

function getIndicators(inst: any): Indicator[] {
  const rsi = inst.rsi_14 ?? 50;
  const macd = inst.macd_histogram ?? 0;
  const bb = inst.bb_position ?? 0.5;
  const vol = inst.volume_ratio ?? 1;
  const ema9 = inst.ema_9 ?? 0;
  const ema21 = inst.ema_21 ?? 0;
  const sent = inst.news_sentiment ?? 0;
  return [
    { label: "RSI", value: rsi.toFixed(0), status: rsi < 30 ? "bullish" : rsi > 70 ? "bearish" : "neutral", zone: rsi < 30 ? "Oversold" : rsi > 70 ? "Overbought" : rsi < 45 ? "Weak" : rsi > 55 ? "Strong" : "Neutral", tip: "RSI(14) — <30 oversold (buy), >70 overbought (sell)" },
    { label: "MACD", value: (macd > 0 ? "+" : "") + macd.toFixed(2), status: macd > 0 ? "bullish" : "bearish", zone: macd > 0 ? "Momentum ↑" : "Momentum ↓", tip: "MACD Histogram — positive = bullish momentum building" },
    { label: "Bollinger", value: bb.toFixed(2), status: bb < 0.2 ? "bullish" : bb > 0.8 ? "bearish" : "neutral", zone: bb < 0.2 ? "Near Low Band" : bb > 0.8 ? "Near High Band" : "Mid Range", tip: "Bollinger Band position — 0 = lower band (oversold), 1 = upper" },
    { label: "Volume", value: vol.toFixed(1) + "x", status: vol > 1.5 ? "warning" : "neutral", zone: vol > 1.5 ? "High Volume" : vol < 0.5 ? "Low Volume" : "Normal", tip: "Volume vs 20-day average — >1.5x confirms the move" },
    { label: "EMA", value: ema9 > ema21 ? "9 > 21" : "9 < 21", status: ema9 > ema21 ? "bullish" : "bearish", zone: ema9 > ema21 ? "Uptrend" : "Downtrend", tip: "EMA crossover — 9 above 21 = uptrend, below = downtrend" },
    { label: "Sentiment", value: sent.toFixed(2), status: sent > 0.1 ? "bullish" : sent < -0.1 ? "bearish" : "neutral", zone: sent > 0.1 ? "Positive News" : sent < -0.1 ? "Negative News" : "Mixed", tip: "News sentiment from headlines (-1 bearish to +1 bullish)" },
  ];
}

const STATUS_COLORS: Record<string, string> = {
  bullish: "text-emerald-400 bg-emerald-500/8 border-emerald-500/20",
  bearish: "text-red-400 bg-red-500/8 border-red-500/20",
  neutral: "text-zinc-400 bg-zinc-800/50 border-zinc-700/30",
  warning: "text-blue-400 bg-blue-500/8 border-blue-500/20",
};

// ── Score bar ───────────────────────────────────────────────────

function ScoreBar({ score, confidence, direction }: { score: number; confidence: number; direction: string }) {
  const pct = Math.abs(score) * 100;
  const isLong = direction === "LONG";
  const isShort = direction === "SHORT";
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[10px]">
        <span className="text-red-500/70 font-bold">SHORT</span>
        <span className={cn("font-mono font-bold text-base tabular-nums", isLong ? "text-emerald-400" : isShort ? "text-red-400" : "text-zinc-500")}>
          {score > 0 ? "+" : ""}{score.toFixed(3)}
        </span>
        <span className="text-emerald-500/70 font-bold">LONG</span>
      </div>
      <div className="relative h-2.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className="absolute top-0 bottom-0 left-1/2 w-px bg-zinc-600 z-10" />
        <div className={cn("absolute top-0 bottom-0 rounded-full transition-all duration-700",
          isLong ? "bg-gradient-to-r from-emerald-600 to-emerald-400" : isShort ? "bg-gradient-to-l from-red-600 to-red-400" : "bg-zinc-600"
        )} style={{ left: score >= 0 ? "50%" : `${50 - pct / 2}%`, width: `${pct / 2}%` }} />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-[9px] text-zinc-600 w-14 shrink-0">Confidence</span>
        <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <div className="h-full bg-blue-500/50 rounded-full transition-all duration-700" style={{ width: `${confidence * 100}%` }} />
        </div>
        <span className="text-[10px] font-mono text-zinc-400 w-8 text-right">{(confidence * 100).toFixed(0)}%</span>
      </div>
    </div>
  );
}

// ── Reason bar ──────────────────────────────────────────────────

function ReasonBar({ reason, direction, index }: { reason: string; direction: string; index: number }) {
  const weights: Record<string, number> = { fii: 0.9, vix: 0.75, rsi: 0.65, macd: 0.6, ema: 0.55, market: 0.5, trend: 0.5, breadth: 0.6, sentiment: 0.4 };
  const w = Object.entries(weights).find(([k]) => reason.toLowerCase().includes(k))?.[1] ?? (0.6 - index * 0.08);
  const isPos = direction === "LONG";
  return (
    <div className="flex items-center gap-3 py-1">
      <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", isPos ? "bg-emerald-500" : "bg-red-500")} />
      <p className="text-xs text-zinc-300 flex-1 leading-snug min-w-0">{reason}</p>
      <Tip text={`Factor strength: ${(w * 100).toFixed(0)}% contribution weight`}>
        <div className="w-20 h-1.5 bg-zinc-800 rounded-full overflow-hidden shrink-0 cursor-help">
          <div className={cn("h-full rounded-full", isPos ? "bg-emerald-500/60" : "bg-red-500/60")} style={{ width: `${w * 100}%` }} />
        </div>
      </Tip>
    </div>
  );
}

// ── Collapsible section ─────────────────────────────────────────

function Collapsible({ title, count, icon: Icon, children, defaultOpen = false }: {
  title: string; count: number; icon: typeof Globe; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-zinc-800/30">
      <button onClick={() => setOpen(o => !o)} className="w-full px-5 py-2.5 flex items-center gap-2 text-left hover:bg-zinc-800/10 transition-colors">
        <ChevronRight className={cn("h-3.5 w-3.5 text-zinc-600 transition-transform duration-200", open && "rotate-90")} />
        <Icon className="h-3.5 w-3.5 text-zinc-500" />
        <span className="text-[11px] text-zinc-400 font-semibold uppercase tracking-wider">{title}</span>
        <span className="text-[10px] text-zinc-700 bg-zinc-800 px-1.5 py-0.5 rounded font-mono">{count}</span>
      </button>
      {open && <div className="px-5 pb-4">{children}</div>}
    </div>
  );
}

// ── Signal grid (for global/sector/features) ────────────────────

function SignalGrid({ signals, columns = 4 }: { signals: Record<string, any>; columns?: number }) {
  const entries = Object.entries(signals).filter(([, v]) => v != null).sort(([a], [b]) => a.localeCompare(b));
  return (
    <div className={cn("grid gap-x-4 gap-y-1", `grid-cols-${columns}`)}>
      {entries.map(([k, v]) => {
        const n = typeof v === "number" ? v : null;
        const color = n == null ? "text-zinc-400" : Math.abs(n) < 0.001 ? "text-zinc-600" : n > 0 ? "text-emerald-400" : "text-red-400";
        const display = n != null ? (Math.abs(n) > 1000 ? `${(n / 1000).toFixed(1)}K` : Math.abs(n) >= 1 ? n.toFixed(2) : n.toFixed(4)) : String(v);
        return (
          <div key={k} className="flex items-center justify-between gap-2 py-0.5 hover:bg-zinc-800/10 rounded px-1 -mx-1">
            <span className="text-[10px] text-zinc-500 truncate">{k.replace(/_/g, " ")}</span>
            <span className={cn("text-[11px] font-mono font-semibold tabular-nums shrink-0", color)}>{display}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────

export default function RunDetail() {
  const params = useParams();
  const id = params?.id as string;
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("");

  useEffect(() => {
    if (!id) return;
    fetch(`/api/run/${id}`)
      .then(r => r.json())
      .then(d => {
        if (d.error) { setError(d.error); return; }
        setData(d);
        // Set first instrument as default tab
        const first = Object.keys(d.instruments ?? {})[0];
        if (first) setActiveTab(first);
      })
      .catch(e => setError(e.message));
  }, [id]);

  if (error) return (
    <div className="min-h-screen bg-[#08080c] text-zinc-100 flex items-center justify-center">
      <div className="text-center space-y-3">
        <XCircle className="h-8 w-8 text-red-400 mx-auto" />
        <p className="text-sm text-red-400">{error}</p>
        <Link href="/" className="text-xs text-blue-400 hover:underline">Back to dashboard</Link>
      </div>
    </div>
  );

  if (!data) return (
    <div className="min-h-screen bg-[#08080c] text-zinc-100">
      <header className="sticky top-0 z-50 bg-[#0a0a0f]/95 backdrop-blur-md border-b border-zinc-800/60">
        <div className="max-w-[1600px] mx-auto px-5 h-12 flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2 text-zinc-400 hover:text-zinc-200 transition-colors">
            <ArrowLeft className="h-4 w-4" /><span className="text-xs">Dashboard</span>
          </Link>
          <span className="text-zinc-800">|</span>
          <Zap className="h-4 w-4 text-blue-500" />
          <span className="font-bold text-zinc-400 text-sm">Loading...</span>
        </div>
      </header>
      <CycleDetailSkeleton />
    </div>
  );

  const instruments = Object.entries(data.instruments ?? {});
  const time = data.timestamp?.split("T")[1]?.substring(0, 8) ?? "";

  return (
    <div className="min-h-screen bg-[#08080c] text-zinc-100 font-sans">
      {/* Nav */}
      <header className="sticky top-0 z-50 bg-[#0a0a0f]/95 backdrop-blur-md border-b border-zinc-800/60">
        <div className="max-w-[1600px] mx-auto px-5 h-11 flex items-center gap-3 text-xs">
          <Link href="/" className="flex items-center gap-1.5 text-zinc-400 hover:text-zinc-200 transition-colors">
            <ArrowLeft className="h-3.5 w-3.5" /><span>Dashboard</span>
          </Link>
          <span className="text-zinc-800">|</span>
          <Zap className="h-3.5 w-3.5 text-blue-500" />
          <span className="font-bold text-zinc-200 text-sm">Pipeline Run</span>
          <span className="font-mono text-zinc-500">{data.run_id?.substring(0, 8)}</span>
        </div>
      </header>

      {/* ── LAYER 1: VERDICT ─────────────────────────────────────── */}
      <div className="bg-[#0c0c11] border-b border-zinc-800/50">
        <div className="max-w-[1600px] mx-auto px-5 py-4 space-y-3">
          {/* Status row */}
          <div className="flex items-center gap-3 flex-wrap">
            <span className="flex items-center gap-1.5 text-emerald-400 text-xs font-bold">
              <CheckCircle2 className="h-3.5 w-3.5" /> SUCCESS
            </span>
            <span className="text-zinc-700">|</span>
            <span className="text-zinc-400 text-xs flex items-center gap-1.5"><Clock className="h-3 w-3" />{time} IST</span>
            <span className="text-zinc-700">|</span>
            <span className={cn("text-[10px] font-bold tracking-widest px-2 py-0.5 rounded border",
              data.session === "regular" ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" : "text-amber-400 bg-amber-500/10 border-amber-500/20"
            )}>{data.session?.toUpperCase()}</span>
            <span className="text-zinc-700">|</span>
            <span className="text-zinc-500 text-xs font-mono">{data.duration_sec}s</span>
          </div>

          {/* Instrument tabs */}
          <div className="flex border-b border-zinc-800/40 -mb-px">
            {instruments.map(([ticker, inst]: [string, any]) => {
              const meta = INST[ticker] ?? { label: ticker, icon: Globe, color: "zinc" };
              const Icon = meta.icon;
              const pred = inst.prediction;
              const dir = pred?.direction ?? "FLAT";
              const isActive = activeTab === ticker;
              return (
                <button key={ticker} onClick={() => setActiveTab(ticker)}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all -mb-px",
                    isActive
                      ? dir === "LONG" ? "border-emerald-500 text-emerald-400 bg-emerald-500/5"
                        : dir === "SHORT" ? "border-red-500 text-red-400 bg-red-500/5"
                        : "border-zinc-400 text-zinc-300 bg-zinc-800/20"
                      : "border-transparent text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/10"
                  )}>
                  <Icon className="h-3.5 w-3.5" />
                  <span>{meta.label}</span>
                  <span className={cn("font-mono tabular-nums text-[10px]",
                    dir === "LONG" ? "text-emerald-500" : dir === "SHORT" ? "text-red-500" : "text-zinc-600"
                  )}>{pred?.score > 0 ? "+" : ""}{pred?.score?.toFixed(2)}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── LAYER 2 + 3: ACTIVE INSTRUMENT DETAIL ────────────────── */}
      <main className="max-w-[1600px] mx-auto px-5 py-4 space-y-4">
        {instruments.filter(([ticker]) => ticker === activeTab).map(([ticker, inst]: [string, any]) => {
          const meta = INST[ticker] ?? { label: ticker, icon: Globe, color: "zinc" };
          const Icon = meta.icon;
          const pred = inst.prediction;
          const dir = pred?.direction ?? "FLAT";
          const dc = dir === "LONG" ? "emerald" : dir === "SHORT" ? "red" : "zinc";
          const indicators = getIndicators(inst);
          const isUp = (inst.change_pct ?? 0) >= 0;

          return (
            <div key={ticker} id={ticker} className={cn("rounded-xl border bg-[#0c0c11] overflow-hidden scroll-mt-14",
              dir === "LONG" ? "border-emerald-900/30" : dir === "SHORT" ? "border-red-900/30" : "border-zinc-800/50"
            )}>
              <div className={cn("h-0.5", `bg-${dc}-500/40`)} />

              {/* Zone A: Identity + Verdict */}
              <div className="px-5 py-4 flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-3">
                  <div className={cn("p-2 rounded-lg", `bg-${meta.color}-500/10`)}>
                    <Icon className={cn("h-5 w-5", `text-${meta.color}-400`)} />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-zinc-100">{meta.label}</h2>
                    <p className="text-[10px] text-zinc-600">{ticker}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div>
                    <span className="text-2xl font-bold font-mono tabular-nums text-zinc-50">{inst.price?.toFixed(2)}</span>
                    <span className={cn("text-sm font-mono font-semibold ml-2", isUp ? "text-emerald-400" : "text-red-400")}>
                      {inst.change_pct >= 0 ? "+" : ""}{inst.change_pct?.toFixed(2)}%
                    </span>
                  </div>
                  {pred && (
                    <span className={cn("flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm font-black tracking-wider",
                      dir === "LONG" ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20"
                      : dir === "SHORT" ? "text-red-400 bg-red-500/10 border-red-500/20"
                      : "text-zinc-500 bg-zinc-800 border-zinc-700"
                    )}>
                      {dir === "LONG" ? <TrendingUp className="h-4 w-4" /> : dir === "SHORT" ? <TrendingDown className="h-4 w-4" /> : <Minus className="h-4 w-4" />}
                      {dir}
                    </span>
                  )}
                </div>
              </div>

              {/* Zone B: Score + Reasons */}
              {pred && (
                <div className="px-5 pb-4 grid grid-cols-1 lg:grid-cols-2 gap-5">
                  <div>
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <Activity className="h-3 w-3" /> Prediction Score
                    </p>
                    <ScoreBar score={pred.score} confidence={pred.confidence} direction={dir} />
                  </div>
                  <div>
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <Brain className="h-3 w-3" /> Why This Prediction ({pred.features_used} features analyzed)
                    </p>
                    <div className="space-y-0.5">
                      {pred.reasons?.map((r: string, i: number) => (
                        <ReasonBar key={i} reason={r} direction={dir} index={i} />
                      ))}
                      {(!pred.reasons || pred.reasons.length === 0) && (
                        <p className="text-xs text-zinc-600">No specific reasons — weak/mixed signals</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Zone C: Indicator Badges */}
              <div className="px-5 pb-4">
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Technical Indicators</p>
                <div className="grid grid-cols-6 gap-2">
                  {indicators.map(ind => (
                    <Tip key={ind.label} text={ind.tip}>
                      <div className={cn("rounded-lg border px-3 py-2.5 text-center cursor-help transition-colors hover:brightness-110", STATUS_COLORS[ind.status])}>
                        <p className="text-[9px] uppercase tracking-wider opacity-60 mb-0.5">{ind.label}</p>
                        <p className="font-mono font-bold tabular-nums text-sm">{ind.value}</p>
                        <p className="text-[9px] opacity-60 mt-0.5">{ind.zone}</p>
                      </div>
                    </Tip>
                  ))}
                </div>
              </div>

              {/* Zone D: Market data strip */}
              <div className="px-5 pb-3 flex flex-wrap gap-x-5 gap-y-1 text-[11px]">
                {([
                  ["Prev Close", inst.prev_close?.toFixed(2)],
                  ["Day High", inst.day_high?.toFixed(2)],
                  ["Day Low", inst.day_low?.toFixed(2)],
                  ["Volume", inst.volume?.toLocaleString()],
                  ["ATR(14)", inst.atr_14?.toFixed(2)],
                  ["1D", `${inst.returns_1d > 0 ? "+" : ""}${inst.returns_1d?.toFixed(1)}%`],
                  ["5D", `${inst.returns_5d > 0 ? "+" : ""}${inst.returns_5d?.toFixed(1)}%`],
                  ["10D", `${inst.returns_10d > 0 ? "+" : ""}${inst.returns_10d?.toFixed(1)}%`],
                ] as const).map(([l, v]) => (
                  <span key={l} className="text-zinc-500"><span className="text-zinc-600">{l}:</span> <span className="font-mono text-zinc-400">{v}</span></span>
                ))}
              </div>

              {/* Zone E: Collapsible raw data */}
              <Collapsible title="Global Signals" count={Object.keys(inst.global_signals ?? {}).length} icon={Globe} defaultOpen>
                <SignalGrid signals={inst.global_signals ?? {}} columns={5} />
              </Collapsible>
              <Collapsible title="Sector Signals" count={Object.keys(inst.sector_signals ?? {}).length} icon={Layers} defaultOpen>
                <SignalGrid signals={inst.sector_signals ?? {}} columns={4} />
              </Collapsible>
              <Collapsible title="All ML Features" count={Object.keys(inst.features ?? {}).length} icon={Brain}>
                <SignalGrid signals={inst.features ?? {}} columns={5} />
              </Collapsible>

              {/* Errors */}
              {inst.errors?.length > 0 && (
                <div className="px-5 py-2 border-t border-zinc-800/30 flex items-center gap-2 text-amber-400 text-xs">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  {inst.errors.join(", ")}
                </div>
              )}
            </div>
          );
        })}
      </main>
    </div>
  );
}
