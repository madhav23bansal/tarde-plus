"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useStore, type TradingStatus } from "@/lib/ws";
import { Tip } from "@/components/tip";
import { cn } from "@/lib/cn";
import {
  ArrowLeft, TrendingUp, TrendingDown, Minus, DollarSign, BarChart3,
  Target, Shield, Zap, Clock, Activity, ArrowUpRight, ArrowDownRight,
  Wallet, PieChart, AlertTriangle, CheckCircle2, XCircle,
} from "lucide-react";

function useTick(ms = 1000) { const [, s] = useState(0); useEffect(() => { const i = setInterval(() => s(t => t + 1), ms); return () => clearInterval(i); }, [ms]); }

function Stat({ label, value, color, icon: Icon, tip }: {
  label: string; value: string | number; color?: string; icon?: typeof DollarSign; tip?: string;
}) {
  const content = (
    <div className="rounded-lg border border-zinc-800/50 bg-[#0c0c11] px-4 py-3">
      <div className="flex items-center gap-2 mb-1">
        {Icon && <Icon className="h-3.5 w-3.5 text-zinc-600" />}
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</p>
      </div>
      <p className={cn("text-lg font-bold font-mono tabular-nums", color ?? "text-zinc-200")}>{value}</p>
    </div>
  );
  if (tip) return <Tip text={tip}><div className="cursor-help">{content}</div></Tip>;
  return content;
}

