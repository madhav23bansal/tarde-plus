"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useStore, type TradingStatus } from "@/lib/ws";
import { cn } from "@/lib/cn";
import {
  ArrowLeft, Zap, Activity, BarChart3, Target, AlertTriangle,
  Wallet, DollarSign, CheckCircle2, XCircle, ChevronRight, TrendingUp, TrendingDown,
} from "lucide-react";

function useTick(ms = 1000) { const [, s] = useState(0); useEffect(() => { const i = setInterval(() => s(t => t + 1), ms); return () => clearInterval(i); }, [ms]); }

const INST: Record<string, string> = { NIFTYBEES: "Nifty 50", BANKBEES: "Bank Nifty", SETFNIF50: "SBI Nifty" };

export default function TradesPage() {
  useTick();
  const { trading, connected } = useStore();
  const [rest, setRest] = useState<TradingStatus | null>(null);
  useEffect(() => {
    const f = () => fetch("/api/trading").then(r => r.json()).then(d => { if (!d.error) setRest(d); }).catch(() => {});
    f(); const i = setInterval(f, 3000); return () => clearInterval(i);
  }, []);
  const t = trading ?? rest;

  return (
    <div className="min-h-screen bg-[#08080c] text-zinc-100 font-sans">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[#0a0a0f]/95 backdrop-blur-md border-b border-zinc-800/60">
        <div className="max-w-[1440px] mx-auto px-5 h-12 flex items-center gap-4 text-xs">
          <Link href="/" className="flex items-center gap-1.5 text-zinc-400 hover:text-zinc-200 transition-colors">
            <ArrowLeft className="h-4 w-4" /><span>Dashboard</span>
          </Link>
          <span className="text-zinc-800">|</span>
          <Zap className="h-4 w-4 text-blue-500" />
          <span className="font-bold text-base text-zinc-100">Trades</span>
          {t && <span className={cn("ml-2 font-mono font-bold text-sm", t.day_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
            {t.day_pnl >= 0 ? "+" : ""}₹{t.day_pnl?.toFixed(2)}
          </span>}
          <span className="ml-auto text-zinc-600 font-mono">₹{t?.capital?.toFixed(0) ?? "50,000"} · {t?.broker ?? "shoonya"}</span>
        </div>
      </header>

      <main className="max-w-[1440px] mx-auto px-5 py-5 space-y-5">
        {!t ? (
          <div className="flex flex-col items-center justify-center py-24 gap-3 text-zinc-500">
            <Activity className="h-8 w-8 animate-pulse" />
            <p>Initializing paper trader...</p>
          </div>
        ) : (<>

          {/* ── P&L Hero ── */}
          <div className={cn("rounded-2xl p-6 relative overflow-hidden",
            t.day_pnl >= 0 ? "bg-gradient-to-br from-emerald-500/[0.04] to-transparent border border-emerald-500/10" :
            "bg-gradient-to-br from-red-500/[0.04] to-transparent border border-red-500/10")}>
            <div className="flex items-start justify-between relative">
              <div>
                <p className="text-[11px] text-zinc-500 uppercase tracking-widest mb-3 flex items-center gap-1.5">
                  <DollarSign className="h-3.5 w-3.5" /> Today's P&L
                </p>
                <p className={cn("text-6xl font-bold font-mono tabular-nums leading-none tracking-tight",
                  t.day_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                  {t.day_pnl >= 0 ? "+" : ""}₹{t.day_pnl?.toFixed(2)}
                </p>
                <div className="flex items-center gap-4 mt-3 text-xs text-zinc-500">
                  <span>Gross ₹{(t.day_pnl + t.day_charges)?.toFixed(2)}</span>
                  <span className="text-zinc-700">·</span>
                  <span>Charges ₹{t.day_charges?.toFixed(2)}</span>
                  <span className="text-zinc-700">·</span>
                  <span>{t.day_trades} trades</span>
                </div>
              </div>
              <div className="text-right">
                <p className="text-3xl font-bold font-mono text-zinc-200 leading-none">₹{t.capital?.toFixed(0)}</p>
                <p className="text-[11px] text-zinc-600 mt-1">of ₹{t.starting_capital?.toFixed(0)}</p>
                <p className={cn("text-lg font-mono font-bold mt-2",
                  t.capital >= t.starting_capital ? "text-emerald-400" : "text-red-400")}>
                  {((t.capital / t.starting_capital - 1) * 100)?.toFixed(2)}%
                </p>
              </div>
            </div>
          </div>

          {/* ── Stats ── */}
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
            {([
              ["Trades", t.day_trades, Activity, undefined],
              ["Win Rate", `${(t.win_rate * 100)?.toFixed(0)}%`, Target, t.win_rate > 0.5 ? "text-emerald-400" : t.win_rate > 0 ? "text-amber-400" : undefined],
              ["W / L", `${t.day_wins} / ${t.day_losses}`, undefined, t.day_wins > t.day_losses ? "text-emerald-400" : t.day_losses > 0 ? "text-red-400" : undefined],
              ["Drawdown", `${(t.max_drawdown * 100)?.toFixed(1)}%`, AlertTriangle, t.max_drawdown > 0.03 ? "text-red-400" : undefined],
              ["Leverage", `${t.leverage}x`, Wallet, undefined],
              ["Positions", t.open_position_count, BarChart3, t.open_position_count > 0 ? "text-blue-400" : undefined],
            ] as const).map(([label, value, icon, color]) => (
              <div key={label as string} className="bg-[#0c0c11] border border-zinc-800/40 rounded-lg px-3 py-2.5">
                <div className="flex items-center gap-1.5 mb-1">
                  {icon && (() => { const I = icon as typeof Activity; return <I className="h-3 w-3 text-zinc-600" />; })()}
                  <p className="text-[9px] text-zinc-600 uppercase tracking-wider">{label as string}</p>
                </div>
                <p className={cn("text-lg font-bold font-mono tabular-nums", (color as string) ?? "text-zinc-200")}>{value as any}</p>
              </div>
            ))}
          </div>

          {/* ── Open Positions ── */}
          <Section title="Open Positions" count={t.open_position_count} extra={
            t.total_unrealized_pnl !== 0 ? (
              <span className={cn("font-mono font-bold", t.total_unrealized_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                {t.total_unrealized_pnl >= 0 ? "+" : ""}₹{t.total_unrealized_pnl?.toFixed(2)}
              </span>
            ) : null
          }>
            {!Object.keys(t.positions).length ? (
              <Empty>No open positions</Empty>
            ) : (
              <table className="w-full text-xs">
                <thead><tr className="text-zinc-500">
                  <th className="text-left py-2 px-4 font-medium">Instrument</th>
                  <th className="text-center py-2 px-3">Side</th>
                  <th className="text-right py-2 px-3">Qty</th>
                  <th className="text-right py-2 px-3">Entry</th>
                  <th className="text-right py-2 px-3">Current</th>
                  <th className="text-right py-2 px-4">P&L</th>
                </tr></thead>
                <tbody>{Object.entries(t.positions).map(([inst, pos]: [string, any]) => (
                  <tr key={inst} className="border-t border-zinc-800/20">
                    <td className="py-3 px-4 font-medium text-zinc-200">{INST[inst] ?? inst}</td>
                    <td className="py-3 px-3 text-center"><SideBadge side={pos.side} /></td>
                    <td className="py-3 px-3 text-right font-mono">{pos.quantity}</td>
                    <td className="py-3 px-3 text-right font-mono text-zinc-400">₹{pos.entry_price?.toFixed(2)}</td>
                    <td className="py-3 px-3 text-right font-mono">₹{pos.current_price?.toFixed(2)}</td>
                    <td className={cn("py-3 px-4 text-right font-mono font-bold", pos.unrealized_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                      {pos.unrealized_pnl >= 0 ? "+" : ""}₹{pos.unrealized_pnl?.toFixed(2)}
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </Section>

          {/* ── Closed Trades ── */}
          <Section title="Trade History" count={t.closed_trades?.length ?? 0}>
            {!t.closed_trades?.length ? (
              <Empty>No trades completed yet</Empty>
            ) : (
              <div className="divide-y divide-zinc-800/20">
                {[...t.closed_trades].reverse().map((trade: any, i: number) => (
                  <TradeRow key={i} trade={trade} />
                ))}
              </div>
            )}
          </Section>

          {/* ── Orders ── */}
          <Section title="Order History" count={t.recent_orders?.length ?? 0}>
            {!t.recent_orders?.length ? (
              <Empty>No orders placed</Empty>
            ) : (
              <table className="w-full text-xs">
                <thead><tr className="text-zinc-500">
                  <th className="text-left py-2 px-4 font-medium">Time</th>
                  <th className="text-left py-2 px-3">Instrument</th>
                  <th className="text-center py-2 px-2">Side</th>
                  <th className="text-right py-2 px-3">Qty</th>
                  <th className="text-right py-2 px-3">Signal</th>
                  <th className="text-right py-2 px-3">Fill</th>
                  <th className="text-right py-2 px-3">Charges</th>
                  <th className="text-center py-2 px-3">Status</th>
                </tr></thead>
                <tbody>{[...t.recent_orders].reverse().map((o: any, i: number) => {
                  const time = o.placed_at ? new Date(o.placed_at * 1000).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }) : "";
                  return (
                    <tr key={i} className="border-t border-zinc-800/20">
                      <td className="py-2.5 px-4 font-mono text-zinc-500">{time}</td>
                      <td className="py-2.5 px-3 text-zinc-200">{INST[o.instrument] ?? o.instrument}</td>
                      <td className="py-2.5 px-2 text-center"><SideBadge side={o.side} /></td>
                      <td className="py-2.5 px-3 text-right font-mono">{o.quantity}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-zinc-500">₹{o.signal_price?.toFixed(2)}</td>
                      <td className="py-2.5 px-3 text-right font-mono">₹{o.fill_price?.toFixed(2)}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-zinc-600">₹{o.charges?.toFixed(2)}</td>
                      <td className="py-2.5 px-3 text-center">
                        {o.status === "COMPLETE" ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 inline" /> : <XCircle className="h-3.5 w-3.5 text-red-500 inline" />}
                      </td>
                    </tr>
                  );
                })}</tbody>
              </table>
            )}
          </Section>
        </>)}
      </main>
    </div>
  );
}

// ── Shared components ───────────────────────────────────────────

function Section({ title, count, extra, children }: { title: string; count: number; extra?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-zinc-800/40 bg-[#0c0c11] overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-800/30 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-[0.08em]">{title}</span>
          <span className="text-[10px] text-zinc-600 font-mono">{count}</span>
        </div>
        {extra}
      </div>
      {children}
    </div>
  );
}

function Empty({ children }: { children: string }) {
  return <div className="px-4 py-8 text-center text-zinc-600 text-xs">{children}</div>;
}

function SideBadge({ side }: { side: string }) {
  return (
    <span className={cn("inline-flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded",
      side === "BUY" || side === "LONG" ? "text-emerald-400 bg-emerald-500/10" : "text-red-400 bg-red-500/10")}>
      {(side === "BUY" || side === "LONG") ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}
      {side}
    </span>
  );
}

function TradeRow({ trade }: { trade: any }) {
  const [open, setOpen] = useState(false);
  const exitTime = trade.exit_time ? new Date(trade.exit_time * 1000).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }) : "";
  const holdMin = trade.exit_time && trade.entry_time ? ((trade.exit_time - trade.entry_time) / 60).toFixed(0) : "?";

  return (
    <div className={cn("cursor-pointer transition-colors", trade.net_pnl >= 0 ? "hover:bg-emerald-500/[0.02]" : "hover:bg-red-500/[0.02]")}
      onClick={() => setOpen(o => !o)}>
      <div className="flex items-center gap-3 text-xs px-4 py-3">
        <span className="font-mono text-zinc-500 w-14 shrink-0">{exitTime}</span>
        <span className="font-medium text-zinc-200 w-20">{INST[trade.instrument] ?? trade.instrument}</span>
        <SideBadge side={trade.side} />
        <span className="font-mono text-zinc-400 text-[11px]">₹{trade.entry_price?.toFixed(2)} → ₹{trade.exit_price?.toFixed(2)}</span>
        <span className="text-zinc-600 text-[10px]">{holdMin}m</span>
        <span className={cn("font-bold font-mono ml-auto tabular-nums", trade.net_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
          {trade.net_pnl >= 0 ? "+" : ""}₹{trade.net_pnl?.toFixed(2)}
        </span>
        <ChevronRight className={cn("h-3 w-3 text-zinc-700 transition-transform shrink-0", open && "rotate-90")} />
      </div>
      {open && (
        <div className="px-4 pb-3 text-[11px] text-zinc-500 space-y-0.5 border-t border-zinc-800/20 pt-2 ml-14">
          <p>Gross: ₹{trade.gross_pnl?.toFixed(2)} · Charges: ₹{trade.charges?.toFixed(2)} · Hold: {holdMin}min</p>
          <p className="text-zinc-600">{trade.reason}</p>
        </div>
      )}
    </div>
  );
}
