import { create } from "zustand";

// ── Types (match actual API response shapes) ────────────────────

export interface MarketStatus {
  market: {
    time_ist: string;
    session: string;
    is_trading_day: boolean;
    can_trade: boolean;
    should_squareoff: boolean;
    time_to_open: string;
    is_holiday: boolean;
  };
  server: {
    collection_count: number;
    last_update: number;
    last_update_ago_sec: number | null;
    errors: string[];
    ws_clients: number;
    db: { redis: boolean; timescaledb: boolean };
  };
}

export interface Prediction {
  instrument: string;
  direction: "LONG" | "SHORT" | "FLAT";
  score: number;
  confidence: number;
  reasons: string[];
  method: string;
  ensemble?: { ml_score: number; rules_score: number };
  market_data?: {
    price: number; change_pct: number; rsi_14: number;
    volume_ratio: number; returns_1d: number; returns_5d: number;
    ai_news_sentiment: number; ai_news_count: number;
  };
  nse_data?: {
    fii_net: number; dii_net: number; india_vix: number;
    india_vix_change: number; pcr_oi: number;
  };
  sector_signals?: Record<string, number>;
  levels?: any;
  decision?: any;
}

export interface TradingStatus {
  capital: number;
  starting_capital: number;
  buying_power: number;
  leverage: number;
  day_pnl: number;
  day_charges: number;
  day_trades: number;
  day_wins: number;
  day_losses: number;
  win_rate: number;
  max_drawdown: number;
  positions: Record<string, any>;
  open_position_count: number;
  total_unrealized_pnl: number;
  recent_orders: any[];
  closed_trades: any[];
  broker: string;
}

export interface ActivityEntry {
  run_id: string;
  cycle: number;
  timestamp: string;
  session: string;
  duration_sec?: number;
  next_run_at?: number;
  status: string;
  predictions?: Record<string, any>;
}

// ── Store ────────────────────────────────────────────────────────

interface Store {
  connected: boolean;
  status: MarketStatus | null;
  predictions: Prediction[];
  activity: ActivityEntry[];
  trading: TradingStatus | null;
  momentum: any;        // intraday trader state (levels, decisions, OI)
  livePrices: any;      // latest prices per instrument
  session: string;
  collectionCount: number;
  updatedAt: number;
  lastWsMessage: number;
  lastActivityAt: number;
  updateSeq: number;
}

export const useStore = create<Store>(() => ({
  connected: false,
  status: null,
  predictions: [],
  activity: [],
  trading: null,
  momentum: null,
  livePrices: null,
  session: "closed",
  collectionCount: 0,
  updatedAt: 0,
  lastWsMessage: 0,
  lastActivityAt: 0,
  updateSeq: 0,
}));

// ── WebSocket ────────────────────────────────────────────────────

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let pingTimer: ReturnType<typeof setInterval> | null = null;

function applyMessage(msg: any) {
  const now = Date.now();

  if (msg.type === "init" || msg.type === "update") {
    const preds = msg.predictions?.predictions ?? [];
    useStore.setState((s) => ({
      status: msg.status,
      predictions: preds,
      activity: msg.activity ?? s.activity,
      trading: msg.trading ?? s.trading,
      momentum: msg.momentum ?? s.momentum,
      session: msg.status?.market?.session ?? s.session,
      collectionCount: msg.predictions?.collection_count ?? s.collectionCount,
      updatedAt: msg.predictions?.updated_at ?? s.updatedAt,
      lastWsMessage: now,
      lastActivityAt: now,
      updateSeq: s.updateSeq + 1,
    }));
  } else if (msg.type === "heartbeat") {
    useStore.setState({
      status: msg.status,
      session: msg.status?.market?.session ?? useStore.getState().session,
      lastWsMessage: now,
    });
  } else if (msg.type === "trading_update") {
    useStore.setState((s) => ({
      trading: msg.trading ?? s.trading,
      momentum: msg.momentum ?? s.momentum,
      livePrices: msg.prices ?? s.livePrices,
      lastWsMessage: now,
    }));
  }
}

export function connectWs() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  try { ws = new WebSocket("ws://localhost:8000/ws"); } catch { scheduleReconnect(); return; }

  ws.onopen = () => {
    useStore.setState({ connected: true });
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    if (pingTimer) clearInterval(pingTimer);
    pingTimer = setInterval(() => { if (ws?.readyState === WebSocket.OPEN) ws.send("ping"); }, 25_000);
  };
  ws.onmessage = (e) => { try { applyMessage(JSON.parse(e.data)); } catch {} };
  ws.onclose = () => { useStore.setState({ connected: false }); ws = null; if (pingTimer) { clearInterval(pingTimer); pingTimer = null; } scheduleReconnect(); };
  ws.onerror = () => ws?.close();
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => { reconnectTimer = null; connectWs(); }, 2000);
}

export function disconnectWs() {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
  ws?.close(); ws = null;
}
