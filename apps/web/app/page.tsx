"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useStore, type Prediction, type ActivityEntry } from "@/lib/ws";
import { GlobalBarSkeleton, NseBarSkeleton, CardGridSkeleton, ActivitySkeleton, HistorySkeleton, SystemInfoSkeleton } from "@/components/skeleton";
import { Tip } from "@/components/tip";
import { cn } from "@/lib/cn";
import {
  TrendingUp, TrendingDown, Minus, Activity, Clock, BarChart3,
  AlertTriangle, Wifi, WifiOff, ArrowUpRight, ArrowDownRight,
  Globe, Gem, Landmark, Droplets, CircleDot, Zap, Timer,
  CheckCircle2, XCircle, Loader2, Radio, ExternalLink,
} from "lucide-react";

function useTick(ms = 1000) { const [, s] = useState(0); useEffect(() => { const i = setInterval(() => s(t => t + 1), ms); return () => clearInterval(i); }, [ms]); }

function parseTimeSec(s: string): number { const m = s.match(/(?:(\d+)\s*days?,?\s*)?(\d+):(\d+):(\d+)/); if (!m) return 0; return +(m[1]||0)*86400+ +m[2]*3600+ +m[3]*60+ +m[4]; }
function fmtDur(s: number): string { if(s<=0)return"0s"; const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60; if(h>0)return`${h}h ${String(m).padStart(2,"0")}m ${String(sec).padStart(2,"0")}s`; return`${m}m ${String(sec).padStart(2,"0")}s`; }

const INST: Record<string,{label:string;icon:typeof Globe;color:string}> = {
  NIFTYBEES:{label:"Nifty 50",icon:BarChart3,color:"text-blue-400"},
  GOLDBEES:{label:"Gold",icon:Gem,color:"text-amber-400"},
  SILVERBEES:{label:"Silver",icon:CircleDot,color:"text-slate-300"},
  BANKBEES:{label:"Bank Nifty",icon:Landmark,color:"text-purple-400"},
};

const GLOBAL_TIPS: Record<string,string> = {
  "S&P 500":"S&P 500 — US large-cap index, strongest predictor of Nifty open",
  Nasdaq:"Nasdaq — US tech index, drives IT sentiment",
  Dow:"Dow Jones Industrial Average",
  Nikkei:"Nikkei 225 — Japan, opens before India",
  "Hang Seng":"Hang Seng — Hong Kong, China risk appetite",
  Crude:"WTI Crude — rising crude bearish for India (net importer)",
  "USD/INR":"Dollar vs Rupee — rising = INR weakening = FII exit",
  Gold:"COMEX Gold futures — primary driver for GOLDBEES",
  DXY:"US Dollar Index — strong dollar = bearish gold/silver",
};

const NSE_TIPS: Record<string,string> = {
  "India VIX":"Volatility Index — >20 = fear (contrarian bullish), <12 = complacency",
  "VIX Chg":"VIX daily change — sharp spikes precede reversals",
  "FII":"Foreign Institutional net buy/sell (crores) — strongest Indian predictor",
  "DII":"Domestic Institutional net buy/sell — counterbalances FII",
  "PCR":"Put-Call Ratio (OI) — >1.2 bullish, <0.8 bearish. Market hours only",
  "A/D":"Advance/Decline ratio — >1.5 broad rally, <0.5 broad selloff",
};

const METRIC_TIPS: Record<string,string> = {
  RSI:"RSI (14) — <30 oversold (buy), >70 overbought (sell)",
  MACD:"MACD Histogram — positive = bullish momentum",
  BB:"Bollinger position — 0.0 = lower band (oversold), 1.0 = upper (overbought)",
  Vol:"Volume vs 20-day avg — >1.5x = confirms the move",
  EMA:"EMA 9/21 — Bull = uptrend, Bear = downtrend",
  Sent:"News sentiment (-1 to +1) from recent headlines",
};

// ── Header ──────────────────────────────────────────────────────

