"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useStore, type Prediction } from "@/lib/ws";
import { Tip } from "@/components/tip";
import { cn } from "@/lib/cn";
import {
  TrendingUp, TrendingDown, Minus, Clock, BarChart3,
  AlertTriangle, Wifi, WifiOff, ArrowUpRight, ArrowDownRight,
  Globe, Landmark, Zap, Timer, Loader2, DollarSign, CheckCircle2, XCircle,
} from "lucide-react";

function useTick(ms = 1000) { const [, s] = useState(0); useEffect(() => { const i = setInterval(() => s(t => t + 1), ms); return () => clearInterval(i); }, [ms]); }
function parseTimeSec(s: string): number { const m = s.match(/(?:(\d+)\s*days?,?\s*)?(\d+):(\d+):(\d+)/); if (!m) return 0; return +(m[1] || 0) * 86400 + +m[2] * 3600 + +m[3] * 60 + +m[4]; }
function fmtDur(s: number): string { if (s <= 0) return "0s"; const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60; if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m ${String(sec).padStart(2, "0")}s`; return `${m}m ${String(sec).padStart(2, "0")}s`; }

const INST: Record<string, { label: string; icon: typeof Globe }> = {
  NIFTYBEES: { label: "Nifty 50", icon: BarChart3 },
  BANKBEES: { label: "Bank Nifty", icon: Landmark },
  SETFNIF50: { label: "SBI Nifty", icon: BarChart3 },
};

// ── Header ──────────────────────────────────────────────────────

function Header() {
  useTick();
  const { connected, status, session, collectionCount, updatedAt, lastWsMessage } = useStore();
  const tto = status?.market?.time_to_open ? parseTimeSec(status.market.time_to_open) : 0;
  const elapsed = lastWsMessage ? Math.floor((Date.now() - lastWsMessage) / 1000) : 0;
  const remaining = Math.max(0, tto - elapsed);
  const updAgo = updatedAt ? Math.floor(Date.now() / 1000 - updatedAt) : null;
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);
  const now = mounted ? new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }) : "--:--:--";

  const badges: Record<string, { l: string; c: string; dot?: boolean }> = {
    pre_market: { l: "PRE-MKT", c: "text-amber-400 bg-amber-500/10 border-amber-500/25" },
    regular: { l: "LIVE", c: "text-emerald-400 bg-emerald-500/10 border-emerald-500/25", dot: true },
    closing: { l: "CLOSING", c: "text-red-400 bg-red-500/10 border-red-500/25", dot: true },
    post_market: { l: "CLOSED", c: "text-zinc-500 bg-zinc-800 border-zinc-700" },
    closed: { l: "CLOSED", c: "text-zinc-600 bg-zinc-900 border-zinc-800" },
  };
  const b = badges[session] ?? badges.closed;

  return (
    <header className="sticky top-0 z-50 bg-[#0a0a0f]/95 backdrop-blur-md border-b border-zinc-800/60">
      <div className="max-w-[1440px] mx-auto px-5 h-12 flex items-center justify-between text-xs">
        <div className="flex items-center gap-3">
          <Zap className="h-4 w-4 text-blue-500" />
          <Link href="/" className="font-bold text-base tracking-tight text-zinc-100 hover:text-white transition-colors">Trade-Plus</Link>
          <Link href="/trades" className="text-zinc-500 hover:text-zinc-300 border border-zinc-800 hover:border-zinc-600 px-2.5 py-1 rounded-md transition-all text-[11px]">Trades</Link>
          <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded border font-bold tracking-widest text-[10px]", b.c)}>
            {b.dot && <span className="relative flex h-1.5 w-1.5"><span className="animate-ping absolute h-full w-full rounded-full bg-current opacity-40" /><span className="relative rounded-full h-1.5 w-1.5 bg-current" /></span>}
            {b.l}
          </span>
        </div>
        <div className="flex items-center gap-4 font-mono tabular-nums">
          <span className="text-sm text-zinc-200">{now}</span>
          <span className="text-zinc-600 text-[10px]">IST</span>
          {session !== "regular" && remaining > 0 && (
            <span className="text-amber-400 flex items-center gap-1"><Timer className="h-3 w-3" />{fmtDur(remaining)}</span>
          )}
          {session === "regular" && <span className="text-emerald-400 font-semibold">Trading</span>}
          {updAgo != null && <span className="text-zinc-700">{updAgo}s</span>}
          <span className={cn("flex items-center gap-1", connected ? "text-emerald-500" : "text-red-500")}>
            {connected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
          </span>
        </div>
      </div>
    </header>
  );
}

// ── Market Context Bar ──────────────────────────────────────────

function MarketContext() {
  const { predictions } = useStore();
  const p = predictions[0];
  if (!p) return null;
  const nse = p.nse_data;
  const ss = p.sector_signals;

  const items: [string, number | undefined, string, boolean?][] = [
    ["S&P", ss?.sp500_change, "US overnight sentiment"],
    ["Crude", ss?.crude_oil_change, "Oil price — rising = bearish India"],
    ["VIX", nse?.india_vix, "India VIX — fear gauge", true],
    ["FII", nse?.fii_net, "FII net flow (₹Cr)", true],
    ["DII", nse?.dii_net, "DII net flow (₹Cr)", true],
  ];

  return (
    <div className="flex gap-1 overflow-x-auto pb-1">
      {items.map(([label, val, tip, isAbs]) => (
        <Tip key={label} text={tip}>
          <div className="shrink-0 bg-[#0c0c11] border border-zinc-800/40 rounded-lg px-3 py-1.5 min-w-[90px] cursor-help">
            <p className="text-[9px] text-zinc-600 uppercase tracking-wider">{label}</p>
            <p className={cn("text-xs font-mono font-bold tabular-nums",
              val == null ? "text-zinc-800" :
              isAbs ? (typeof val === "number" && Math.abs(val) > 20 ? "text-amber-400" : "text-zinc-300") :
              (typeof val === "number" && val > 0 ? "text-emerald-400" : typeof val === "number" && val < 0 ? "text-red-400" : "text-zinc-500")
            )}>
              {val != null ? (
                isAbs ? (typeof val === "number" && Math.abs(val) > 100 ? `${(val / 1000).toFixed(1)}K` : typeof val === "number" ? val.toFixed(1) : "--") :
                `${typeof val === "number" && val > 0 ? "+" : ""}${typeof val === "number" ? val.toFixed(2) : "--"}%`
              ) : "--"}
            </p>
          </div>
        </Tip>
      ))}
    </div>
  );
}

// ── Instrument Card ─────────────────────────────────────────────

function InstrumentCard({ pred, seq }: { pred: Prediction; seq: number }) {
  const md = pred.market_data;
  const meta = INST[pred.instrument] ?? { label: pred.instrument, icon: Globe };
  const Icon = meta.icon;
  const { trading, livePrices } = useStore();
  const pos = trading?.positions?.[pred.instrument];
  const lp = livePrices?.[pred.instrument];
  const price = lp?.price || md?.price || 0;
  const isUp = (md?.change_pct ?? 0) >= 0;

  const prev = useRef(seq); const [flash, setFlash] = useState(false);
  useEffect(() => { if (seq !== prev.current) { prev.current = seq; setFlash(true); const t = setTimeout(() => setFlash(false), 600); return () => clearTimeout(t); } }, [seq]);

  const dc = pred.direction === "LONG" ? "emerald" : pred.direction === "SHORT" ? "red" : "zinc";

  return (
    <div className={cn("rounded-xl border bg-[#0c0c11] overflow-hidden transition-all",
      pred.direction === "LONG" ? "border-emerald-500/15" : pred.direction === "SHORT" ? "border-red-500/15" : "border-zinc-800/50")}>

      {/* Color accent */}
      <div className={cn("h-[2px]", `bg-${dc}-500/40`)} />

      <div className="p-4 space-y-3">
        {/* Row 1: Name + Direction */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className={cn("h-4 w-4", pred.direction === "LONG" ? "text-emerald-400" : pred.direction === "SHORT" ? "text-red-400" : "text-zinc-500")} />
            <div>
              <p className="text-sm font-semibold text-zinc-200 leading-tight">{meta.label}</p>
              <p className="text-[10px] text-zinc-600 leading-tight">{pred.instrument}</p>
            </div>
          </div>
          <div className={cn("flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-black tracking-wider",
            pred.direction === "LONG" ? "text-emerald-400 bg-emerald-500/10" :
            pred.direction === "SHORT" ? "text-red-400 bg-red-500/10" : "text-zinc-600 bg-zinc-800")}>
            {pred.direction === "LONG" && <TrendingUp className="h-3.5 w-3.5" />}
            {pred.direction === "SHORT" && <TrendingDown className="h-3.5 w-3.5" />}
            {pred.direction === "FLAT" && <Minus className="h-3.5 w-3.5" />}
            {pred.direction}
          </div>
        </div>

        {/* Row 2: Price + Score */}
        <div className="flex items-end justify-between">
          <div>
            <p className={cn("text-[28px] font-bold font-mono tabular-nums leading-none tracking-tight transition-colors duration-500", flash ? "text-blue-200" : "text-zinc-50")}>
              {price > 0 ? `₹${price.toFixed(2)}` : "—"}
            </p>
            {md && (
              <p className={cn("text-xs font-mono mt-1 flex items-center gap-0.5", isUp ? "text-emerald-400" : "text-red-400")}>
                {isUp ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                {md.change_pct >= 0 ? "+" : ""}{md.change_pct?.toFixed(2)}%
              </p>
            )}
          </div>
          <div className="text-right">
            <p className={cn("text-2xl font-bold font-mono tabular-nums",
              pred.score > 0.05 ? "text-emerald-400" : pred.score < -0.05 ? "text-red-400" : "text-zinc-600")}>
              {pred.score > 0 ? "+" : ""}{pred.score?.toFixed(2)}
            </p>
            <p className="text-[10px] text-zinc-600">{(pred.confidence * 100)?.toFixed(0)}% · {pred.method}</p>
          </div>
        </div>

        {/* Score bar */}
        <div className="h-1 bg-zinc-800 rounded-full overflow-hidden relative">
          <div className="absolute top-0 bottom-0 left-1/2 w-px bg-zinc-700 z-10" />
          <div className={cn("absolute top-0 bottom-0 rounded-full transition-all duration-700",
            pred.score > 0 ? "bg-gradient-to-r from-emerald-600 to-emerald-400" : "bg-gradient-to-l from-red-600 to-red-400")}
            style={{ left: pred.score >= 0 ? "50%" : `${50 - Math.abs(pred.score) * 50}%`, width: `${Math.abs(pred.score) * 50}%` }} />
        </div>

        {/* Reasons */}
        {pred.reasons?.length > 0 && (
          <div className="space-y-0.5">
            {pred.reasons.slice(0, 2).map((r, i) => (
              <p key={i} className="text-[11px] text-zinc-400 leading-snug flex items-start gap-1.5">
                <span className={cn("mt-[5px] h-1 w-1 rounded-full shrink-0",
                  pred.direction === "LONG" ? "bg-emerald-500" : pred.direction === "SHORT" ? "bg-red-500" : "bg-zinc-600")} />
                {r}
              </p>
            ))}
          </div>
        )}

        {/* S/R Levels */}
        {pred.levels?.levels?.length > 0 && (
          <div className="flex items-center gap-2 text-[10px] pt-1 border-t border-zinc-800/30">
            <span className="text-zinc-600">Levels:</span>
            {(() => {
              const lvls = pred.levels.levels;
              const sup = lvls.filter((l: any) => l.type === "support" && l.price < price).slice(-2);
              const res = lvls.filter((l: any) => l.type === "resistance" && l.price > price).slice(0, 2);
              return (<>
                {sup.map((l: any) => <span key={l.name} className="text-emerald-500/50 font-mono">S:{l.price}</span>)}
                <span className="text-zinc-800">|</span>
                {res.map((l: any) => <span key={l.name} className="text-red-500/50 font-mono">R:{l.price}</span>)}
                {!sup.length && !res.length && <span className="text-zinc-700">Computing...</span>}
              </>);
            })()}
            {pred.levels.cpr && (
              <span className={cn("ml-auto px-1.5 py-px rounded text-[9px] font-bold",
                pred.levels.cpr.day_type === "trending" ? "text-blue-400 bg-blue-500/10" : "text-amber-400 bg-amber-500/10")}>
                {pred.levels.cpr.day_type}
              </span>
            )}
          </div>
        )}

        {/* Engine decision */}
        {pred.decision && (
          <div className="flex items-center gap-2 text-[10px] border-t border-zinc-800/30 pt-1">
            <Zap className="h-3 w-3 text-blue-500/60" />
            <span className={cn("font-semibold",
              pred.decision.action?.includes("ENTER") ? "text-blue-400" :
              pred.decision.action === "HOLD" ? "text-zinc-400" : "text-zinc-600")}>
              {pred.decision.action}
            </span>
            <span className="text-zinc-600 truncate flex-1">{pred.decision.reasons?.[0]}</span>
          </div>
        )}
      </div>

      {/* Position stripe */}
      {pos && (
        <div className={cn("px-4 py-2 border-t flex items-center justify-between",
          pos.side === "LONG" ? "bg-emerald-500/[0.04] border-emerald-500/10" : "bg-red-500/[0.04] border-red-500/10")}>
          <span className="text-[11px] text-zinc-500">
            <span className={cn("font-bold", pos.side === "LONG" ? "text-emerald-400" : "text-red-400")}>{pos.side}</span>
            {" "}{pos.quantity}u @ ₹{pos.entry_price?.toFixed(2)}
          </span>
          <span className={cn("text-sm font-bold font-mono tabular-nums",
            pos.unrealized_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
            {pos.unrealized_pnl >= 0 ? "+" : ""}₹{pos.unrealized_pnl?.toFixed(2)}
          </span>
        </div>
      )}
    </div>
  );
}

// ── Bottom Status Bar ───────────────────────────────────────────

function BottomBar() {
  useTick();
  const { trading, connected, collectionCount, updatedAt } = useStore();
  const updAgo = updatedAt ? Math.floor(Date.now() / 1000 - updatedAt) : null;
  return (
    <div className="fixed bottom-0 left-0 right-0 h-8 bg-[#0a0a0f] border-t border-zinc-800/60 flex items-center px-5 gap-6 text-[10px] z-50">
      {trading && <>
        <span className="text-zinc-600">Positions <span className={cn("font-bold", trading.open_position_count > 0 ? "text-blue-400" : "text-zinc-500")}>{trading.open_position_count}</span></span>
        <span className="text-zinc-600">P&L <span className={cn("font-bold font-mono", trading.day_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>{trading.day_pnl >= 0 ? "+" : ""}₹{trading.day_pnl?.toFixed(2)}</span></span>
        <span className="text-zinc-600">Trades <span className="text-zinc-400">{trading.day_trades}</span></span>
        <span className="text-zinc-600">Capital <span className="text-zinc-400 font-mono">₹{trading.capital?.toFixed(0)}</span></span>
      </>}
      <span className="ml-auto text-zinc-700 font-mono tabular-nums">#{collectionCount}{updAgo != null ? ` · ${updAgo}s` : ""}</span>
      <span className={cn("text-lg leading-none", connected ? "text-emerald-500" : "text-red-500")}>●</span>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────

export default function Home() {
  useTick();
  const { connected, predictions, status, updateSeq, trading, activity } = useStore();
  const hasPreds = predictions.length > 0;

  return (
    <div className="flex flex-col min-h-screen bg-[#08080c] text-zinc-100 font-sans pb-10">
      <Header />

      <main className="flex-1 max-w-[1440px] mx-auto w-full px-5 py-4 space-y-4">
        {/* Connection alert */}
        {!connected && !hasPreds && (
          <div className="flex items-center gap-2 bg-amber-500/5 border border-amber-500/15 rounded-lg px-4 py-3 text-xs text-amber-400/80">
            <Loader2 className="h-4 w-4 animate-spin" /> Connecting...
          </div>
        )}

        {status?.market?.should_squareoff && (
          <div className="flex items-center gap-2 bg-red-500/8 border border-red-500/20 rounded-lg px-4 py-2.5 text-xs text-red-400 font-bold animate-pulse">
            <AlertTriangle className="h-4 w-4" /> SQUARE OFF — Close positions before 3:20 PM
          </div>
        )}

        {/* Trading bar */}
        {trading && (
          <Link href="/trades" className={cn("group flex items-center justify-between rounded-lg border px-4 py-3 transition-all hover:brightness-110",
            !trading.day_trades ? "border-zinc-800/50 bg-[#0c0c11]" :
            trading.day_pnl >= 0 ? "border-emerald-500/15 bg-emerald-500/[0.02]" : "border-red-500/15 bg-red-500/[0.02]")}>
            <div className="flex items-center gap-5 text-xs">
              <DollarSign className="h-4 w-4 text-zinc-600" />
              <span className="text-zinc-400 font-medium">Paper Trading</span>
              <span className={cn("font-mono font-bold text-sm", trading.day_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                {trading.day_pnl >= 0 ? "+" : ""}₹{trading.day_pnl?.toFixed(2)}
              </span>
              <span className="text-zinc-600">{trading.day_trades} trades</span>
              {trading.open_position_count > 0 && <span className="text-blue-400">{trading.open_position_count} open</span>}
            </div>
            <span className="text-[11px] text-zinc-600 group-hover:text-zinc-400 transition-colors">View details →</span>
          </Link>
        )}

        {/* Market context */}
        <MarketContext />

        {/* Instrument cards */}
        {hasPreds ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {predictions.map(p => <InstrumentCard key={p.instrument} pred={p} seq={updateSeq} />)}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[0, 1, 2].map(i => (
              <div key={i} className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] p-4 space-y-4 animate-pulse">
                <div className="flex justify-between"><div className="h-5 w-28 bg-zinc-800/60 rounded" /><div className="h-6 w-16 bg-zinc-800/60 rounded" /></div>
                <div className="h-8 w-36 bg-zinc-800/60 rounded" />
                <div className="h-1 w-full bg-zinc-800/60 rounded-full" />
                <div className="space-y-1.5"><div className="h-3 w-full bg-zinc-800/40 rounded" /><div className="h-3 w-3/4 bg-zinc-800/40 rounded" /></div>
              </div>
            ))}
          </div>
        )}

        {/* Pipeline runs + system */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Pipeline activity */}
          <div className="lg:col-span-2 rounded-xl border border-zinc-800/40 bg-[#0c0c11] overflow-hidden">
            <div className="px-4 py-2.5 border-b border-zinc-800/30 flex items-center justify-between">
              <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-[0.08em]">Pipeline Runs</span>
              <span className="text-[10px] text-zinc-600 font-mono">{activity.length} cycles</span>
            </div>
            {!activity.length ? (
              <div className="px-4 py-6 text-center text-zinc-600 text-xs">Waiting for first pipeline cycle...</div>
            ) : (
              <div className="max-h-[240px] overflow-y-auto divide-y divide-zinc-800/20">
                {[...activity].reverse().map((a, i) => {
                  const isOk = a.status === "ok";
                  const time = a.timestamp?.split("T")[1]?.substring(0, 8) ?? "";
                  const nextAt = a.next_run_at ?? 0;
                  const rem = i === 0 && nextAt > 0 ? Math.max(0, Math.floor(nextAt - Date.now() / 1000)) : 0;
                  return (
                    <div key={a.run_id || a.cycle} className={cn("px-4 py-2 text-xs", i === 0 && "bg-blue-500/[0.02]")}>
                      <div className="flex items-center gap-2">
                        {isOk ? <CheckCircle2 className="h-3 w-3 text-emerald-500 shrink-0" /> : <XCircle className="h-3 w-3 text-red-500 shrink-0" />}
                        <span className="font-mono text-zinc-400 tabular-nums">{time}</span>
                        <span className="text-zinc-600">#{a.cycle}</span>
                        {a.duration_sec != null && <span className="text-zinc-700 font-mono">{a.duration_sec}s</span>}
                        {a.predictions && Object.entries(a.predictions).map(([t, p]: [string, any]) => (
                          <span key={t} className={cn("font-mono font-bold tabular-nums",
                            p.direction === "LONG" ? "text-emerald-400" : p.direction === "SHORT" ? "text-red-400" : "text-zinc-600")}>
                            {INST[t]?.label?.split(" ")[0] ?? t}:{p.score > 0 ? "+" : ""}{p.score?.toFixed(2)}
                          </span>
                        ))}
                        {i === 0 && rem > 0 && (
                          <span className="text-amber-400 font-mono tabular-nums ml-auto flex items-center gap-1">
                            <Timer className="h-3 w-3" />{fmtDur(rem)}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* System status */}
          <div className="rounded-xl border border-zinc-800/40 bg-[#0c0c11] p-4 space-y-3">
            <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-[0.08em]">System</span>
            {status && (
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                <div className="flex justify-between"><span className="text-zinc-500">Session</span><span className="text-zinc-300">{status.market.session}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Trading</span><span className={status.market.can_trade ? "text-emerald-400" : "text-zinc-600"}>{status.market.can_trade ? "Yes" : "No"}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Holiday</span><span className={status.market.is_holiday ? "text-amber-400" : "text-zinc-600"}>{status.market.is_holiday ? "Yes" : "No"}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Cycles</span><span className="text-zinc-300 font-mono">{status.server.collection_count}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Redis</span><span className={status.server.db.redis ? "text-emerald-400" : "text-red-400"}>●</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">TimescaleDB</span><span className={status.server.db.timescaledb ? "text-emerald-400" : "text-red-400"}>●</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">WS Clients</span><span className="text-zinc-300">{status.server.ws_clients}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Broker</span><span className="text-zinc-300">{trading?.broker ?? "—"}</span></div>
                {status.server.errors?.length > 0 && (
                  <div className="col-span-2 text-red-400 text-[10px]">{status.server.errors.length} errors</div>
                )}
              </div>
            )}
          </div>
        </div>
      </main>

      <BottomBar />
    </div>
  );
}