export default function TradesPage() {
  useTick(2000);
  const { trading, connected } = useStore();

  // Also fetch from REST as fallback
  const [restData, setRestData] = useState<TradingStatus | null>(null);
  useEffect(() => {
    fetch("/api/trading").then(r => r.json()).then(d => {
      if (!d.error) setRestData(d);
    }).catch(() => {});
    const i = setInterval(() => {
      fetch("/api/trading").then(r => r.json()).then(d => {
        if (!d.error) setRestData(d);
      }).catch(() => {});
    }, 5000);
    return () => clearInterval(i);
  }, []);

  const t = trading ?? restData;

  return (
    <div className="min-h-screen bg-[#08080c] text-zinc-100 font-sans">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[#0a0a0f]/95 backdrop-blur-md border-b border-zinc-800/60">
        <div className="max-w-[1600px] mx-auto px-5 h-11 flex items-center gap-3 text-xs">
          <Link href="/" className="flex items-center gap-1.5 text-zinc-400 hover:text-zinc-200 transition-colors">
            <ArrowLeft className="h-3.5 w-3.5" /><span>Dashboard</span>
          </Link>
          <span className="text-zinc-800">|</span>
          <Zap className="h-3.5 w-3.5 text-blue-500" />
          <span className="font-bold text-zinc-200 text-sm">Paper Trading</span>
          {t && <span className={cn("text-[10px] font-bold tracking-widest px-2 py-0.5 rounded border", t.day_pnl >= 0 ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" : "text-red-400 bg-red-500/10 border-red-500/20")}>
            P&L: Rs {t.day_pnl >= 0 ? "+" : ""}{t.day_pnl?.toFixed(2)}
          </span>}
          {t && <span className="text-zinc-500 ml-auto font-mono">Capital: Rs {t.capital?.toFixed(0)} | Broker: {t.broker}</span>}
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-5 py-4 space-y-4">
        {!t && (
          <div className="text-center py-20 text-zinc-500">
            <Activity className="h-8 w-8 mx-auto mb-3 animate-pulse" />
            <p className="text-sm">Waiting for paper trader to initialize...</p>
            <p className="text-xs mt-1 text-zinc-700">The trader starts when the API server runs its first collection cycle.</p>
          </div>
        )}

        {t && (<>
          {/* ── P&L Hero ── */}
          <div className={cn("rounded-xl border p-5", t.day_pnl >= 0 ? "border-emerald-900/30 bg-emerald-500/[0.03]" : "border-red-900/30 bg-red-500/[0.03]")}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-zinc-500 uppercase tracking-wider mb-1">Today's Net P&L</p>
                <p className={cn("text-4xl font-bold font-mono tabular-nums", t.day_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                  Rs {t.day_pnl >= 0 ? "+" : ""}{t.day_pnl?.toFixed(2)}
                </p>
                <p className="text-xs text-zinc-600 mt-1">
                  Gross: Rs {(t.day_pnl + t.day_charges)?.toFixed(2)} | Charges: Rs {t.day_charges?.toFixed(2)}
                </p>
              </div>
              <div className="text-right space-y-1">
                <p className="text-2xl font-bold font-mono text-zinc-200">Rs {t.capital?.toFixed(0)}</p>
                <p className="text-xs text-zinc-600">of Rs {t.starting_capital?.toFixed(0)} starting</p>
                <p className={cn("text-xs font-mono", t.capital >= t.starting_capital ? "text-emerald-400" : "text-red-400")}>
                  {((t.capital / t.starting_capital - 1) * 100)?.toFixed(2)}%
                </p>
              </div>
            </div>
          </div>

          {/* ── Stats Grid ── */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <Stat label="Trades" value={t.day_trades} icon={Activity} tip="Total trades executed today" />
            <Stat label="Win Rate" value={`${(t.win_rate * 100)?.toFixed(0)}%`} icon={Target}
              color={t.win_rate > 0.5 ? "text-emerald-400" : t.win_rate > 0 ? "text-amber-400" : "text-zinc-500"}
              tip="Percentage of profitable trades" />
            <Stat label="Wins / Losses" value={`${t.day_wins} / ${t.day_losses}`} icon={PieChart}
              color={t.day_wins > t.day_losses ? "text-emerald-400" : "text-red-400"} />
            <Stat label="Max Drawdown" value={`${(t.max_drawdown * 100)?.toFixed(2)}%`} icon={AlertTriangle}
              color={t.max_drawdown > 0.05 ? "text-red-400" : t.max_drawdown > 0.02 ? "text-amber-400" : "text-zinc-400"}
              tip="Maximum peak-to-trough decline" />
            <Stat label="Buying Power" value={`Rs ${(t.buying_power / 1000)?.toFixed(0)}K`} icon={Wallet}
              tip={`${t.leverage}x leverage on Rs ${t.capital?.toFixed(0)} capital`} />
            <Stat label="Open Positions" value={t.open_position_count} icon={BarChart3}
              color={t.open_position_count > 0 ? "text-blue-400" : "text-zinc-500"} />
          </div>

          {/* ── Open Positions ── */}
          <div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] overflow-hidden">
            <div className="px-4 py-2.5 border-b border-zinc-800/40 flex items-center justify-between">
              <span className="text-xs font-bold text-zinc-300 uppercase tracking-wider">Open Positions ({t.open_position_count})</span>
              <span className={cn("text-xs font-mono", t.total_unrealized_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                Unrealized: Rs {t.total_unrealized_pnl >= 0 ? "+" : ""}{t.total_unrealized_pnl?.toFixed(2)}
              </span>
            </div>
            {Object.keys(t.positions).length === 0 ? (
              <div className="px-4 py-6 text-center text-zinc-600 text-xs">No open positions</div>
            ) : (
              <table className="w-full text-xs">
                <thead><tr className="text-zinc-500 bg-zinc-900/50">
                  <th className="text-left py-2 px-4">Instrument</th>
                  <th className="text-center py-2 px-2">Side</th>
                  <th className="text-right py-2 px-2">Qty</th>
                  <th className="text-right py-2 px-2">Entry</th>
                  <th className="text-right py-2 px-2">Current</th>
                  <th className="text-right py-2 px-2">P&L</th>
                </tr></thead>
                <tbody>
                  {Object.entries(t.positions).map(([inst, pos]: [string, any]) => (
                    <tr key={inst} className="border-t border-zinc-800/20">
                      <td className="py-2 px-4 font-semibold text-zinc-200">{inst}</td>
                      <td className="py-2 px-2 text-center">
                        <span className={cn("text-[10px] font-bold px-1.5 py-0.5 rounded",
                          pos.side === "LONG" ? "text-emerald-400 bg-emerald-500/10" : "text-red-400 bg-red-500/10"
                        )}>{pos.side}</span>
                      </td>
                      <td className="py-2 px-2 text-right font-mono">{pos.quantity}</td>
                      <td className="py-2 px-2 text-right font-mono text-zinc-400">{pos.entry_price?.toFixed(2)}</td>
                      <td className="py-2 px-2 text-right font-mono">{pos.current_price?.toFixed(2)}</td>
                      <td className={cn("py-2 px-2 text-right font-mono font-bold", pos.unrealized_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {pos.unrealized_pnl >= 0 ? "+" : ""}{pos.unrealized_pnl?.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* ── Closed Trades ── */}
          <div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] overflow-hidden">
            <div className="px-4 py-2.5 border-b border-zinc-800/40">
              <span className="text-xs font-bold text-zinc-300 uppercase tracking-wider">Closed Trades ({t.closed_trades?.length ?? 0})</span>
            </div>
            {(!t.closed_trades || t.closed_trades.length === 0) ? (
              <div className="px-4 py-6 text-center text-zinc-600 text-xs">No closed trades yet</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead><tr className="text-zinc-500 bg-zinc-900/50">
                    <th className="text-left py-2 px-4">Instrument</th>
                    <th className="text-center py-2 px-2">Side</th>
                    <th className="text-right py-2 px-2">Qty</th>
                    <th className="text-right py-2 px-2">Entry</th>
                    <th className="text-right py-2 px-2">Exit</th>
                    <th className="text-right py-2 px-2">Gross</th>
                    <th className="text-right py-2 px-2">Charges</th>
                    <th className="text-right py-2 px-2">Net P&L</th>
                    <th className="text-left py-2 px-2">Reason</th>
                  </tr></thead>
                  <tbody>
                    {[...t.closed_trades].reverse().map((trade: any, i: number) => (
                      <tr key={i} className="border-t border-zinc-800/20">
                        <td className="py-2 px-4 font-semibold text-zinc-200">{trade.instrument}</td>
                        <td className="py-2 px-2 text-center">
                          <span className={cn("text-[10px] font-bold px-1.5 py-0.5 rounded",
                            trade.side === "LONG" ? "text-emerald-400 bg-emerald-500/10" : "text-red-400 bg-red-500/10"
                          )}>{trade.side}</span>
                        </td>
                        <td className="py-2 px-2 text-right font-mono">{trade.quantity}</td>
                        <td className="py-2 px-2 text-right font-mono text-zinc-400">{trade.entry_price?.toFixed(2)}</td>
                        <td className="py-2 px-2 text-right font-mono text-zinc-400">{trade.exit_price?.toFixed(2)}</td>
                        <td className={cn("py-2 px-2 text-right font-mono", trade.gross_pnl >= 0 ? "text-emerald-400/70" : "text-red-400/70")}>
                          {trade.gross_pnl >= 0 ? "+" : ""}{trade.gross_pnl?.toFixed(2)}
                        </td>
                        <td className="py-2 px-2 text-right font-mono text-zinc-600">{trade.charges?.toFixed(2)}</td>
                        <td className={cn("py-2 px-2 text-right font-mono font-bold", trade.net_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                          {trade.net_pnl >= 0 ? "+" : ""}{trade.net_pnl?.toFixed(2)}
                        </td>
                        <td className="py-2 px-2 text-zinc-500 truncate max-w-[150px]">{trade.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* ── Recent Orders ── */}
          <div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] overflow-hidden">
            <div className="px-4 py-2.5 border-b border-zinc-800/40">
              <span className="text-xs font-bold text-zinc-300 uppercase tracking-wider">Recent Orders ({t.recent_orders?.length ?? 0})</span>
            </div>
            {(!t.recent_orders || t.recent_orders.length === 0) ? (
              <div className="px-4 py-6 text-center text-zinc-600 text-xs">No orders yet — trades execute when prediction confidence is high enough during market hours</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead><tr className="text-zinc-500 bg-zinc-900/50">
                    <th className="text-left py-2 px-4">Time</th>
                    <th className="text-left py-2 px-2">Instrument</th>
                    <th className="text-center py-2 px-2">Side</th>
                    <th className="text-right py-2 px-2">Qty</th>
                    <th className="text-right py-2 px-2">Signal Price</th>
                    <th className="text-right py-2 px-2">Fill Price</th>
                    <th className="text-right py-2 px-2">Charges</th>
                    <th className="text-center py-2 px-2">Status</th>
                    <th className="text-left py-2 px-2">Reason</th>
                  </tr></thead>
                  <tbody>
                    {[...t.recent_orders].reverse().map((order: any, i: number) => {
                      const time = order.placed_at ? new Date(order.placed_at * 1000).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }) : "";
                      return (
                        <tr key={i} className="border-t border-zinc-800/20">
                          <td className="py-2 px-4 font-mono text-zinc-500">{time}</td>
                          <td className="py-2 px-2 text-zinc-200">{order.instrument}</td>
                          <td className="py-2 px-2 text-center">
                            <span className={cn("text-[10px] font-bold px-1.5 py-0.5 rounded",
                              order.side === "BUY" ? "text-emerald-400 bg-emerald-500/10" : "text-red-400 bg-red-500/10"
                            )}>{order.side}</span>
                          </td>
                          <td className="py-2 px-2 text-right font-mono">{order.quantity}</td>
                          <td className="py-2 px-2 text-right font-mono text-zinc-500">{order.signal_price?.toFixed(2)}</td>
                          <td className="py-2 px-2 text-right font-mono">{order.fill_price?.toFixed(2)}</td>
                          <td className="py-2 px-2 text-right font-mono text-zinc-600">{order.charges?.toFixed(2)}</td>
                          <td className="py-2 px-2 text-center">
                            {order.status === "COMPLETE" ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 inline" /> : <XCircle className="h-3.5 w-3.5 text-red-500 inline" />}
                          </td>
                          <td className="py-2 px-2 text-zinc-500 truncate max-w-[150px]">{order.reason}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>)}
      </main>
    </div>
  );
}
