"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useStore, type TradingStatus } from "@/lib/ws";
import { cn } from "@/lib/cn";
import {
  ArrowLeft, Zap, Activity, TrendingUp, TrendingDown,
  ChevronDown, ChevronRight, DollarSign, Brain, Layers, Timer, Shield,
  Target, BarChart3, ArrowUpRight, ArrowDownRight, Radio,
  CheckCircle2, XCircle, Calendar, Trophy, Minus,
} from "lucide-react";

/* ── Helpers ──────────────────────────────────────────────────── */

function useTick(ms = 1000) {
  const [, s] = useState(0);
  useEffect(() => { const i = setInterval(() => s(t => t + 1), ms); return () => clearInterval(i); }, [ms]);
}

const N: Record<string, string> = { NIFTYBEES: "Nifty", BANKBEES: "Bank", SETFNIF50: "SBI" };

function fmtMoney(n: number): string {
  if (Math.abs(n) >= 100000) return `₹${(n / 100000).toFixed(2)}L`;
  if (Math.abs(n) >= 1000) return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${n.toFixed(2)}`;
}

/* ── Data Hooks ───────────────────────────────────────────────── */

function useMomentum() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    const f = () => fetch("/api/trading/momentum").then(r => r.json()).then(d => { if (!d.error) setData(d); }).catch(() => {});
    f(); const i = setInterval(f, 10000); return () => clearInterval(i);
  }, []);
  const wsMom = useStore(s => s.momentum);
  return { momentum: wsMom ?? data?.momentum, fastLoopCount: data?.fast_loop_count ?? 0, fastInterval: data?.fast_loop_interval ?? 30 };
}

function useDayResult() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    const f = () => fetch("/api/trading/day-result").then(r => r.json()).then(d => { if (!d.error) setData(d); }).catch(() => {});
    f(); const i = setInterval(f, 5000); return () => clearInterval(i);
  }, []);
  return data;
}

function useTradeHistory() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    fetch("/api/trade-history").then(r => r.json()).then(d => setData(d)).catch(() => {});
  }, []);
  return data;
}

function useFeedStatus() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    const f = () => fetch("/api/feed-status").then(r => r.json()).then(d => setData(d)).catch(() => {});
    f(); const i = setInterval(f, 15000); return () => clearInterval(i);
  }, []);
  return data;
}

function useAccuracy() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    fetch("/api/accuracy").then(r => r.json()).then(d => setData(d)).catch(() => {});
  }, []);
  return data;
}

/* ── Main Trades Page ─────────────────────────────────────────── */

export default function TradesPage() {
  useTick();
  const { trading, connected, predictions, status } = useStore();
  const [rest, setRest] = useState<TradingStatus | null>(null);
  useEffect(() => {
    const f = () => fetch("/api/trading").then(r => r.json()).then(d => { if (!d.error) setRest(d); }).catch(() => {});
    f(); const i = setInterval(f, 3000); return () => clearInterval(i);
  }, []);
  const t = trading ?? rest;
  const { momentum, fastLoopCount, fastInterval } = useMomentum();
  const dayResult = useDayResult();
  const tradeHistory = useTradeHistory();
  const feed = useFeedStatus();
  const accuracy = useAccuracy();
  const session = status?.market?.session ?? "closed";
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);
  const now = mounted ? new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }) : "--:--:--";

  if (!t) return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
      <Activity className="h-6 w-6 animate-pulse text-zinc-600" />
    </div>
  );

  const netEquity = t.capital + (t.total_unrealized_pnl ?? 0);
  const grossPnl = t.day_pnl + t.day_charges;

  // Compute invested amount from positions
  const invested = Object.values(t.positions).reduce((sum: number, pos: any) => {
    return sum + (pos.entry_price ?? 0) * (pos.quantity ?? 0);
  }, 0);
  // Include closed trade invested amounts
  const closedInvested = (t.closed_trades ?? []).reduce((sum: number, tr: any) => {
    return sum + (tr.entry_price ?? 0) * (tr.quantity ?? 0);
  }, 0);
  const totalInvested = invested + closedInvested;
  const returnOnInvested = totalInvested > 0 ? (t.day_pnl / totalInvested) * 100 : 0;

  // Cumulative trade history stats
  const histDays = tradeHistory?.daily_results ?? tradeHistory?.results ?? [];
  const cumStats = tradeHistory?.cumulative ?? tradeHistory?.stats ?? null;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 font-sans flex flex-col">

      {/* ━━━ TOP BAR ━━━ */}
      <header className="h-10 bg-zinc-950 border-b border-zinc-800/50 px-3 flex items-center gap-2 text-[11px] sticky top-0 z-50">
        <Link href="/" className="text-zinc-400 hover:text-zinc-100 transition-colors flex items-center gap-1">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <Zap className="h-4 w-4 text-blue-500" />
        <span className="font-black text-sm tracking-tight text-zinc-50">TRADE+</span>
        <span className="text-zinc-600 text-xs">Trades</span>

        <div className="flex-1" />

        <span className={cn("px-2 py-0.5 rounded text-[9px] font-black tracking-widest",
          session === "regular" ? "text-emerald-400 bg-emerald-500/10 border border-emerald-500/20" :
          session === "pre_market" ? "text-amber-400 bg-amber-500/10 border border-amber-500/20" :
          "text-zinc-500 bg-zinc-900 border border-zinc-800")}>
          {session === "regular" ? "LIVE" : session === "pre_market" ? "PRE-MKT" : "CLOSED"}
        </span>
        <span className="font-mono tabular-nums text-zinc-400 text-xs">{now}</span>

        <div className="h-4 w-px bg-zinc-800 mx-1" />

        <span className={cn("font-mono font-bold text-sm tabular-nums", t.day_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
          {t.day_pnl >= 0 ? "+" : ""}₹{t.day_pnl?.toFixed(2)}
        </span>
        <span className="text-zinc-600 text-[10px] font-mono">{t.day_trades}t {t.open_position_count}p</span>
        <span className={cn("h-2 w-2 rounded-full", connected ? "bg-emerald-500" : "bg-red-500")} />
      </header>

      <div className="flex-1 max-w-[1600px] mx-auto w-full px-3 py-2 space-y-2">

        {/* ━━━ SECTION 1: Today's P&L Hero ━━━ */}
        <div className={cn("rounded border p-4 relative overflow-hidden",
          t.day_pnl >= 0
            ? "bg-gradient-to-br from-emerald-500/[0.06] to-zinc-900 border-emerald-500/15"
            : "bg-gradient-to-br from-red-500/[0.06] to-zinc-900 border-red-500/15")}>
          <div className="flex items-start justify-between">
            <div>
              <p className="text-[9px] text-zinc-500 uppercase tracking-widest mb-1">Today's Net P&L</p>
              <p className={cn("text-4xl font-black font-mono tabular-nums leading-none tracking-tight",
                t.day_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                {t.day_pnl >= 0 ? "+" : ""}₹{t.day_pnl?.toFixed(2)}
              </p>
            </div>
            {/* Win/Loss badge */}
            <div className="text-right">
              <div className="flex items-center gap-2">
                <span className="text-emerald-400 font-mono text-sm font-bold">{t.day_wins}W</span>
                <span className="text-zinc-700">/</span>
                <span className="text-red-400 font-mono text-sm font-bold">{t.day_losses}L</span>
              </div>
              <p className="text-[10px] text-zinc-500 font-mono mt-0.5">
                {t.day_trades > 0 ? `${(t.win_rate * 100).toFixed(0)}% Win Rate` : "No trades"}
              </p>
            </div>
          </div>

          {/* Breakdown row */}
          <div className="flex gap-4 mt-3 text-[10px]">
            <KV l="Invested" v={totalInvested > 0 ? `₹${totalInvested.toFixed(0)}` : "---"} />
            <KV l="Gross P&L" v={`₹${grossPnl.toFixed(2)}`} c={grossPnl >= 0 ? "text-emerald-400/70" : "text-red-400/70"} />
            <KV l="Charges" v={`₹${t.day_charges.toFixed(2)}`} c="text-amber-400/70" />
            <KV l="Net P&L" v={`${t.day_pnl >= 0 ? "+" : ""}₹${t.day_pnl.toFixed(2)}`} c={t.day_pnl >= 0 ? "text-emerald-400" : "text-red-400"} />
            <KV l="Return/Invested" v={totalInvested > 0 ? `${returnOnInvested >= 0 ? "+" : ""}${returnOnInvested.toFixed(2)}%` : "---"} c={returnOnInvested >= 0 ? "text-emerald-400/70" : "text-red-400/70"} />
            <KV l="Capital" v={`₹${t.capital.toFixed(0)}`} />
            <KV l="Drawdown" v={`${(t.max_drawdown * 100).toFixed(1)}%`} c={t.max_drawdown > 0.02 ? "text-amber-400" : "text-zinc-400"} />
          </div>
          {dayResult && (
            <div className="flex gap-4 mt-1 text-[10px]">
              <KV l="Start Capital" v={`₹${dayResult.starting_capital?.toFixed(0)}`} />
              <KV l="End Capital" v={`₹${dayResult.ending_capital?.toFixed(0)}`} />
            </div>
          )}
        </div>

        {/* ━━━ SECTION 2: Open Positions ━━━ */}
        <div className="bg-zinc-900 border border-zinc-800/30 rounded overflow-hidden">
          <div className="px-3 py-1.5 border-b border-zinc-800/20 flex items-center justify-between text-[10px]">
            <span className="text-zinc-500 font-semibold uppercase tracking-wider">Open Positions</span>
            <span className={cn("font-mono font-bold", t.total_unrealized_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
              {t.total_unrealized_pnl >= 0 ? "+" : ""}₹{t.total_unrealized_pnl?.toFixed(2)} unrealized
            </span>
          </div>
          {Object.keys(t.positions).length === 0 ? (
            <div className="p-3 text-center text-[10px] text-zinc-700">No open positions</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-[9px] text-zinc-600 uppercase tracking-wider border-b border-zinc-800/10">
                    <th className="text-left py-1 px-3 font-medium">Instrument</th>
                    <th className="text-left py-1 px-2 font-medium">Side</th>
                    <th className="text-right py-1 px-2 font-medium">Qty</th>
                    <th className="text-right py-1 px-2 font-medium">Entry</th>
                    <th className="text-right py-1 px-2 font-medium">Current</th>
                    <th className="text-right py-1 px-2 font-medium">Unrlz P&L</th>
                    <th className="text-right py-1 px-2 font-medium">P&L%</th>
                    <th className="text-right py-1 px-3 font-medium">HWM</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(t.positions).map(([inst, pos]: [string, any]) => {
                    const pnlPct = pos.entry_price > 0 ? ((pos.current_price - pos.entry_price) / pos.entry_price * 100 * (pos.side === "SHORT" ? -1 : 1)) : 0;
                    return (
                      <tr key={inst} className="border-t border-zinc-800/10 hover:bg-zinc-800/10">
                        <td className="py-1.5 px-3 font-semibold text-zinc-200">{N[inst] ?? inst}</td>
                        <td className="py-1.5 px-2"><SideBadge s={pos.side} /></td>
                        <td className="py-1.5 px-2 text-right font-mono text-zinc-400">{pos.quantity}</td>
                        <td className="py-1.5 px-2 text-right font-mono text-zinc-500">₹{pos.entry_price?.toFixed(2)}</td>
                        <td className="py-1.5 px-2 text-right font-mono text-zinc-300">₹{pos.current_price?.toFixed(2)}</td>
                        <td className={cn("py-1.5 px-2 text-right font-mono font-bold", pos.unrealized_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                          {pos.unrealized_pnl >= 0 ? "+" : ""}₹{pos.unrealized_pnl?.toFixed(2)}
                        </td>
                        <td className={cn("py-1.5 px-2 text-right font-mono", pnlPct >= 0 ? "text-emerald-400/70" : "text-red-400/70")}>
                          {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
                        </td>
                        <td className="py-1.5 px-3 text-right font-mono text-zinc-600">{pos.hwm?.toFixed(2) ?? "---"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ━━━ SECTION 3: Today's Closed Trades ━━━ */}
        <div className="bg-zinc-900 border border-zinc-800/30 rounded overflow-hidden">
          <div className="px-3 py-1.5 border-b border-zinc-800/20 flex items-center justify-between text-[10px]">
            <span className="text-zinc-500 font-semibold uppercase tracking-wider">
              Closed Trades <span className="text-zinc-600 font-mono font-normal ml-1">{t.closed_trades?.length ?? 0}</span>
            </span>
            {t.closed_trades?.length > 0 && (() => {
              const totalPnl = t.closed_trades.reduce((s: number, tr: any) => s + (tr.net_pnl ?? 0), 0);
              return <span className={cn("font-mono font-bold", totalPnl >= 0 ? "text-emerald-400" : "text-red-400")}>{totalPnl >= 0 ? "+" : ""}₹{totalPnl.toFixed(2)}</span>;
            })()}
          </div>
          {!t.closed_trades?.length ? (
            <div className="p-3 text-center text-[10px] text-zinc-700">No completed trades yet</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-[9px] text-zinc-600 uppercase tracking-wider border-b border-zinc-800/10">
                    <th className="text-left py-1 px-3 font-medium">Time</th>
                    <th className="text-left py-1 px-2 font-medium">Inst</th>
                    <th className="text-left py-1 px-2 font-medium">Side</th>
                    <th className="text-right py-1 px-2 font-medium">Qty</th>
                    <th className="text-right py-1 px-2 font-medium">Entry</th>
                    <th className="text-right py-1 px-2 font-medium">Exit</th>
                    <th className="text-right py-1 px-2 font-medium">Hold</th>
                    <th className="text-right py-1 px-2 font-medium">Gross</th>
                    <th className="text-right py-1 px-2 font-medium">Charges</th>
                    <th className="text-right py-1 px-2 font-medium">Net P&L</th>
                    <th className="text-right py-1 px-3 font-medium">Return%</th>
                  </tr>
                </thead>
                <tbody>
                  {[...t.closed_trades].reverse().map((trade: any, i: number) => (
                    <ClosedTradeRow key={i} trade={trade} />
                  ))}
                  {/* Totals row */}
                  {t.closed_trades.length > 1 && (() => {
                    const totGross = t.closed_trades.reduce((s: number, tr: any) => s + (tr.gross_pnl ?? 0), 0);
                    const totCharges = t.closed_trades.reduce((s: number, tr: any) => s + (tr.charges ?? 0), 0);
                    const totNet = t.closed_trades.reduce((s: number, tr: any) => s + (tr.net_pnl ?? 0), 0);
                    return (
                      <tr className="border-t border-zinc-700/50 bg-zinc-800/20 font-bold text-[10px]">
                        <td className="py-1.5 px-3 text-zinc-400" colSpan={7}>TOTAL</td>
                        <td className={cn("py-1.5 px-2 text-right font-mono", totGross >= 0 ? "text-emerald-400/70" : "text-red-400/70")}>₹{totGross.toFixed(2)}</td>
                        <td className="py-1.5 px-2 text-right font-mono text-amber-400/70">₹{totCharges.toFixed(2)}</td>
                        <td className={cn("py-1.5 px-2 text-right font-mono", totNet >= 0 ? "text-emerald-400" : "text-red-400")}>{totNet >= 0 ? "+" : ""}₹{totNet.toFixed(2)}</td>
                        <td className="py-1.5 px-3" />
                      </tr>
                    );
                  })()}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ━━━ SECTION 3.5: Orders ━━━ */}
        <div className="bg-zinc-900 border border-zinc-800/30 rounded overflow-hidden">
          <div className="px-3 py-1.5 border-b border-zinc-800/20 flex items-center justify-between text-[10px]">
            <span className="text-zinc-500 font-semibold uppercase tracking-wider">
              Orders <span className="text-zinc-600 font-mono font-normal ml-1">{t.recent_orders?.length ?? 0}</span>
            </span>
            {t.recent_orders?.length > 0 && (() => {
              const totalCharges = t.recent_orders.reduce((s: number, o: any) => s + (o.charges ?? 0), 0);
              return <span className="text-zinc-600 font-mono">₹{totalCharges.toFixed(2)} charges</span>;
            })()}
          </div>
          {!t.recent_orders?.length ? (
            <div className="p-3 text-center text-[10px] text-zinc-700">No orders today</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-[9px] text-zinc-600 uppercase tracking-wider border-b border-zinc-800/10">
                    <th className="text-left py-1 px-3 font-medium">Time</th>
                    <th className="text-left py-1 px-2 font-medium">Inst</th>
                    <th className="text-left py-1 px-2 font-medium">Side</th>
                    <th className="text-right py-1 px-2 font-medium">Qty</th>
                    <th className="text-right py-1 px-2 font-medium">Signal</th>
                    <th className="text-right py-1 px-2 font-medium">Fill</th>
                    <th className="text-right py-1 px-2 font-medium">Charges</th>
                    <th className="text-right py-1 px-3 font-medium">P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {[...t.recent_orders].reverse().map((o: any, i: number) => {
                    const time = fmtTime(o.placed_at);
                    return (
                      <tr key={i} className="border-t border-zinc-800/10 hover:bg-zinc-800/10">
                        <td className="py-1 px-3 font-mono text-zinc-500">{time}</td>
                        <td className="py-1 px-2 text-zinc-300">{N[o.instrument] ?? o.instrument}</td>
                        <td className="py-1 px-2"><SideBadge s={o.side} /></td>
                        <td className="py-1 px-2 text-right font-mono text-zinc-500">{o.quantity}</td>
                        <td className="py-1 px-2 text-right font-mono text-zinc-500">₹{o.signal_price?.toFixed(2)}</td>
                        <td className="py-1 px-2 text-right font-mono text-zinc-300">₹{o.fill_price?.toFixed(2)}</td>
                        <td className="py-1 px-2 text-right font-mono text-amber-400/70">₹{o.charges?.toFixed(2)}</td>
                        <td className="py-1 px-3 text-right">
                          {o.pnl != null
                            ? <span className={cn("font-mono font-bold", o.pnl >= 0 ? "text-emerald-400" : "text-red-400")}>{o.pnl >= 0 ? "+" : ""}₹{o.pnl?.toFixed(2)}</span>
                            : <span className="text-zinc-700">---</span>
                          }
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ━━━ SECTION 4: Trade History (Daily Breakdown) ━━━ */}
        <div className="bg-zinc-900 border border-zinc-800/30 rounded overflow-hidden">
          <div className="px-3 py-1.5 border-b border-zinc-800/20 flex items-center justify-between text-[10px]">
            <div className="flex items-center gap-2">
              <Calendar className="h-3 w-3 text-blue-500/60" />
              <span className="text-zinc-500 font-semibold uppercase tracking-wider">Trade History</span>
            </div>
            <Link href="/trades/history" className="text-[10px] text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1">
              Full History →
            </Link>
          </div>

          {/* Cumulative stats strip */}
          {cumStats && (
            <div className="px-3 py-2 border-b border-zinc-800/20 flex gap-4 text-[10px] flex-wrap">
              {cumStats.total_days != null && <KV l="Total Days" v={cumStats.total_days} />}
              {cumStats.win_days != null && <KV l="Win Days" v={cumStats.win_days} c="text-emerald-400/70" />}
              {cumStats.loss_days != null && <KV l="Loss Days" v={cumStats.loss_days} c="text-red-400/70" />}
              {cumStats.win_rate != null && <KV l="Day Win%" v={`${(cumStats.win_rate * 100).toFixed(0)}%`} c={cumStats.win_rate > 0.5 ? "text-emerald-400" : "text-amber-400"} />}
              {cumStats.total_pnl != null && <KV l="Total P&L" v={`${cumStats.total_pnl >= 0 ? "+" : ""}₹${cumStats.total_pnl.toFixed(2)}`} c={cumStats.total_pnl >= 0 ? "text-emerald-400" : "text-red-400"} />}
              {cumStats.total_trades != null && <KV l="Total Trades" v={cumStats.total_trades} />}
              {cumStats.avg_daily_pnl != null && <KV l="Avg Daily" v={`${cumStats.avg_daily_pnl >= 0 ? "+" : ""}₹${cumStats.avg_daily_pnl.toFixed(2)}`} c={cumStats.avg_daily_pnl >= 0 ? "text-emerald-400/70" : "text-red-400/70"} />}
              {cumStats.total_charges != null && <KV l="Total Charges" v={`₹${cumStats.total_charges.toFixed(2)}`} c="text-amber-400/70" />}
              {cumStats.max_drawdown != null && <KV l="Max DD" v={`${(cumStats.max_drawdown * 100).toFixed(1)}%`} c="text-amber-400" />}
              {cumStats.sharpe != null && <KV l="Sharpe" v={cumStats.sharpe.toFixed(2)} />}
            </div>
          )}

          {/* Daily results table */}
          {histDays.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-[9px] text-zinc-600 uppercase tracking-wider border-b border-zinc-800/10">
                    <th className="text-left py-1 px-3 font-medium w-5" />
                    <th className="text-left py-1 px-2 font-medium">Date</th>
                    <th className="text-left py-1 px-2 font-medium">Day</th>
                    <th className="text-right py-1 px-2 font-medium">Trades</th>
                    <th className="text-center py-1 px-2 font-medium">W/L</th>
                    <th className="text-right py-1 px-2 font-medium">Win%</th>
                    <th className="text-right py-1 px-2 font-medium">Invested</th>
                    <th className="text-right py-1 px-2 font-medium">Net P&L</th>
                    <th className="text-right py-1 px-2 font-medium">Charges</th>
                    <th className="text-right py-1 px-3 font-medium">Return%</th>
                  </tr>
                </thead>
                <tbody>
                  {[...histDays].reverse().map((day: any, i: number) => (
                    <DayRow key={day.date ?? i} day={day} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-3 text-center text-[10px] text-zinc-700">No historical data available</div>
          )}
        </div>

        {/* ━━━ SECTION 5: Engine Status + Accuracy ━━━ */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
          {/* Engine Status */}
          <div className="bg-zinc-900 border border-zinc-800/30 rounded overflow-hidden">
            <div className="px-3 py-1.5 border-b border-zinc-800/20 flex items-center gap-2 text-[10px]">
              <Brain className="h-3 w-3 text-blue-500/70" />
              <span className="text-zinc-500 font-semibold uppercase tracking-wider">Engine Status</span>
            </div>
            <div className="p-3 space-y-1 text-[11px]">
              {momentum ? <>
                <SR l="Mode" v={momentum.mode} />
                <SR l="Time Window" v={momentum.time_window?.toUpperCase() ?? "---"} c={momentum.time_window === "prime" ? "text-emerald-400" : momentum.time_window === "orb" ? "text-amber-400" : undefined} />
                <SR l="Levels" v={momentum.levels_computed ? "Computed" : "Pending"} c={momentum.levels_computed ? "text-emerald-400" : "text-zinc-600"} />
                <SR l="ORB" v={momentum.orb_set ? "Set" : "Pending"} c={momentum.orb_set ? "text-emerald-400" : "text-zinc-600"} />
                <SR l="Fast Loop" v={`${fastLoopCount} runs . ${fastInterval}s interval`} />
                {momentum.bias_direction && <SR l="Bias" v={`${momentum.bias_direction} (${momentum.bias_confidence?.toFixed(0)}%)`} c={momentum.bias_direction === "LONG" ? "text-emerald-400" : momentum.bias_direction === "SHORT" ? "text-red-400" : undefined} />}
              </> : <span className="text-zinc-700">Loading...</span>}

              {feed && (
                <div className="border-t border-zinc-800/20 pt-1 mt-1">
                  <SR l="Feed Source" v={feed.source ?? feed.feed_type ?? "---"} />
                  {feed.status && <SR l="Feed Status" v={feed.status} c={feed.status === "connected" ? "text-emerald-400" : "text-amber-400"} />}
                  {feed.last_price_at && <SR l="Last Price" v={new Date(feed.last_price_at * 1000).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false })} />}
                </div>
              )}

              {status && (
                <div className="border-t border-zinc-800/20 pt-1 mt-1">
                  <SR l="Trading" v={status.market.can_trade ? "Active" : "Inactive"} c={status.market.can_trade ? "text-emerald-400" : "text-zinc-600"} />
                  <SR l="Redis" v={status.server.db.redis ? "OK" : "Down"} c={status.server.db.redis ? "text-emerald-400" : "text-red-400"} />
                  <SR l="TSDB" v={status.server.db.timescaledb ? "OK" : "Down"} c={status.server.db.timescaledb ? "text-emerald-400" : "text-red-400"} />
                  <SR l="Broker" v={t.broker ?? "---"} />
                  <SR l="Leverage" v={`${t.leverage}x`} />
                </div>
              )}
            </div>
          </div>

          {/* Accuracy */}
          <div className="bg-zinc-900 border border-zinc-800/30 rounded overflow-hidden">
            <div className="px-3 py-1.5 border-b border-zinc-800/20 flex items-center gap-2 text-[10px]">
              <Shield className="h-3 w-3 text-blue-500/60" />
              <span className="text-zinc-500 font-semibold uppercase tracking-wider">Accuracy Tracker</span>
            </div>
            {accuracy && Object.keys(accuracy).length > 0 ? (
              <div className="grid grid-cols-3 divide-x divide-zinc-800/10">
                {Object.entries(accuracy).map(([inst, acc]: [string, any]) => (
                  <div key={inst} className="px-3 py-2">
                    <p className="text-[11px] font-semibold text-zinc-300 mb-1">{N[inst] ?? inst}</p>
                    {acc.overall && Object.keys(acc.overall).length > 0 ? (
                      <div className="space-y-0.5 text-[10px]">
                        {acc.overall.total_trades != null && <SR l="Trades" v={acc.overall.total_trades} />}
                        {acc.overall.win_rate != null && <SR l="Win Rate" v={`${(acc.overall.win_rate * 100).toFixed(0)}%`} c={acc.overall.win_rate > 0.5 ? "text-emerald-400" : "text-amber-400"} />}
                        {acc.overall.avg_rr != null && <SR l="Avg R:R" v={acc.overall.avg_rr?.toFixed(2)} />}
                        {acc.overall.expectancy != null && <SR l="Expectancy" v={acc.overall.expectancy?.toFixed(2)} />}
                        {acc.overall.sharpe != null && <SR l="Sharpe" v={acc.overall.sharpe?.toFixed(2)} />}
                      </div>
                    ) : (
                      <p className="text-[10px] text-zinc-700">No data</p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-3 text-center text-[10px] text-zinc-700">No accuracy data</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Shared Components ────────────────────────────────────────── */

function KV({ l, v, c }: { l: string; v: any; c?: string }) {
  return (
    <div>
      <span className="text-zinc-600">{l} </span>
      <span className={cn("font-mono font-semibold", c ?? "text-zinc-300")}>{v}</span>
    </div>
  );
}

function SR({ l, v, c }: { l: string; v: any; c?: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-zinc-600">{l}</span>
      <span className={cn("font-mono", c ?? "text-zinc-300")}>{v}</span>
    </div>
  );
}

function SideBadge({ s }: { s: string }) {
  return (
    <span className={cn("text-[9px] font-bold px-1.5 py-px rounded inline-block",
      s === "BUY" || s === "LONG" ? "text-emerald-400 bg-emerald-500/10" : "text-red-400 bg-red-500/10")}>
      {s}
    </span>
  );
}

function fmtTime(v: any): string {
  if (!v) return "";
  if (typeof v === "string") return v; // already "HH:MM" from trade history
  if (typeof v === "number" && v > 1e9) {
    try { return new Date(v * 1000).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }); } catch { return ""; }
  }
  return String(v);
}

function calcHoldMin(entry: any, exit: any): string {
  if (!entry || !exit) return "?";
  if (typeof entry === "number" && typeof exit === "number" && entry > 1e9) return ((exit - entry) / 60).toFixed(0);
  return "?";
}

function ClosedTradeRow({ trade }: { trade: any }) {
  const [open, setOpen] = useState(false);
  const exitTime = fmtTime(trade.exit_time);
  const entryTime = fmtTime(trade.entry_time);
  const holdMin = trade.hold_minutes ?? calcHoldMin(trade.entry_time, trade.exit_time);
  const invested = (trade.entry_price ?? 0) * (trade.quantity ?? 0);
  const returnPct = invested > 0 ? ((trade.net_pnl ?? 0) / invested * 100) : 0;

  return (
    <>
      <tr className={cn("border-t border-zinc-800/10 cursor-pointer transition-colors",
        trade.net_pnl >= 0 ? "hover:bg-emerald-500/[0.03]" : "hover:bg-red-500/[0.03]")}
        onClick={() => setOpen(o => !o)}>
        <td className="py-1 px-3 font-mono text-zinc-500">{exitTime}</td>
        <td className="py-1 px-2 text-zinc-300">{N[trade.instrument] ?? trade.instrument}</td>
        <td className="py-1 px-2"><SideBadge s={trade.side} /></td>
        <td className="py-1 px-2 text-right font-mono text-zinc-500">{trade.quantity}</td>
        <td className="py-1 px-2 text-right font-mono text-zinc-500">₹{trade.entry_price?.toFixed(2)}</td>
        <td className="py-1 px-2 text-right font-mono text-zinc-300">₹{trade.exit_price?.toFixed(2)}</td>
        <td className="py-1 px-2 text-right text-zinc-600">{holdMin}m</td>
        <td className={cn("py-1 px-2 text-right font-mono", trade.gross_pnl >= 0 ? "text-emerald-400/70" : "text-red-400/70")}>₹{trade.gross_pnl?.toFixed(2)}</td>
        <td className="py-1 px-2 text-right font-mono text-amber-400/70">₹{trade.charges?.toFixed(2)}</td>
        <td className={cn("py-1 px-2 text-right font-mono font-bold", trade.net_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
          {trade.net_pnl >= 0 ? "+" : ""}₹{trade.net_pnl?.toFixed(2)}
        </td>
        <td className={cn("py-1 px-3 text-right font-mono text-[10px]", returnPct >= 0 ? "text-emerald-400/60" : "text-red-400/60")}>
          {returnPct >= 0 ? "+" : ""}{returnPct.toFixed(2)}%
        </td>
      </tr>
      {open && (
        <tr className="border-t border-zinc-800/5">
          <td colSpan={11} className="px-3 py-1.5 bg-zinc-800/10">
            <div className="text-[10px] text-zinc-500 space-y-0.5 ml-4">
              <p>Entry: ₹{trade.entry_price?.toFixed(2)} at {entryTime}</p>
              <p>Exit: ₹{trade.exit_price?.toFixed(2)} at {exitTime}</p>
              <p>Invested: ₹{invested.toFixed(2)} | Gross: ₹{trade.gross_pnl?.toFixed(2)} | Charges: ₹{trade.charges?.toFixed(2)} | Net: {trade.net_pnl >= 0 ? "+" : ""}₹{trade.net_pnl?.toFixed(2)}</p>
              {trade.reason && <p>Reason: <span className="text-zinc-400">{trade.reason}</span></p>}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function DayRow({ day }: { day: any }) {
  const [open, setOpen] = useState(false);
  const [dayTrades, setDayTrades] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);

  const toggleOpen = () => {
    if (!open && !dayTrades && day.date) {
      setLoading(true);
      fetch(`/api/trade-history/${day.date}`)
        .then(r => r.json())
        .then(d => { setDayTrades(d.trades ?? d.closed_trades ?? []); setLoading(false); })
        .catch(() => { setDayTrades([]); setLoading(false); });
    }
    setOpen(o => !o);
  };

  const netPnl = day.net_pnl ?? day.pnl ?? 0;
  const charges = day.charges ?? day.total_charges ?? 0;
  const trades = day.total_trades ?? day.trades ?? 0;
  const wins = day.wins ?? day.win_count ?? 0;
  const losses = day.losses ?? day.loss_count ?? 0;
  const winRate = trades > 0 ? (wins / trades * 100) : 0;
  const invested = day.invested ?? day.total_invested ?? 0;
  const returnPct = invested > 0 ? (netPnl / invested * 100) : (day.return_pct ?? 0);

  // Get day of week from date string
  let dayName = "";
  if (day.date) {
    try {
      const d = new Date(day.date + "T00:00:00");
      dayName = d.toLocaleDateString("en-IN", { weekday: "short" });
    } catch {}
  }

  return (
    <>
      <tr className={cn("border-t border-zinc-800/10 cursor-pointer transition-colors hover:bg-zinc-800/10")}
        onClick={toggleOpen}>
        <td className="py-1 px-3">
          <ChevronRight className={cn("h-3 w-3 text-zinc-600 transition-transform", open && "rotate-90")} />
        </td>
        <td className="py-1 px-2 font-mono text-zinc-400">{day.date}</td>
        <td className="py-1 px-2 text-zinc-600">{day.day ?? dayName}</td>
        <td className="py-1 px-2 text-right font-mono text-zinc-400">{trades}</td>
        <td className="py-1 px-2 text-center">
          <span className="text-emerald-400/70 font-mono">{wins}</span>
          <span className="text-zinc-700">/</span>
          <span className="text-red-400/70 font-mono">{losses}</span>
        </td>
        <td className={cn("py-1 px-2 text-right font-mono", winRate >= 50 ? "text-emerald-400/70" : winRate > 0 ? "text-red-400/70" : "text-zinc-600")}>
          {trades > 0 ? `${winRate.toFixed(0)}%` : "---"}
        </td>
        <td className="py-1 px-2 text-right font-mono text-zinc-500">
          {invested > 0 ? `₹${invested.toFixed(0)}` : "---"}
        </td>
        <td className={cn("py-1 px-2 text-right font-mono font-bold", netPnl >= 0 ? "text-emerald-400" : "text-red-400")}>
          {netPnl >= 0 ? "+" : ""}₹{netPnl.toFixed(2)}
        </td>
        <td className="py-1 px-2 text-right font-mono text-amber-400/70">₹{charges.toFixed(2)}</td>
        <td className={cn("py-1 px-3 text-right font-mono", returnPct >= 0 ? "text-emerald-400/60" : "text-red-400/60")}>
          {returnPct !== 0 ? `${returnPct >= 0 ? "+" : ""}${returnPct.toFixed(2)}%` : "---"}
        </td>
      </tr>
      {open && (
        <tr className="border-t border-zinc-800/5">
          <td colSpan={10} className="bg-zinc-800/10 px-3 py-2">
            {loading ? (
              <div className="text-[10px] text-zinc-600 flex items-center gap-1"><Activity className="h-3 w-3 animate-pulse" /> Loading trades...</div>
            ) : dayTrades && dayTrades.length > 0 ? (
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-[8px] text-zinc-600 uppercase tracking-wider">
                    <th className="text-left py-0.5 px-2 font-medium">Time</th>
                    <th className="text-left py-0.5 px-2 font-medium">Inst</th>
                    <th className="text-left py-0.5 px-2 font-medium">Side</th>
                    <th className="text-right py-0.5 px-2 font-medium">Entry</th>
                    <th className="text-right py-0.5 px-2 font-medium">Exit</th>
                    <th className="text-right py-0.5 px-2 font-medium">Net P&L</th>
                    <th className="text-left py-0.5 px-2 font-medium">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {dayTrades.map((tr: any, i: number) => {
                    const exitT = fmtTime(tr.exit_time) || tr.exit_at || "";
                    return (
                      <tr key={i} className="border-t border-zinc-800/5">
                        <td className="py-0.5 px-2 font-mono text-zinc-600">{exitT}</td>
                        <td className="py-0.5 px-2 text-zinc-400">{N[tr.instrument] ?? tr.instrument}</td>
                        <td className="py-0.5 px-2"><SideBadge s={tr.side} /></td>
                        <td className="py-0.5 px-2 text-right font-mono text-zinc-600">₹{tr.entry_price?.toFixed(2)}</td>
                        <td className="py-0.5 px-2 text-right font-mono text-zinc-400">₹{tr.exit_price?.toFixed(2)}</td>
                        <td className={cn("py-0.5 px-2 text-right font-mono font-bold",
                          (tr.net_pnl ?? tr.pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                          {(tr.net_pnl ?? tr.pnl ?? 0) >= 0 ? "+" : ""}₹{(tr.net_pnl ?? tr.pnl ?? 0).toFixed(2)}
                        </td>
                        <td className="py-0.5 px-2 text-zinc-600 truncate max-w-[200px]">{tr.reason ?? "---"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p className="text-[10px] text-zinc-700">No trade details available</p>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