function Header() {
  useTick();
  const {connected,status,session,collectionCount,updatedAt,lastWsMessage}=useStore();
  const tto=status?.market?.time_to_open?parseTimeSec(status.market.time_to_open):0;
  const elapsed=lastWsMessage?Math.floor((Date.now()-lastWsMessage)/1000):0;
  const remaining=Math.max(0,tto-elapsed);
  const updAgo=updatedAt?Math.floor(Date.now()/1000-updatedAt):null;
  // Client-only clock to avoid SSR hydration mismatch
  const [mounted,setMounted]=useState(false);
  useEffect(()=>{setMounted(true)},[]);
  const now=mounted?new Date().toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour12:false}):"--:--:--";
  const sc:Record<string,{l:string;c:string;dot?:boolean}>={
    pre_market:{l:"PRE-MKT",c:"text-amber-400 bg-amber-500/10 border-amber-500/25"},
    pre_open:{l:"PRE-OPEN",c:"text-amber-400 bg-amber-500/10 border-amber-500/25"},
    regular:{l:"LIVE",c:"text-emerald-400 bg-emerald-500/10 border-emerald-500/25",dot:true},
    closing:{l:"CLOSING",c:"text-red-400 bg-red-500/10 border-red-500/25",dot:true},
    post_market:{l:"CLOSED",c:"text-zinc-500 bg-zinc-800 border-zinc-700"},
    closed:{l:"CLOSED",c:"text-zinc-600 bg-zinc-900 border-zinc-800"},
  };
  const s=sc[session]??sc.closed;
  return(
    <header className="sticky top-0 z-50 bg-[#0a0a0f]/95 backdrop-blur-md border-b border-zinc-800/60 select-none">
      <div className="max-w-[1600px] mx-auto px-5 h-11 flex items-center justify-between text-xs">
        <div className="flex items-center gap-3">
          <Zap className="h-4 w-4 text-blue-500"/><Link href="/" className="font-bold text-sm tracking-tight text-zinc-100 hover:text-white">TRADE-PLUS</Link>
          <Link href="/trades" className="text-[10px] text-zinc-500 hover:text-zinc-300 border border-zinc-800 hover:border-zinc-600 px-2 py-0.5 rounded transition-colors">Trades</Link>
          <Tip text="Current NSE session"><span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded border font-bold tracking-widest text-[10px] cursor-help",s.c)}>
            {s.dot&&<span className="relative flex h-1.5 w-1.5"><span className="animate-ping absolute h-full w-full rounded-full bg-current opacity-40"/><span className="relative rounded-full h-1.5 w-1.5 bg-current"/></span>}{s.l}
          </span></Tip>
        </div>
        <div className="flex items-center gap-3 font-mono tabular-nums text-zinc-300">
          <span className="text-sm text-zinc-100">{now}</span><span className="text-zinc-600">IST</span>
          {session!=="regular"&&remaining>0&&(<><span className="text-zinc-800">|</span><Tip text="Countdown to NSE market open at 9:15 AM IST"><span className="flex items-center gap-1.5 text-amber-400 cursor-help"><Timer className="h-3.5 w-3.5"/>{fmtDur(remaining)}</span></Tip></>)}
          {session==="regular"&&<span className="text-emerald-400 font-bold ml-1">TRADING</span>}
        </div>
        <div className="flex items-center gap-4">
          {updAgo!=null&&<Tip text="Seconds since last data collection"><span className="text-zinc-600 cursor-help">{updAgo}s ago</span></Tip>}
          <Tip text="Pipeline cycles completed"><span className="text-zinc-700 font-mono cursor-help">#{collectionCount}</span></Tip>
          <Tip text={connected?"WebSocket live — real-time updates":"Disconnected — reconnecting..."}>
            <span className={cn("flex items-center gap-1 font-semibold cursor-help",connected?"text-emerald-500":"text-red-500")}>
              {connected?<><Wifi className="h-3.5 w-3.5"/>WS</>:<><WifiOff className="h-3.5 w-3.5"/>OFF</>}
            </span></Tip>
        </div>
      </div>
    </header>
  );
}

// ── Global + NSE data strips ────────────────────────────────────

