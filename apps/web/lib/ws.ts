import { create } from "zustand";

// ── Types ────────────────────────────────────────────────────────

export interface MarketStatus {
  market: {
    time_ist: string;
    session: string;
    is_trading_day: boolean;
    can_trade: boolean;
    can_open_new: boolean;
    should_squareoff: boolean;
    should_collect_signals: boolean;
    time_to_open: string;
    is_holiday: boolean;
  };
  server: {
    collection_count: number;
    last_update: number;
    last_update_ago_sec: number | null;
    errors: string[];
    ws_clients: number;
  };
}

export interface MarketData {
  price: number;
  prev_close: number;
  change_pct: number;
  day_high: number;
  day_low: number;
  volume: number;
  volume_ratio: number;
  rsi_14: number;
  macd_histogram: number;
  bb_position: number;
  ema_9: number;
  ema_21: number;
  atr_14: number;
  returns_1d: number;
  returns_5d: number;
  returns_10d: number;
  news_sentiment: number;
  news_count: number;
  social_sentiment: number;
  social_post_count: number;
  social_trending: string[];
  ai_news_sentiment: number;
  ai_news_count: number;
  ai_news_positive: number;
  ai_news_negative: number;
}

export interface EnsembleData {
  ml_score: number;
  rules_score: number;
  ml_confidence: number;
  rules_confidence: number;
}

export interface NseData {
  fii_net: number;
  dii_net: number;
  india_vix: number;
  india_vix_change: number;
  pcr_oi: number;
  ad_ratio: number;
}

export interface Prediction {
  instrument: string;
  direction: "LONG" | "SHORT" | "FLAT";
  score: number;
  confidence: number;
  reasons: string[];
  features_used: number;
  method: string;
  ensemble?: EnsembleData;
  market_data?: MarketData;
  nse_data?: NseData;
  sector_signals?: Record<string, number>;
}

export interface HistoryEntry {
  timestamp: string;
  session: string;
  instruments: Record<
    string,
    { price: number; change_pct: number; rsi: number; score: number; direction: string; confidence: number }
  >;
}

// ── Store ────────────────────────────────────────────────────────

export interface ActivityEntry {
  run_id: string;
  cycle: number;
  timestamp: string;
  session: string;
  duration_sec?: number;
  next_run_at?: number;  // absolute unix timestamp of next run
  status: string;
  error?: string;
  data_sources?: { global_signals: number; instruments: number };
  predictions?: Record<string, {
    direction: string; score: number; confidence: number;
    price: number; features: number; errors: string[];
  }>;
}

export interface TradingStatus {
  capital: number;
  starting_capital: number;
  buying_power: number;
  leverage: number;
  net_equity: number;
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

interface Store {
  connected: boolean;
  status: MarketStatus | null;
  predictions: Prediction[];
  history: HistoryEntry[];
  activity: ActivityEntry[];
  trading: TradingStatus | null;
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
  history: [],
  activity: [],
  trading: null,
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
      history: msg.history ?? s.history,
      activity: msg.activity ?? s.activity,
      trading: msg.trading ?? s.trading,
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
    // Fast loop trading updates (every 30s during market hours)
    useStore.setState((s) => ({
      trading: msg.trading ?? s.trading,
      lastWsMessage: now,
    }));
  }
}

export function connectWs() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;

  try {
    ws = new WebSocket("ws://localhost:8000/ws");
  } catch {
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    useStore.setState({ connected: true });
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    // Keepalive ping every 25s
    if (pingTimer) clearInterval(pingTimer);
    pingTimer = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
    }, 25_000);
  };

  ws.onmessage = (event) => {
    try {
      applyMessage(JSON.parse(event.data));
    } catch { /* ignore malformed */ }
  };

  ws.onclose = () => {
    useStore.setState({ connected: false });
    ws = null;
    if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
    scheduleReconnect();
  };

  ws.onerror = () => ws?.close();
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWs();
  }, 2000);
}

export function disconnectWs() {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
  ws?.close();
  ws = null;
}
