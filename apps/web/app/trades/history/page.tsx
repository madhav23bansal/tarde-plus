"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { cn } from "@/lib/cn";
import {
  ArrowLeft, ChevronRight, ChevronLeft, Calendar, Trophy,
  TrendingUp, TrendingDown, Minus, BarChart3, Filter,
  ArrowUpRight, ArrowDownRight, Activity, DollarSign,
  CheckCircle2, XCircle,
} from "lucide-react";

/* ── Helpers ──────────────────────────────────────────────────── */

function fmtMoney(n: number): string {
  if (Math.abs(n) >= 100000) return `₹${(n / 100000).toFixed(2)}L`;
  if (Math.abs(n) >= 1000) return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${n.toFixed(2)}`;
}

const N: Record<string, string> = { NIFTYBEES: "Nifty", BANKBEES: "Bank", SETFNIF50: "SBI" };

/* ── Types ────────────────────────────────────────────────────── */

interface DailySummary {
  date: string;
  day_of_week?: string;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  net_pnl: number;
  total_charges: number;
  total_invested: number;
  return_on_invested_pct: number;
  return_on_capital_pct?: number;
}

interface CumulativeStats {
  total_days: number;
  winning_days: number;
  losing_days: number;
  day_win_rate_pct: number;
  total_trades: number;
  total_wins: number;
  total_losses: number;
  trade_win_rate_pct: number;
  total_net_pnl: number;
  total_charges: number;
  total_invested: number;
  avg_daily_pnl: number;
  daily_results: DailySummary[];
}

interface Trade {
  instrument: string;
  side: string;
  quantity: number;
  entry_price: number;
  exit_price: number;
  entry_value: number;
  exit_value: number;
  gross_pnl: number;
  charges: number;
  net_pnl: number;
  return_pct: number;
  hold_minutes: number;
  reason: string;
  entry_time: string;
  exit_time: string;
}

interface DayDetail {
  date: string;
  day_of_week: string;
  starting_capital: number;
  total_invested: number;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  gross_pnl: number;
  total_charges: number;
  net_pnl: number;
  return_on_invested_pct: number;
  return_on_capital_pct: number;
  max_drawdown_pct: number;
  trades: Trade[];
}

/* ── Page ─────────────────────────────────────────────────────── */

const ITEMS_PER_PAGE = 20;

export default function TradeHistoryPage() {
  const [stats, setStats] = useState<CumulativeStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<"all" | "wins" | "losses">("all");
  const [expandedDate, setExpandedDate] = useState<string | null>(null);
  const [dayDetail, setDayDetail] = useState<Record<string, DayDetail>>({});
  const [loadingDay, setLoadingDay] = useState<string | null>(null);
  const [instrumentFilter, setInstrumentFilter] = useState<string>("all");

  useEffect(() => {
    fetch("/api/trade-history")
      .then(r => r.json())
      .then(d => { setStats(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const filteredDays = useMemo(() => {
    if (!stats?.daily_results) return [];
    let days = [...stats.daily_results].reverse(); // newest first
    if (filter === "wins") days = days.filter(d => d.net_pnl > 0);
    if (filter === "losses") days = days.filter(d => d.net_pnl <= 0);
    return days;
  }, [stats, filter]);

  const totalPages = Math.ceil(filteredDays.length / ITEMS_PER_PAGE);
  const pagedDays = filteredDays.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE);

  const toggleDay = (date: string) => {
    if (expandedDate === date) {
      setExpandedDate(null);
      return;
    }
    setExpandedDate(date);
    if (!dayDetail[date]) {
      setLoadingDay(date);
      fetch(`/api/trade-history/${date}`)
        .then(r => r.json())
        .then(d => {
          setDayDetail(prev => ({ ...prev, [date]: d }));
          setLoadingDay(null);
        })
        .catch(() => setLoadingDay(null));
    }
  };

  const filteredTrades = (trades: Trade[]) => {
    if (instrumentFilter === "all") return trades;
    return trades.filter(t => t.instrument === instrumentFilter);
  };

  const allInstruments = useMemo(() => {
    const set = new Set<string>();
    Object.values(dayDetail).forEach(d => d.trades?.forEach(t => set.add(t.instrument)));
    return Array.from(set).sort();
  }, [dayDetail]);

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <Activity className="h-5 w-5 text-zinc-600 animate-spin" />
      </div>
    );
  }

  const s = stats;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* ── Top Bar ──────────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 h-10 bg-zinc-950/95 backdrop-blur border-b border-zinc-800/50 flex items-center px-4 gap-4">
        <Link href="/trades" className="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 transition-colors">
          <ArrowLeft className="h-3.5 w-3.5" />
          <span className="text-[11px] font-medium">Trades</span>
        </Link>
        <div className="h-3 w-px bg-zinc-800" />
        <h1 className="text-[11px] font-bold tracking-wider text-zinc-300 uppercase flex items-center gap-1.5">
          <Calendar className="h-3 w-3 text-blue-400" />
          Trade History
        </h1>
        <div className="flex-1" />
        <Link href="/" className="text-[10px] text-zinc-600 hover:text-zinc-400">Dashboard</Link>
      </header>

      <div className="max-w-[1440px] mx-auto px-4 py-4 space-y-4">
        {/* ── Cumulative Stats ────────────────────────────────────── */}
        {s && s.total_days > 0 && (
          <div className="border border-zinc-800/50 rounded bg-zinc-900/30">
            <div className="px-3 py-2 border-b border-zinc-800/30 flex items-center gap-2">
              <Trophy className="h-3 w-3 text-amber-400" />
              <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">Cumulative Performance</span>
              <span className="text-[10px] text-zinc-600 ml-auto">{s.total_days} trading day{s.total_days > 1 ? "s" : ""}</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 divide-x divide-zinc-800/30">
              <Stat label="Total P&L" value={`${s.total_net_pnl >= 0 ? "+" : ""}₹${s.total_net_pnl.toFixed(2)}`} color={s.total_net_pnl >= 0 ? "text-emerald-400" : "text-red-400"} />
              <Stat label="Total Trades" value={String(s.total_trades)} />
              <Stat label="Win Rate" value={`${s.trade_win_rate_pct.toFixed(0)}%`} color={s.trade_win_rate_pct >= 50 ? "text-emerald-400" : "text-red-400"} />
              <Stat label="Day Win Rate" value={`${s.day_win_rate_pct.toFixed(0)}%`} color={s.day_win_rate_pct >= 50 ? "text-emerald-400" : "text-red-400"} />
              <Stat label="Avg Daily P&L" value={`${s.avg_daily_pnl >= 0 ? "+" : ""}₹${s.avg_daily_pnl.toFixed(2)}`} color={s.avg_daily_pnl >= 0 ? "text-emerald-400" : "text-red-400"} />
              <Stat label="Total Charges" value={`₹${s.total_charges.toFixed(2)}`} color="text-amber-400/70" />
              <Stat label="Total Invested" value={fmtMoney(s.total_invested)} />
              <Stat label="W / L Days" value={`${s.winning_days} / ${s.losing_days}`} />
            </div>
          </div>
        )}

        {/* ── Filters + Pagination ───────────────────────────────── */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1 border border-zinc-800/50 rounded overflow-hidden">
            {(["all", "wins", "losses"] as const).map(f => (
              <button key={f} onClick={() => { setFilter(f); setPage(1); }}
                className={cn("px-3 py-1 text-[10px] font-medium uppercase tracking-wider transition-colors",
                  filter === f ? "bg-zinc-800 text-zinc-200" : "text-zinc-600 hover:text-zinc-400")}>
                {f === "all" ? "All Days" : f === "wins" ? "Profitable" : "Losing"}
              </button>
            ))}
          </div>

          {allInstruments.length > 0 && (
            <select value={instrumentFilter} onChange={e => setInstrumentFilter(e.target.value)}
              className="bg-zinc-900 border border-zinc-800/50 rounded px-2 py-1 text-[10px] text-zinc-400">
              <option value="all">All Instruments</option>
              {allInstruments.map(inst => (
                <option key={inst} value={inst}>{N[inst] ?? inst}</option>
              ))}
            </select>
          )}

          <div className="flex-1" />

          <span className="text-[10px] text-zinc-600">
            {filteredDays.length} day{filteredDays.length !== 1 ? "s" : ""}
            {filteredDays.length !== (stats?.daily_results?.length ?? 0) && ` of ${stats?.daily_results?.length}`}
          </span>

          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
                className="p-1 rounded hover:bg-zinc-800 disabled:opacity-30 transition-colors">
                <ChevronLeft className="h-3 w-3 text-zinc-500" />
              </button>
              <span className="text-[10px] text-zinc-500 font-mono px-1">{page}/{totalPages}</span>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                className="p-1 rounded hover:bg-zinc-800 disabled:opacity-30 transition-colors">
                <ChevronRight className="h-3 w-3 text-zinc-500" />
              </button>
            </div>
          )}
        </div>

        {/* ── Daily Results Table ─────────────────────────────────── */}
        <div className="border border-zinc-800/50 rounded bg-zinc-900/30 overflow-hidden">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-[9px] text-zinc-600 uppercase tracking-wider bg-zinc-900/50 border-b border-zinc-800/30">
                <th className="w-6 py-1.5 px-2" />
                <th className="text-left py-1.5 px-2 font-medium">Date</th>
                <th className="text-left py-1.5 px-2 font-medium">Day</th>
                <th className="text-right py-1.5 px-2 font-medium">Trades</th>
                <th className="text-center py-1.5 px-2 font-medium">W/L</th>
                <th className="text-right py-1.5 px-2 font-medium">Win%</th>
                <th className="text-right py-1.5 px-2 font-medium">Invested</th>
                <th className="text-right py-1.5 px-2 font-medium">Net P&L</th>
                <th className="text-right py-1.5 px-2 font-medium">Charges</th>
                <th className="text-right py-1.5 px-2 font-medium">Return%</th>
              </tr>
            </thead>
            <tbody>
              {pagedDays.length === 0 ? (
                <tr><td colSpan={10} className="py-8 text-center text-zinc-700 text-[11px]">No trading history yet</td></tr>
              ) : pagedDays.map(day => (
                <DayRow key={day.date} day={day}
                  expanded={expandedDate === day.date}
                  loading={loadingDay === day.date}
                  detail={dayDetail[day.date]}
                  onToggle={() => toggleDay(day.date)}
                  instrumentFilter={instrumentFilter} />
              ))}
            </tbody>
          </table>
        </div>

        {/* ── Bottom Pagination ──────────────────────────────────── */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 py-2">
            <button onClick={() => setPage(1)} disabled={page <= 1}
              className="px-2 py-1 text-[10px] text-zinc-500 hover:text-zinc-300 disabled:opacity-30">First</button>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
              className="px-2 py-1 text-[10px] text-zinc-500 hover:text-zinc-300 disabled:opacity-30">
              <ChevronLeft className="h-3 w-3 inline" /> Prev
            </button>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const pageNum = Math.max(1, Math.min(page - 2 + i, totalPages));
              return (
                <button key={pageNum} onClick={() => setPage(pageNum)}
                  className={cn("w-6 h-6 text-[10px] rounded font-mono", page === pageNum ? "bg-zinc-800 text-zinc-200" : "text-zinc-600 hover:text-zinc-400")}>
                  {pageNum}
                </button>
              );
            })}
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
              className="px-2 py-1 text-[10px] text-zinc-500 hover:text-zinc-300 disabled:opacity-30">
              Next <ChevronRight className="h-3 w-3 inline" />
            </button>
            <button onClick={() => setPage(totalPages)} disabled={page >= totalPages}
              className="px-2 py-1 text-[10px] text-zinc-500 hover:text-zinc-300 disabled:opacity-30">Last</button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Components ───────────────────────────────────────────────── */

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="px-3 py-2">
      <div className="text-[8px] text-zinc-600 uppercase tracking-wider font-medium">{label}</div>
      <div className={cn("text-[13px] font-mono font-bold", color ?? "text-zinc-300")}>{value}</div>
    </div>
  );
}

function SideBadge({ s }: { s: string }) {
  return (
    <span className={cn("text-[9px] font-bold px-1.5 py-0.5 rounded",
      s === "BUY" || s === "LONG" ? "text-emerald-400 bg-emerald-500/10" : "text-red-400 bg-red-500/10")}>
      {s}
    </span>
  );
}

function DayRow({ day, expanded, loading, detail, onToggle, instrumentFilter }: {
  day: DailySummary; expanded: boolean; loading: boolean; detail?: DayDetail; onToggle: () => void; instrumentFilter: string;
}) {
  const netPnl = day.net_pnl ?? 0;
  const charges = day.total_charges ?? 0;
  const invested = day.total_invested ?? 0;
  const returnPct = day.return_on_invested_pct ?? (invested > 0 ? netPnl / invested * 100 : 0);
  const winRate = day.total_trades > 0 ? (day.wins / day.total_trades * 100) : 0;

  let dayName = day.day_of_week ?? "";
  if (!dayName && day.date) {
    try { dayName = new Date(day.date + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short" }); } catch {}
  }

  const trades = detail?.trades ?? [];
  const shown = instrumentFilter === "all" ? trades : trades.filter(t => t.instrument === instrumentFilter);

  return (
    <>
      <tr className={cn("border-t border-zinc-800/20 cursor-pointer transition-colors",
        expanded ? "bg-zinc-800/15" : "hover:bg-zinc-800/10")}
        onClick={onToggle}>
        <td className="py-1.5 px-2">
          <ChevronRight className={cn("h-3 w-3 text-zinc-600 transition-transform", expanded && "rotate-90")} />
        </td>
        <td className="py-1.5 px-2 font-mono text-zinc-300 font-medium">{day.date}</td>
        <td className="py-1.5 px-2 text-zinc-500">{dayName}</td>
        <td className="py-1.5 px-2 text-right font-mono text-zinc-400">{day.total_trades}</td>
        <td className="py-1.5 px-2 text-center">
          <span className="text-emerald-400 font-mono">{day.wins}</span>
          <span className="text-zinc-700 mx-0.5">/</span>
          <span className="text-red-400 font-mono">{day.losses}</span>
        </td>
        <td className={cn("py-1.5 px-2 text-right font-mono", winRate >= 50 ? "text-emerald-400" : winRate > 0 ? "text-red-400" : "text-zinc-600")}>
          {day.total_trades > 0 ? `${winRate.toFixed(0)}%` : "---"}
        </td>
        <td className="py-1.5 px-2 text-right font-mono text-zinc-500">
          {invested > 0 ? `₹${invested.toFixed(0)}` : "---"}
        </td>
        <td className={cn("py-1.5 px-2 text-right font-mono font-bold", netPnl >= 0 ? "text-emerald-400" : "text-red-400")}>
          {netPnl >= 0 ? "+" : ""}₹{netPnl.toFixed(2)}
        </td>
        <td className="py-1.5 px-2 text-right font-mono text-amber-400/60">₹{charges.toFixed(2)}</td>
        <td className={cn("py-1.5 px-2 text-right font-mono", returnPct >= 0 ? "text-emerald-400/70" : "text-red-400/70")}>
          {returnPct !== 0 ? `${returnPct >= 0 ? "+" : ""}${returnPct.toFixed(2)}%` : "---"}
        </td>
      </tr>

      {expanded && (
        <tr>
          <td colSpan={10} className="bg-zinc-900/50 border-t border-zinc-800/20">
            {loading ? (
              <div className="py-4 flex items-center justify-center gap-2 text-zinc-600 text-[10px]">
                <Activity className="h-3 w-3 animate-spin" /> Loading trades...
              </div>
            ) : shown.length > 0 ? (
              <div className="px-4 py-2">
                {/* Day summary strip */}
                {detail && (
                  <div className="flex items-center gap-4 mb-2 text-[10px] text-zinc-500">
                    <span>Capital: ₹{detail.starting_capital?.toLocaleString()}</span>
                    <span>Invested: ₹{detail.total_invested?.toFixed(0)}</span>
                    <span>Gross: <span className={detail.gross_pnl >= 0 ? "text-emerald-400" : "text-red-400"}>₹{detail.gross_pnl?.toFixed(2)}</span></span>
                    <span>Charges: <span className="text-amber-400">₹{detail.total_charges?.toFixed(2)}</span></span>
                    <span>Max DD: {detail.max_drawdown_pct?.toFixed(2)}%</span>
                  </div>
                )}

                <table className="w-full text-[10px]">
                  <thead>
                    <tr className="text-[8px] text-zinc-600 uppercase tracking-wider">
                      <th className="text-left py-1 px-2 font-medium">Entry</th>
                      <th className="text-left py-1 px-2 font-medium">Exit</th>
                      <th className="text-left py-1 px-2 font-medium">Inst</th>
                      <th className="text-left py-1 px-2 font-medium">Side</th>
                      <th className="text-right py-1 px-2 font-medium">Qty</th>
                      <th className="text-right py-1 px-2 font-medium">Entry ₹</th>
                      <th className="text-right py-1 px-2 font-medium">Exit ₹</th>
                      <th className="text-right py-1 px-2 font-medium">Hold</th>
                      <th className="text-right py-1 px-2 font-medium">Gross</th>
                      <th className="text-right py-1 px-2 font-medium">Charges</th>
                      <th className="text-right py-1 px-2 font-medium">Net P&L</th>
                      <th className="text-right py-1 px-2 font-medium">Return</th>
                      <th className="text-left py-1 px-2 font-medium">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((t, i) => (
                      <tr key={i} className={cn("border-t border-zinc-800/10",
                        t.net_pnl >= 0 ? "hover:bg-emerald-500/[0.03]" : "hover:bg-red-500/[0.03]")}>
                        <td className="py-1 px-2 font-mono text-zinc-500">{t.entry_time}</td>
                        <td className="py-1 px-2 font-mono text-zinc-500">{t.exit_time}</td>
                        <td className="py-1 px-2 text-zinc-300">{N[t.instrument] ?? t.instrument}</td>
                        <td className="py-1 px-2"><SideBadge s={t.side} /></td>
                        <td className="py-1 px-2 text-right font-mono text-zinc-500">{t.quantity}</td>
                        <td className="py-1 px-2 text-right font-mono text-zinc-500">₹{t.entry_price?.toFixed(2)}</td>
                        <td className="py-1 px-2 text-right font-mono text-zinc-300">₹{t.exit_price?.toFixed(2)}</td>
                        <td className="py-1 px-2 text-right text-zinc-600">{t.hold_minutes ? `${t.hold_minutes}m` : "?"}</td>
                        <td className={cn("py-1 px-2 text-right font-mono", t.gross_pnl >= 0 ? "text-emerald-400/60" : "text-red-400/60")}>
                          ₹{t.gross_pnl?.toFixed(2)}
                        </td>
                        <td className="py-1 px-2 text-right font-mono text-amber-400/50">₹{t.charges?.toFixed(2)}</td>
                        <td className={cn("py-1 px-2 text-right font-mono font-bold", t.net_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                          {t.net_pnl >= 0 ? "+" : ""}₹{t.net_pnl?.toFixed(2)}
                        </td>
                        <td className={cn("py-1 px-2 text-right font-mono", (t.return_pct ?? 0) >= 0 ? "text-emerald-400/50" : "text-red-400/50")}>
                          {t.return_pct ? `${t.return_pct >= 0 ? "+" : ""}${t.return_pct.toFixed(2)}%` : "---"}
                        </td>
                        <td className="py-1 px-2 text-zinc-600 truncate max-w-[180px]" title={t.reason}>{t.reason || "---"}</td>
                      </tr>
                    ))}
                    {/* Totals row */}
                    <tr className="border-t border-zinc-700/30 bg-zinc-800/20 font-bold">
                      <td colSpan={8} className="py-1 px-2 text-[9px] text-zinc-500 uppercase">Total ({shown.length} trades)</td>
                      <td className={cn("py-1 px-2 text-right font-mono text-[10px]",
                        shown.reduce((s, t) => s + (t.gross_pnl ?? 0), 0) >= 0 ? "text-emerald-400/70" : "text-red-400/70")}>
                        ₹{shown.reduce((s, t) => s + (t.gross_pnl ?? 0), 0).toFixed(2)}
                      </td>
                      <td className="py-1 px-2 text-right font-mono text-[10px] text-amber-400/60">
                        ₹{shown.reduce((s, t) => s + (t.charges ?? 0), 0).toFixed(2)}
                      </td>
                      <td className={cn("py-1 px-2 text-right font-mono text-[10px]",
                        shown.reduce((s, t) => s + (t.net_pnl ?? 0), 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {shown.reduce((s, t) => s + (t.net_pnl ?? 0), 0) >= 0 ? "+" : ""}
                        ₹{shown.reduce((s, t) => s + (t.net_pnl ?? 0), 0).toFixed(2)}
                      </td>
                      <td colSpan={2} />
                    </tr>
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="py-4 text-center text-zinc-700 text-[10px]">No trade details available for this day</div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