function DataStrip({items,tips}:{items:[string,number|undefined][];tips:Record<string,string>}) {
  const cols=items.length;
  return(
    <div className={cn("grid gap-px bg-zinc-800/30 rounded-lg overflow-hidden border border-zinc-800/50")} style={{gridTemplateColumns:`repeat(${cols},minmax(0,1fr))`}}>
      {items.map(([label,val])=>(
        <Tip key={label} text={tips[label]??label}>
          <div className="bg-[#0d0d12] px-3 py-2 text-center cursor-help">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-0.5">{label}</p>
            <p className={cn("text-xs font-mono font-bold tabular-nums",
              val==null?"text-zinc-800":val>0.01?"text-emerald-400":val<-0.01?"text-red-400":"text-zinc-500"
            )}>{val!=null?`${val>0?"+":""}${val.toFixed(2)}${Math.abs(val)<100?"%":""}`:"--"}</p>
          </div>
        </Tip>
      ))}
    </div>
  );
}

function GlobalBar(){
  const{predictions}=useStore();
  const idx=predictions.find(p=>p.instrument==="NIFTYBEES");
  const gold=predictions.find(p=>p.instrument==="GOLDBEES");
  const ss=idx?.sector_signals; if(!ss)return null;
  const items:[string,number|undefined][]=[
    ["S&P 500",ss.sp500_change],["Nasdaq",ss.nasdaq_change],["Dow",ss.dow_change],
    ["Nikkei",ss.nikkei_change],["Hang Seng",ss.hangseng_change],
    ["Crude",ss.crude_oil_change],["USD/INR",ss.usd_inr_change],
    ["Gold",gold?.sector_signals?.gold_comex_change],["DXY",gold?.sector_signals?.dxy_change],
  ];
  return <DataStrip items={items} tips={GLOBAL_TIPS}/>;
}

function NseBar(){
  const{predictions}=useStore();
  const idx=predictions.find(p=>p.nse_data);const n=idx?.nse_data;if(!n)return null;
  const items:[string,number|undefined][]=[
    ["India VIX",n.india_vix],["VIX Chg",n.india_vix_change],
    ["FII",n.fii_net],["DII",n.dii_net],
    ["PCR",n.pcr_oi||undefined],["A/D",n.ad_ratio],
  ];
  return <DataStrip items={items} tips={NSE_TIPS}/>;
}

// ── Instrument card ─────────────────────────────────────────────

function Card({pred,seq}:{pred:Prediction;seq:number}){
  const md=pred.market_data;const meta=INST[pred.instrument]??{label:pred.instrument,icon:Globe,color:"text-zinc-400"};
  const Icon=meta.icon;const isUp=(md?.change_pct??0)>=0;
  const prev=useRef(seq);const[flash,setFlash]=useState(false);
  useEffect(()=>{if(seq!==prev.current){prev.current=seq;setFlash(true);const t=setTimeout(()=>setFlash(false),800);return()=>clearTimeout(t);}},[seq]);
  const dc=pred.direction==="LONG"?"emerald":pred.direction==="SHORT"?"red":"zinc";
  return(
    <div className={cn("rounded-xl border bg-[#0c0c11] transition-all duration-300",
      pred.direction==="LONG"?"border-emerald-900/40":pred.direction==="SHORT"?"border-red-900/40":"border-zinc-800/50",
      flash&&"ring-1 ring-blue-500/30")}>
      <div className={cn("h-0.5 rounded-t-xl",`bg-${dc}-500/50`)}/>
      <div className="p-3.5 space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className={cn("h-4 w-4",meta.color)}/>
            <span className="text-sm font-semibold text-zinc-200">{meta.label}</span>
            <span className="text-[10px] text-zinc-600">{pred.instrument}</span>
            <Tip text={pred.method==="ensemble"?"Prediction blends ML model + rule-based analysis":pred.method==="ml"?"ML model only":"Rule-based analysis only"}>
              <span className="text-[8px] text-zinc-600 bg-zinc-800 px-1 py-px rounded cursor-help uppercase tracking-wider">{pred.method}</span>
            </Tip>
          </div>
          <Tip text={pred.direction==="LONG"?"BUY signal — expects price UP":pred.direction==="SHORT"?"SELL signal — expects price DOWN":"No clear signal"}>
            <span className={cn("text-[10px] font-black tracking-widest px-2 py-0.5 rounded cursor-help",
              pred.direction==="LONG"?"text-emerald-400 bg-emerald-500/10":pred.direction==="SHORT"?"text-red-400 bg-red-500/10":"text-zinc-600 bg-zinc-800")}>
              {pred.direction==="LONG"&&<TrendingUp className="inline h-3 w-3 mr-1 -mt-px"/>}
              {pred.direction==="SHORT"&&<TrendingDown className="inline h-3 w-3 mr-1 -mt-px"/>}
              {pred.direction==="FLAT"&&<Minus className="inline h-3 w-3 mr-1 -mt-px"/>}
              {pred.direction}
            </span></Tip>
        </div>
        {md&&(<div className="flex items-end justify-between">
          <div><span className={cn("text-2xl font-bold font-mono tabular-nums tracking-tight",flash?"text-blue-200":"text-zinc-50")}>{md.price?.toFixed(2)}</span>
            <span className={cn("text-sm font-mono font-semibold ml-2",isUp?"text-emerald-400":"text-red-400")}>
              {isUp?<ArrowUpRight className="inline h-3.5 w-3.5 -mt-0.5"/>:<ArrowDownRight className="inline h-3.5 w-3.5 -mt-0.5"/>}{md.change_pct>=0?"+":""}{md.change_pct?.toFixed(2)}%
            </span></div>
          <Tip text="Score: -1.0 (strong sell) to +1.0 (strong buy). Confidence = signal strength.">
            <div className="text-right cursor-help"><span className={cn("text-xl font-bold font-mono tabular-nums",pred.score>0.05?"text-emerald-400":pred.score<-0.05?"text-red-400":"text-zinc-600")}>{pred.score>0?"+":""}{pred.score.toFixed(2)}</span>
            <p className="text-[10px] text-zinc-500">{(pred.confidence*100).toFixed(0)}% conf / {pred.features_used}f</p></div></Tip>
        </div>)}
        <Tip text="Score bar — left = SHORT, right = LONG, fills proportionally"><div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden relative cursor-help">
          <div className="absolute top-0 bottom-0 left-1/2 w-px bg-zinc-700 z-10"/>
          <div className={cn("absolute top-0 bottom-0 rounded-full transition-all duration-500",pred.score>0?"bg-emerald-500":"bg-red-500")} style={{left:pred.score>=0?"50%":`${50-Math.abs(pred.score)*50}%`,width:`${Math.abs(pred.score)*50}%`}}/>
        </div></Tip>
        <div className="space-y-0.5">
          {pred.reasons?.slice(0,3).map((r,i)=>(<p key={i} className="text-[11px] text-zinc-400 leading-snug"><span className={cn("inline-block h-1 w-1 rounded-full mr-1.5 align-middle",pred.direction==="LONG"?"bg-emerald-600":pred.direction==="SHORT"?"bg-red-600":"bg-zinc-700")}/>{r}</p>))}
        </div>
        {/* Technicals row */}
        {md&&(<div className="grid grid-cols-5 gap-px bg-zinc-800/30 rounded overflow-hidden">
          {([["RSI",md.rsi_14?.toFixed(0),md.rsi_14<30?"text-emerald-400":md.rsi_14>70?"text-red-400":"text-zinc-300"],
            ["MACD",(md.macd_histogram>0?"+":"")+md.macd_histogram?.toFixed(1),md.macd_histogram>0?"text-emerald-400":"text-red-400"],
            ["BB",md.bb_position?.toFixed(2),md.bb_position<0.2?"text-emerald-400":md.bb_position>0.8?"text-red-400":"text-zinc-400"],
            ["Vol",md.volume_ratio?.toFixed(1)+"x",md.volume_ratio>1.5?"text-blue-400":"text-zinc-400"],
            ["EMA",md.ema_9>md.ema_21?"Bull":"Bear",md.ema_9>md.ema_21?"text-emerald-400":"text-red-400"],
          ] as const).map(([l,v,c])=>(<Tip key={l} text={METRIC_TIPS[l]??l}><div className="bg-[#0a0a0f] py-1.5 px-1 text-center cursor-help"><p className="text-[9px] text-zinc-600 uppercase tracking-wider mb-0.5">{l}</p><p className={cn("text-[11px] font-mono font-semibold tabular-nums",c)}>{v}</p></div></Tip>))}
        </div>)}
        {/* Sentiment: 3 sources */}
        {md&&(<div className="grid grid-cols-3 gap-px bg-zinc-800/30 rounded overflow-hidden">
          <Tip text="RSS news sentiment from MoneyControl, ET, LiveMint, Google News (VADER scored)"><div className="bg-[#0a0a0f] py-1.5 px-2 cursor-help">
            <p className="text-[8px] text-zinc-600 uppercase tracking-wider">RSS News</p>
            <p className={cn("text-[11px] font-mono font-semibold tabular-nums",md.news_sentiment>0.1?"text-emerald-400":md.news_sentiment<-0.1?"text-red-400":"text-zinc-400")}>{md.news_sentiment?.toFixed(3)}</p>
            <p className="text-[8px] text-zinc-700">{md.news_count} headlines</p>
          </div></Tip>
          <Tip text="X/Twitter sentiment via xAI Grok — real-time social media sentiment about this instrument"><div className="bg-[#0a0a0f] py-1.5 px-2 cursor-help">
            <p className="text-[8px] text-zinc-600 uppercase tracking-wider">X/Twitter</p>
            <p className={cn("text-[11px] font-mono font-semibold tabular-nums",md.social_sentiment>0.1?"text-emerald-400":md.social_sentiment<-0.1?"text-red-400":"text-zinc-500")}>{md.social_post_count>0?md.social_sentiment?.toFixed(3):"—"}</p>
            <p className="text-[8px] text-zinc-700">{md.social_post_count>0?`${md.social_post_count} posts`:"no data"}</p>
          </div></Tip>
          <Tip text="AI news search via Parallel AI — real-time articles with deduplication, VADER scored"><div className="bg-[#0a0a0f] py-1.5 px-2 cursor-help">
            <p className="text-[8px] text-zinc-600 uppercase tracking-wider">AI News</p>
            <p className={cn("text-[11px] font-mono font-semibold tabular-nums",md.ai_news_sentiment>0.1?"text-emerald-400":md.ai_news_sentiment<-0.1?"text-red-400":"text-zinc-500")}>{md.ai_news_count>0?md.ai_news_sentiment?.toFixed(3):"—"}</p>
            <p className="text-[8px] text-zinc-700">{md.ai_news_count>0?`${md.ai_news_count} articles (+${md.ai_news_positive}/-${md.ai_news_negative})`:"no data"}</p>
          </div></Tip>
        </div>)}
        {/* Returns + ensemble */}
        {md&&(<div className="flex gap-3 text-[10px] flex-wrap">
          {([["1D",md.returns_1d,"1-day return"],["5D",md.returns_5d,"5-day return"],["10D",md.returns_10d,"10-day return"]] as const).map(([l,v,t])=>(
            <Tip key={l} text={t}><span className={cn("font-mono tabular-nums cursor-help",v>0?"text-emerald-500/70":v<0?"text-red-500/70":"text-zinc-700")}>{l}:{v>0?"+":""}{v?.toFixed(1)}%</span></Tip>
          ))}
          {pred.ensemble&&(<Tip text={`Ensemble blend: ML score ${pred.ensemble.ml_score>0?"+":""}${pred.ensemble.ml_score.toFixed(2)} (${pred.ensemble.ml_confidence>0?(pred.ensemble.ml_confidence*100).toFixed(0)+"%":"?"}) + Rules ${pred.ensemble.rules_score>0?"+":""}${pred.ensemble.rules_score.toFixed(2)}`}>
            <span className="text-zinc-600 font-mono cursor-help ml-auto">
              ML:{pred.ensemble.ml_score>0?"+":""}{pred.ensemble.ml_score.toFixed(2)} R:{pred.ensemble.rules_score>0?"+":""}{pred.ensemble.rules_score.toFixed(2)}
            </span>
          </Tip>)}
        </div>)}
      </div>
    </div>
  );
}

// ── Pipeline Activity ───────────────────────────────────────────

function ActivityLog(){
  const{activity,collectionCount}=useStore();useTick();
  if(!activity.length&&collectionCount===0) return(<div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] p-4 flex items-center gap-3 text-zinc-400 text-sm"><Loader2 className="h-4 w-4 animate-spin text-blue-500"/>Waiting for first pipeline cycle...</div>);
  return(
    <div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] overflow-hidden flex flex-col">
      <div className="px-4 py-2 border-b border-zinc-800/40 flex items-center justify-between shrink-0">
        <Tip text="Shows each data collection cycle — what was collected, predictions made, and next cycle countdown"><div className="flex items-center gap-2 cursor-help"><Radio className="h-3.5 w-3.5 text-blue-500"/><span className="text-xs font-bold text-zinc-300 uppercase tracking-wider">Pipeline Activity</span></div></Tip>
        <span className="text-[10px] text-zinc-600 font-mono">{activity.length} runs</span>
      </div>
      <div className="flex-1 overflow-y-auto max-h-[400px]">
        {[...activity].reverse().map((a,i)=>(<ActivityRow key={a.run_id||a.cycle} entry={a} isLatest={i===0}/>))}
      </div>
    </div>
  );
}

function ActivityRow({entry,isLatest}:{entry:ActivityEntry;isLatest:boolean}){
  useTick();
  const isOk=entry.status==="ok";const time=entry.timestamp?.split("T")[1]?.substring(0,8)??"";
  // Countdown uses absolute next_run_at (unix seconds) — survives reload
  const nextRunAt=entry.next_run_at??0;
  const liveRem=isLatest&&nextRunAt>0?Math.max(0,Math.floor(nextRunAt-Date.now()/1000)):0;
  return(
    <Link href={`/run/${entry.run_id||entry.cycle}`} className={cn("block px-4 py-2 border-b border-zinc-800/20 hover:bg-zinc-800/20 transition-colors",isLatest&&"bg-blue-500/[0.03]")}>
      <div className="flex items-center gap-2 mb-1">
        {isOk?<CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0"/>:<XCircle className="h-3.5 w-3.5 text-red-500 shrink-0"/>}
        <span className="font-mono text-xs text-zinc-300 tabular-nums">{time}</span>
        <span className="text-xs text-zinc-600">#{entry.cycle}</span>
        <span className={cn("px-1.5 py-px rounded text-[9px] font-bold tracking-wider",entry.session==="regular"?"text-emerald-500 bg-emerald-500/10":"text-zinc-500 bg-zinc-800")}>{entry.session?.toUpperCase()}</span>
        {entry.duration_sec!=null&&<Tip text="Collection + prediction duration"><span className="text-xs text-zinc-500 font-mono cursor-help">{entry.duration_sec}s</span></Tip>}
        <ExternalLink className="h-3 w-3 text-zinc-700 ml-auto shrink-0"/>
        {isLatest&&liveRem>0&&(<Tip text="Live countdown to next collection"><span className="text-xs text-amber-400 font-mono font-bold tabular-nums cursor-help flex items-center gap-1"><Timer className="h-3 w-3"/>next in {fmtDur(liveRem)}</span></Tip>)}
        {isLatest&&liveRem===0&&nextRunAt>0&&<span className="text-xs text-blue-400 font-mono flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin"/>collecting...</span>}
      </div>
      {isOk&&entry.predictions&&(
        <div className="flex flex-wrap gap-x-4 gap-y-0.5 ml-6 text-xs">
          {Object.entries(entry.predictions).map(([ticker,p])=>(
            <div key={ticker} className="flex items-center gap-1.5">
              <span className="text-zinc-500">{INST[ticker]?.label??ticker}</span>
              <span className={cn("font-mono font-bold tabular-nums",p.direction==="LONG"?"text-emerald-400":p.direction==="SHORT"?"text-red-400":"text-zinc-600")}>{p.score>0?"+":""}{p.score.toFixed(2)}</span>
              <span className="text-zinc-700 font-mono text-[10px]">{p.features}f</span>
              {p.errors?.length>0&&<Tip text={`Errors: ${p.errors.join(", ")}`}><AlertTriangle className="h-3 w-3 text-amber-500 cursor-help"/></Tip>}
            </div>
          ))}
        </div>
      )}
      {!isOk&&entry.error&&<p className="text-xs text-red-400/80 ml-6 truncate">{entry.error}</p>}
    </Link>
  );
}

// ── History table ───────────────────────────────────────────────

function HistoryTable(){
  const{history,predictions,collectionCount}=useStore();const tickers=predictions.map(p=>p.instrument);
  const rows=[...history].reverse().slice(0,20);
  return(
    <div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] overflow-hidden flex flex-col">
      <div className="px-4 py-2 border-b border-zinc-800/40 flex items-center gap-2 shrink-0">
        <Tip text="Prediction scores over time — tracks how signals evolve across cycles"><div className="flex items-center gap-2 cursor-help"><Clock className="h-3.5 w-3.5 text-zinc-500"/><span className="text-xs font-bold text-zinc-300 uppercase tracking-wider">Signal History</span></div></Tip>
        <span className="text-[10px] text-zinc-600 ml-auto">{history.length} snapshot{history.length!==1?"s":""}</span>
      </div>
      {rows.length<2?(
        <div className="flex-1 flex flex-col items-center justify-center py-8 gap-2 text-zinc-600">
          <Clock className="h-5 w-5 text-zinc-700"/>
          <p className="text-xs">Awaiting more data</p>
          <p className="text-[10px] text-zinc-700">{history.length} of 2 cycles needed to show comparison</p>
          <p className="text-[10px] text-zinc-800">Next cycle will populate this table</p>
        </div>
      ):(
        <div className="flex-1 overflow-y-auto max-h-[400px]">
          <table className="w-full text-xs"><thead><tr className="text-zinc-500 bg-zinc-900/50 sticky top-0">
            <th className="text-left py-1.5 px-3 font-medium">Time</th>
            {tickers.map(t=>(<th key={t} className="text-center py-1.5 px-2 font-medium">{INST[t]?.label??t}</th>))}
          </tr></thead><tbody>
            {rows.map((e,i)=>(<tr key={i} className={cn("border-t border-zinc-800/20",i===0&&"bg-blue-500/[0.03]")}>
              <td className="py-1.5 px-3 font-mono text-zinc-400 tabular-nums">{e.timestamp?.split("T")[1]?.substring(0,8)}</td>
              {tickers.map(t=>{const d=e.instruments?.[t];if(!d)return<td key={t} className="text-center py-1.5 px-2 text-zinc-800">--</td>;
                return(<td key={t} className="text-center py-1.5 px-2"><span className={cn("font-mono font-bold tabular-nums",d.direction==="LONG"?"text-emerald-400":d.direction==="SHORT"?"text-red-400":"text-zinc-700")}>{d.score>0?"+":""}{d.score?.toFixed(2)}</span><span className="text-zinc-600 ml-1.5">{d.price?.toFixed(0)}</span></td>);
              })}
            </tr>))}
          </tbody></table>
        </div>
      )}
    </div>
  );
}

// ── System info panel (fills space) ─────────────────────────────

function SystemInfo(){
  const{status,predictions,collectionCount}=useStore();
  const ms=status?.market;const sv=status?.server;
  if(!ms)return null;
  return(
    <div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] p-4 space-y-3">
      <p className="text-xs font-bold text-zinc-400 uppercase tracking-wider">System Status</p>
      <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs">
        <div className="flex justify-between"><span className="text-zinc-500">Trading Day</span><span className={ms.is_trading_day?"text-emerald-400":"text-zinc-600"}>{ms.is_trading_day?"Yes":"No"}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">Can Trade</span><span className={ms.can_trade?"text-emerald-400":"text-zinc-600"}>{ms.can_trade?"Yes":"No"}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">New Positions</span><span className={ms.can_open_new?"text-emerald-400":"text-zinc-600"}>{ms.can_open_new?"Allowed":"Blocked"}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">Square Off</span><span className={ms.should_squareoff?"text-red-400":"text-zinc-600"}>{ms.should_squareoff?"ACTIVE":"No"}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">Holiday</span><span className={ms.is_holiday?"text-amber-400":"text-zinc-600"}>{ms.is_holiday?"Yes":"No"}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">Collect Signals</span><span className={ms.should_collect_signals?"text-emerald-400":"text-zinc-600"}>{ms.should_collect_signals?"Active":"Idle"}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">WS Clients</span><span className="text-zinc-300">{sv?.ws_clients??0}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">Pipeline Cycles</span><span className="text-zinc-300">{collectionCount}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">Instruments</span><span className="text-zinc-300">{predictions.length}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">Total Features</span><span className="text-zinc-300">{predictions.reduce((s,p)=>s+p.features_used,0)}</span></div>
      </div>
      {sv?.errors&&sv.errors.length>0&&(
        <div className="mt-2 space-y-1"><p className="text-[10px] text-red-400 font-bold uppercase">Errors</p>{sv.errors.map((e,i)=>(<p key={i} className="text-[10px] text-red-400/70 truncate">{e}</p>))}</div>
      )}
    </div>
  );
}

// ── Main ────────────────────────────────────────────────────────

export default function Home(){
  useTick();
  const{connected,predictions,status,updateSeq,activity,history,trading}=useStore();
  const hasPreds = predictions.length > 0;
  const isLoading = connected && !hasPreds;
  const isDisconnected = !connected && !hasPreds;

  return(
    <div className="flex flex-col min-h-screen bg-[#08080c] text-zinc-100 font-sans">
      <Header/>
      <main className="flex-1 max-w-[1600px] mx-auto w-full px-5 py-3 flex flex-col gap-3">
        {/* Alerts */}
        {isDisconnected&&(
          <div className="flex items-center gap-2 bg-amber-500/5 border border-amber-500/15 rounded-lg px-4 py-3 text-xs text-amber-400/80"><Loader2 className="h-4 w-4 animate-spin"/>Connecting... run <code className="font-mono bg-zinc-800 px-1.5 py-0.5 rounded">python -m trade_plus.api</code></div>
        )}
        {status?.market?.should_squareoff&&(
          <div className="flex items-center gap-2 bg-red-500/8 border border-red-500/20 rounded-lg px-4 py-2.5 text-xs text-red-400 font-bold animate-pulse"><AlertTriangle className="h-4 w-4"/>SQUARE OFF — Close MIS before 3:20 PM</div>
        )}

        {/* Trading summary bar — always visible */}
        {trading && (
          <Link href="/trades" className={cn("flex items-center justify-between rounded-lg border px-4 py-2 transition-colors hover:brightness-110",
            !trading.day_trades ? "border-zinc-800/50 bg-zinc-900/30" : trading.day_pnl >= 0 ? "border-emerald-900/30 bg-emerald-500/[0.03]" : "border-red-900/30 bg-red-500/[0.03]"
          )}>
            <div className="flex items-center gap-4 text-xs">
              <span className="text-zinc-400 font-semibold">Paper Trading</span>
              <span className="text-zinc-600">Capital: Rs {trading.capital?.toFixed(0)}</span>
              <span className={cn("font-mono font-bold", trading.day_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                P&L: Rs {trading.day_pnl >= 0 ? "+" : ""}{trading.day_pnl?.toFixed(2)}
              </span>
              <span className="text-zinc-600">Trades: {trading.day_trades}</span>
              {trading.day_trades > 0 && <span className="text-zinc-600">Win: {(trading.win_rate * 100)?.toFixed(0)}%</span>}
              <span className={cn("text-zinc-600", trading.open_position_count > 0 && "text-blue-400")}>Positions: {trading.open_position_count}</span>
            </div>
            <span className="text-[10px] text-zinc-600">View details →</span>
          </Link>
        )}

        {/* Global + NSE bars */}
        {hasPreds ? <GlobalBar/> : <GlobalBarSkeleton/>}
        {hasPreds ? <NseBar/> : <NseBarSkeleton/>}

        {/* Instrument cards */}
        {hasPreds
          ? <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">{predictions.map(p=><Card key={p.instrument} pred={p} seq={updateSeq}/>)}</div>
          : <CardGridSkeleton/>}

        {/* Bottom 3-col */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 flex-1 min-h-0">
          {activity.length > 0 ? <ActivityLog/> : <ActivitySkeleton/>}
          {!hasPreds ? <HistorySkeleton/> : <HistoryTable/>}
          {status ? <SystemInfo/> : <SystemInfoSkeleton/>}
        </div>
      </main>
      <footer className="border-t border-zinc-800/30 py-2 text-center text-[10px] text-zinc-700">
        Trade-Plus v0.1 | Yahoo Finance + NSE India | Not financial advice | {status?.server?.ws_clients??0} clients
      </footer>
    </div>
  );
}
