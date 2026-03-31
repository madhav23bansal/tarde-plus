"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useStore, type Prediction } from "@/lib/ws";
import { Tip } from "@/components/tip";
import { cn } from "@/lib/cn";
import {
  TrendingUp, TrendingDown, Minus, BarChart3, Wifi, WifiOff,
  ArrowUpRight, ArrowDownRight, Globe, Landmark, Zap, Timer,
  Loader2, DollarSign, CheckCircle2, XCircle, AlertTriangle,
  Activity, Shield, Brain, Layers,
} from "lucide-react";

function useTick(ms=1000){const[,s]=useState(0);useEffect(()=>{const i=setInterval(()=>s(t=>t+1),ms);return()=>clearInterval(i)},[ms])}
function parseTimeSec(s:string):number{const m=s.match(/(?:(\d+)\s*days?,?\s*)?(\d+):(\d+):(\d+)/);if(!m)return 0;return +(m[1]||0)*86400+ +m[2]*3600+ +m[3]*60+ +m[4]}
function fmtDur(s:number):string{if(s<=0)return"0s";const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;if(h>0)return`${h}h${String(m).padStart(2,"0")}m`;return m>0?`${m}m${String(sec).padStart(2,"0")}s`:`${sec}s`}

const I:Record<string,{l:string;s:string;icon:typeof Globe}>={
  NIFTYBEES:{l:"Nifty 50",s:"NIFTY",icon:BarChart3},
  BANKBEES:{l:"Bank Nifty",s:"BANK",icon:Landmark},
  SETFNIF50:{l:"SBI Nifty",s:"SBI",icon:BarChart3},
};

// Fetch momentum endpoint for engine state (not in WS during market close)
function useMomentum(){
  const[data,setData]=useState<any>(null);
  useEffect(()=>{
    const f=()=>fetch("/api/trading/momentum").then(r=>r.json()).then(d=>{if(!d.error)setData(d.momentum)}).catch(()=>{});
    f();const i=setInterval(f,10000);return()=>clearInterval(i);
  },[]);
  const wsMom=useStore(s=>s.momentum);
  return wsMom??data;
}

// Fetch history for score trend
function useHistory(){
  const[data,setData]=useState<any[]>([]);
  useEffect(()=>{
    fetch("/api/history").then(r=>r.json()).then(d=>setData(d.history??[])).catch(()=>{});
  },[]);
  return data;
}

export default function Home(){
  useTick();
  const{connected,predictions,status,updateSeq,trading,activity,livePrices,updatedAt,collectionCount,lastWsMessage}=useStore();
  const mom=useMomentum();
  const history=useHistory();
  const hasPreds=predictions.length>0;
  const session=status?.market?.session??"closed";
  const tto=status?.market?.time_to_open?parseTimeSec(status.market.time_to_open):0;
  const elapsed=lastWsMessage?Math.floor((Date.now()-lastWsMessage)/1000):0;
  const remaining=Math.max(0,tto-elapsed);
  const[mounted,setMounted]=useState(false);
  useEffect(()=>{setMounted(true)},[]);
  const now=mounted?new Date().toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour12:false}):"--:--:--";
  const updAgo=updatedAt?Math.floor(Date.now()/1000-updatedAt):null;

  return(
    <div className="min-h-screen bg-[#08080c] text-zinc-100 font-sans flex flex-col">

      {/* ━━━ TOP BAR ━━━ */}
      <div className="bg-[#0a0a0f] border-b border-zinc-800/60 px-4 py-2 flex items-center gap-3 text-[11px] sticky top-0 z-50">
        <Zap className="h-4 w-4 text-blue-500"/>
        <span className="font-bold text-sm text-zinc-100">Trade-Plus</span>
        <Link href="/trades" className="text-zinc-500 hover:text-zinc-200 border border-zinc-800 hover:border-zinc-600 px-2 py-0.5 rounded transition-all">Trades</Link>
        <span className={cn("px-1.5 py-px rounded font-bold tracking-widest text-[9px]",
          session==="regular"?"text-emerald-400 bg-emerald-500/10":session==="pre_market"?"text-amber-400 bg-amber-500/10":"text-zinc-500 bg-zinc-800")}>
          {session==="regular"?"LIVE":session==="pre_market"?"PRE-MKT":"CLOSED"}
        </span>
        <span className="ml-auto"/>
        {trading&&(
          <Link href="/trades" className="flex items-center gap-2 hover:opacity-80">
            <span className={cn("font-mono font-bold",trading.day_pnl>=0?"text-emerald-400":"text-red-400")}>{trading.day_pnl>=0?"+":""}₹{trading.day_pnl?.toFixed(2)}</span>
            <span className="text-zinc-600">{trading.day_trades}t {trading.open_position_count}p</span>
          </Link>
        )}
        <span className="text-zinc-700">|</span>
        <span className="font-mono tabular-nums text-zinc-300">{now}</span>
        {session!=="regular"&&remaining>0&&<span className="text-amber-400 font-mono tabular-nums"><Timer className="h-3 w-3 inline -mt-px mr-0.5"/>{fmtDur(remaining)}</span>}
        <span className={cn("text-sm",connected?"text-emerald-500":"text-red-500")}>●</span>
      </div>

      {!connected&&!hasPreds&&(
        <div className="mx-4 mt-3 flex items-center gap-2 bg-amber-500/5 border border-amber-500/15 rounded-lg px-3 py-2 text-xs text-amber-400/80"><Loader2 className="h-3.5 w-3.5 animate-spin"/>Connecting...</div>
      )}

      <div className="flex-1 max-w-[1440px] mx-auto w-full px-4 py-3 space-y-3">

        {/* ━━━ MARKET + TRADING STRIP ━━━ */}
        {hasPreds&&(()=>{
          const p=predictions[0];const nse=p.nse_data;const ss=p.sector_signals;const md=p.market_data;
          return(
            <div className="flex gap-1.5 flex-wrap">
              <Pill l="S&P" v={ss?.sp500_change} pct/>
              <Pill l="Crude" v={ss?.crude_oil_change} pct/>
              <Pill l="VIX" v={nse?.india_vix} abs warn={typeof nse?.india_vix==="number"&&nse.india_vix>20}/>
              <Pill l="VIX Δ" v={nse?.india_vix_change} pct/>
              <Pill l="FII" v={nse?.fii_net} abs big/>
              <Pill l="DII" v={nse?.dii_net} abs big/>
              <Pill l="Vol" v={md?.volume_ratio} abs suffix="x"/>
              {(md?.ai_news_count??0)>0&&<Pill l="News" v={md?.ai_news_sentiment} pct/>}
              {trading&&<>
                <div className="ml-auto"/>
                <Pill l="Capital" v={trading.capital} abs prefix="₹" fixed={0}/>
                <Pill l="Power" v={trading.buying_power} abs prefix="₹" fixed={0} big/>
                <Pill l="DD" v={trading.max_drawdown*100} abs suffix="%"/>
              </>}
            </div>
          );
        })()}

        {/* ━━━ INSTRUMENT CARDS ━━━ */}
        {hasPreds?(
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {predictions.map(p=><Card key={p.instrument} pred={p} seq={updateSeq} mom={mom} history={history}/>)}
          </div>
        ):(
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {[0,1,2].map(i=><div key={i} className="bg-[#0c0c11] border border-zinc-800/30 rounded-xl h-[280px] animate-pulse"/>)}
          </div>
        )}

        {/* ━━━ ENGINE STATE + OI + LEVELS ━━━ */}
        {mom&&(
          <div className="bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
            <div className="px-3 py-2 border-b border-zinc-800/20 flex items-center gap-3 text-[10px]">
              <Brain className="h-3.5 w-3.5 text-blue-500/70"/>
              <span className="text-zinc-500 font-semibold uppercase tracking-wider">Engine</span>
              <span className={cn("px-1.5 py-px rounded text-[9px] font-bold",
                mom.time_window==="prime"?"text-emerald-400 bg-emerald-500/10":
                mom.time_window==="orb"?"text-amber-400 bg-amber-500/10":"text-zinc-500 bg-zinc-800")}>
                {mom.time_window?.toUpperCase()??"—"}
              </span>
              <span className="text-zinc-600">Levels: {mom.levels_computed?"✓":"—"}</span>
              <span className="text-zinc-600">ORB: {mom.orb_set?"✓":"—"}</span>
              <span className="text-zinc-600">Mode: {mom.mode}</span>
            </div>

            {/* OI Data */}
            {mom.oi&&Object.keys(mom.oi).length>0&&(
              <div className="px-3 py-2 border-b border-zinc-800/10 flex gap-4 text-[11px]">
                <span className="text-zinc-500"><Layers className="inline h-3 w-3 -mt-px mr-1"/>OI</span>
                {Object.entries(mom.oi).map(([idx,oi]:[string,any])=>(
                  <span key={idx} className="text-zinc-400">
                    <span className="text-zinc-600">{idx}:</span>{" "}
                    <span className="text-red-400/70">R:{oi.oi_resistance}</span>{" "}
                    <span className="text-emerald-400/70">S:{oi.oi_support}</span>{" "}
                    <span className="text-zinc-500">MP:{oi.max_pain}</span>{" "}
                    <span className={oi.pcr>1.2?"text-emerald-400/70":oi.pcr<0.8?"text-red-400/70":"text-zinc-500"}>PCR:{oi.pcr}</span>{" "}
                    <span className={oi.oi_buildup==="bullish"?"text-emerald-400/60":oi.oi_buildup==="bearish"?"text-red-400/60":"text-zinc-600"}>{oi.oi_buildup}</span>
                  </span>
                ))}
              </div>
            )}

            {/* Levels per instrument */}
            {mom.levels&&Object.keys(mom.levels).length>0&&(
              <div className="px-3 py-2 border-b border-zinc-800/10">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {Object.entries(mom.levels).map(([ticker,dl]:[string,any])=>(
                    <div key={ticker}>
                      <p className="text-[9px] text-zinc-600 uppercase tracking-wider mb-1">{I[ticker]?.l??ticker} Levels</p>
                      <div className="flex flex-wrap gap-1">
                        {dl.levels?.sort((a:any,b:any)=>a.price-b.price).map((lv:any)=>(
                          <span key={lv.name} className={cn("text-[10px] font-mono px-1 py-px rounded",
                            lv.type==="support"?"text-emerald-400/60 bg-emerald-500/5":
                            lv.type==="resistance"?"text-red-400/60 bg-red-500/5":"text-zinc-500 bg-zinc-800/50")}>
                            {lv.name}:{lv.price}
                          </span>
                        ))}
                        {(!dl.levels||dl.levels.length===0)&&<span className="text-[10px] text-zinc-700">Computing at market open...</span>}
                      </div>
                      {dl.cpr&&<p className="text-[9px] text-zinc-600 mt-0.5">CPR: {dl.cpr.tc}-{dl.cpr.bc} ({dl.cpr.day_type}) | Gap: {dl.gap?.pct?.toFixed(2)}% {dl.gap?.type}</p>}
                      {dl.orb?.set&&<p className="text-[9px] text-zinc-600">ORB: {dl.orb.high}-{dl.orb.low}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Decisions */}
            {mom.decisions&&Object.keys(mom.decisions).length>0&&(
              <div className="px-3 py-2">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                  {Object.entries(mom.decisions).map(([ticker,d]:[string,any])=>(
                    <div key={ticker} className="flex items-center gap-2 text-[11px]">
                      <span className="text-zinc-500 w-12">{I[ticker]?.s??ticker}</span>
                      <span className={cn("font-bold px-1 py-px rounded text-[10px]",
                        d.action?.includes("ENTER")?"text-blue-400 bg-blue-500/10":
                        d.action==="HOLD"?"text-zinc-400 bg-zinc-800":"text-zinc-600 bg-zinc-800/50")}>{d.action}</span>
                      <span className="text-zinc-600 truncate flex-1">{d.reasons?.[0]??"—"}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ━━━ PIPELINE + SYSTEM ━━━ */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
          <div className="lg:col-span-3 bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
            <div className="px-3 py-2 border-b border-zinc-800/20 flex items-center justify-between text-[10px]">
              <span className="text-zinc-500 font-semibold uppercase tracking-wider">Pipeline</span>
              <span className="text-zinc-600 font-mono">{activity.length} runs</span>
            </div>
            {!activity.length?(
              <div className="p-4 text-xs text-zinc-600 text-center">Waiting...</div>
            ):(
              <div className="max-h-[180px] overflow-y-auto divide-y divide-zinc-800/10">
                {[...activity].reverse().map((a,i)=>{
                  const time=a.timestamp?.split("T")[1]?.substring(0,8)??"";
                  const nextAt=a.next_run_at??0;
                  const rem=i===0&&nextAt>0?Math.max(0,Math.floor(nextAt-Date.now()/1000)):0;
                  return(
                    <div key={a.run_id||a.cycle} className={cn("px-3 py-1.5 flex items-center gap-2 text-[11px]",i===0&&"bg-blue-500/[0.02]")}>
                      {a.status==="ok"?<CheckCircle2 className="h-3 w-3 text-emerald-500/70 shrink-0"/>:<XCircle className="h-3 w-3 text-red-500/70 shrink-0"/>}
                      <span className="font-mono text-zinc-500 tabular-nums w-16">{time}</span>
                      <span className="text-zinc-700">#{a.cycle}</span>
                      {a.session&&<span className="text-zinc-700">{a.session}</span>}
                      {a.predictions&&Object.entries(a.predictions).map(([t,p]:[string,any])=>(
                        <span key={t} className={cn("font-mono tabular-nums",p.direction==="LONG"?"text-emerald-400/80":p.direction==="SHORT"?"text-red-400/80":"text-zinc-600")}>
                          {I[t]?.s??t}:{p.score>0?"+":""}{p.score?.toFixed(2)}
                        </span>
                      ))}
                      {a.duration_sec!=null&&<span className="text-zinc-700 font-mono">{a.duration_sec}s</span>}
                      {i===0&&rem>0&&<span className="text-amber-400/80 font-mono tabular-nums ml-auto"><Timer className="h-2.5 w-2.5 inline -mt-px mr-0.5"/>{fmtDur(rem)}</span>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="bg-[#0c0c11] border border-zinc-800/30 rounded-xl p-3 text-[11px] space-y-1.5">
            <p className="text-zinc-500 font-semibold uppercase tracking-wider text-[10px] mb-2">System</p>
            {status&&(<>
              <R l="Session" v={session} c={session==="regular"?"text-emerald-400":undefined}/>
              <R l="Trading" v={status.market.can_trade?"Active":"Inactive"} c={status.market.can_trade?"text-emerald-400":"text-zinc-600"}/>
              {status.market.is_holiday&&<R l="Holiday" v="Yes" c="text-amber-400"/>}
              <R l="Redis" v={status.server.db.redis?"Connected":"Down"} c={status.server.db.redis?"text-emerald-400":"text-red-400"}/>
              <R l="TSDB" v={status.server.db.timescaledb?"Connected":"Down"} c={status.server.db.timescaledb?"text-emerald-400":"text-red-400"}/>
              <R l="Capital" v={`₹${trading?.capital?.toFixed(0)??"50,000"}`}/>
              <R l="Power" v={`₹${trading?.buying_power?.toFixed(0)??"250,000"}`}/>
              <R l="Leverage" v={`${trading?.leverage??5}x`}/>
              <R l="Broker" v={trading?.broker??"shoonya"}/>
              <R l="Cycles" v={String(collectionCount)}/>
              <R l="Updated" v={updAgo!=null?`${updAgo}s ago`:"—"}/>
              <R l="WS" v={`${status.server.ws_clients} clients`}/>
            </>)}
          </div>
        </div>

        {/* ━━━ SCORE HISTORY ━━━ */}
        {history.length>1&&(
          <div className="bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
            <div className="px-3 py-2 border-b border-zinc-800/20 text-[10px] text-zinc-500 font-semibold uppercase tracking-wider">
              Score History <span className="font-mono font-normal text-zinc-600 ml-1">{history.length} snapshots</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead><tr className="text-zinc-600">
                  <th className="text-left py-1.5 px-3 font-medium">Time</th>
                  {Object.keys(history[0]?.instruments??{}).map(t=>(
                    <th key={t} className="text-center py-1.5 px-2 font-medium">{I[t]?.s??t}</th>
                  ))}
                </tr></thead>
                <tbody>{[...history].reverse().slice(0,10).map((h,i)=>(
                  <tr key={i} className={cn("border-t border-zinc-800/10",i===0&&"bg-blue-500/[0.02]")}>
                    <td className="py-1 px-3 font-mono text-zinc-500 tabular-nums">{h.timestamp?.split("T")[1]?.substring(0,8)}</td>
                    {Object.entries(h.instruments??{}).map(([t,d]:[string,any])=>(
                      <td key={t} className="py-1 px-2 text-center">
                        <span className={cn("font-mono font-bold tabular-nums",
                          d.direction==="LONG"?"text-emerald-400/80":d.direction==="SHORT"?"text-red-400/80":"text-zinc-600")}>
                          {d.score>0?"+":""}{d.score?.toFixed(2)}
                        </span>
                        <span className="text-zinc-700 ml-1 font-mono">{typeof d.price==="number"?d.price.toFixed(0):""}</span>
                      </td>
                    ))}
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* ━━━ BOTTOM BAR ━━━ */}
      <div className="sticky bottom-0 bg-[#0a0a0f] border-t border-zinc-800/60 px-4 py-1.5 flex items-center gap-4 text-[10px] z-50">
        {trading&&<>
          <span className="text-zinc-600">Pos <span className={trading.open_position_count>0?"text-blue-400 font-bold":"text-zinc-500"}>{trading.open_position_count}</span></span>
          <span className="text-zinc-600">P&L <span className={cn("font-mono font-bold",trading.day_pnl>=0?"text-emerald-400":"text-red-400")}>{trading.day_pnl>=0?"+":""}₹{trading.day_pnl?.toFixed(2)}</span></span>
          <span className="text-zinc-600">Unrlz <span className={cn("font-mono",trading.total_unrealized_pnl>=0?"text-emerald-400/70":"text-red-400/70")}>{trading.total_unrealized_pnl>=0?"+":""}₹{trading.total_unrealized_pnl?.toFixed(2)}</span></span>
          <span className="text-zinc-600">Equity <span className="text-zinc-400 font-mono">₹{(trading.capital+(trading.total_unrealized_pnl??0)).toFixed(0)}</span></span>
          <span className="text-zinc-600">DD <span className="text-zinc-400 font-mono">{(trading.max_drawdown*100).toFixed(1)}%</span></span>
        </>}
        <span className="ml-auto text-zinc-700 font-mono tabular-nums">#{collectionCount}{updAgo!=null?` · ${updAgo}s`:""}</span>
        <span className={cn("text-base leading-none",connected?"text-emerald-500":"text-red-500")}>●</span>
      </div>
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────

function R({l,v,c}:{l:string;v:string;c?:string}){
  return<div className="flex justify-between"><span className="text-zinc-600">{l}</span><span className={c??"text-zinc-300"}>{v}</span></div>;
}

function Pill({l,v,pct,abs,big,warn,prefix,suffix,fixed}:{l:string;v:any;pct?:boolean;abs?:boolean;big?:boolean;warn?:boolean;prefix?:string;suffix?:string;fixed?:number}){
  if(v==null)return null;
  const n=typeof v==="number"?v:0;
  const f=fixed??2;
  const display=abs?
    (big&&Math.abs(n)>100?`${prefix??""}${(n/1000).toFixed(1)}K${suffix??""}`:
    `${prefix??""}${n.toFixed(f)}${suffix??""}`):
    `${n>0?"+":""}${n.toFixed(f)}${suffix??"%"}`;
  const color=warn?"text-amber-400":abs?"text-zinc-300":n>0?"text-emerald-400":n<0?"text-red-400":"text-zinc-500";
  return(
    <div className="bg-[#0c0c11] border border-zinc-800/30 rounded px-2 py-1 min-w-[60px]">
      <p className="text-[8px] text-zinc-600 uppercase leading-none">{l}</p>
      <p className={cn("text-[11px] font-mono font-bold tabular-nums leading-tight",color)}>{display}</p>
    </div>
  );
}

// ── Instrument Card ─────────────────────────────────────────────

function Card({pred,seq,mom,history}:{pred:Prediction;seq:number;mom:any;history:any[]}){
  const md=pred.market_data;
  const meta=I[pred.instrument]??{l:pred.instrument,s:pred.instrument.slice(0,4),icon:Globe};
  const Icon=meta.icon;
  const{trading,livePrices}=useStore();
  const pos=trading?.positions?.[pred.instrument];
  const lp=livePrices?.[pred.instrument];
  const price=lp?.price||md?.price||0;
  const isUp=(md?.change_pct??0)>=0;
  const prev=useRef(seq);const[flash,setFlash]=useState(false);
  useEffect(()=>{if(seq!==prev.current){prev.current=seq;setFlash(true);const t=setTimeout(()=>setFlash(false),600);return()=>clearTimeout(t)}},[seq]);
  const dir=pred.direction;

  // Score trend from history
  const trend=history.filter(h=>h.instruments?.[pred.instrument]).map(h=>h.instruments[pred.instrument].score).slice(-5);

  // Decision from momentum
  const decision=mom?.decisions?.[pred.instrument];

  return(
    <div className={cn("rounded-xl border bg-[#0c0c11] overflow-hidden",
      dir==="LONG"?"border-emerald-500/10":dir==="SHORT"?"border-red-500/10":"border-zinc-800/30")}>
      <div className={cn("h-[2px]",dir==="LONG"?"bg-emerald-500/30":dir==="SHORT"?"bg-red-500/30":"bg-zinc-700/30")}/>
      <div className="p-3 space-y-2">

        {/* Name + Direction + Score */}
        <div className="flex items-center gap-2">
          <Icon className={cn("h-3.5 w-3.5",dir==="LONG"?"text-emerald-400":dir==="SHORT"?"text-red-400":"text-zinc-400")}/>
          <span className="text-[13px] font-semibold text-zinc-200 flex-1">{meta.l}</span>
          <span className={cn("text-[10px] font-black tracking-wider px-1.5 py-px rounded",
            dir==="LONG"?"text-emerald-400 bg-emerald-500/10":dir==="SHORT"?"text-red-400 bg-red-500/10":"text-zinc-500 bg-zinc-800")}>
            {dir==="LONG"?<TrendingUp className="inline h-3 w-3 mr-0.5 -mt-px"/>:
             dir==="SHORT"?<TrendingDown className="inline h-3 w-3 mr-0.5 -mt-px"/>:
             <Minus className="inline h-3 w-3 mr-0.5 -mt-px"/>}
            {dir}
          </span>
          <span className={cn("text-lg font-bold font-mono tabular-nums",
            dir==="LONG"?"text-emerald-400":dir==="SHORT"?"text-red-400":"text-zinc-500")}>{pred.score>0?"+":""}{pred.score?.toFixed(2)}</span>
        </div>

        {/* Price */}
        <div className="flex items-baseline justify-between">
          <p className={cn("text-[26px] font-bold font-mono tabular-nums leading-none tracking-tight transition-colors duration-500",flash?"text-blue-200":"text-zinc-50")}>
            {price>0?`₹${price.toFixed(2)}`:"—"}
          </p>
          {md&&<span className={cn("text-xs font-mono flex items-center gap-0.5",isUp?"text-emerald-400":"text-red-400")}>
            {isUp?<ArrowUpRight className="h-3 w-3"/>:<ArrowDownRight className="h-3 w-3"/>}
            {md.change_pct>=0?"+":""}{md.change_pct?.toFixed(2)}%
          </span>}
        </div>

        {/* Score bar */}
        <div className="h-[3px] bg-zinc-800 rounded-full overflow-hidden relative">
          <div className="absolute top-0 bottom-0 left-1/2 w-px bg-zinc-700 z-10"/>
          <div className={cn("absolute top-0 bottom-0 rounded-full transition-all duration-700",
            pred.score>0?"bg-gradient-to-r from-emerald-600 to-emerald-400":"bg-gradient-to-l from-red-600 to-red-400")}
            style={{left:pred.score>=0?"50%":`${50-Math.abs(pred.score)*50}%`,width:`${Math.abs(pred.score)*50}%`}}/>
        </div>

        {/* Reasons */}
        {pred.reasons&&pred.reasons.length>0&&(
          <p className="text-[10px] text-zinc-500 leading-snug">{pred.reasons.slice(0,2).join(" | ")}</p>
        )}

        {/* Data grid: 8 cells instead of 4 */}
        {md&&(
          <div className="grid grid-cols-4 gap-px rounded overflow-hidden">
            <Cell l="RSI" v={md.rsi_14?.toFixed(0)} c={md.rsi_14<30?"text-emerald-400":md.rsi_14>70?"text-red-400":"text-zinc-300"}/>
            <Cell l="Vol" v={md.volume_ratio?.toFixed(1)+"x"} c={md.volume_ratio>1.5?"text-blue-400":"text-zinc-400"}/>
            <Cell l="1D" v={`${md.returns_1d>0?"+":""}${md.returns_1d?.toFixed(1)}%`} c={md.returns_1d>0?"text-emerald-400/80":"text-red-400/80"}/>
            <Cell l="5D" v={`${md.returns_5d>0?"+":""}${md.returns_5d?.toFixed(1)}%`} c={md.returns_5d>0?"text-emerald-400/80":"text-red-400/80"}/>
          </div>
        )}

        {/* Ensemble + confidence row */}
        <div className="flex items-center gap-2 text-[10px] text-zinc-600">
          {pred.ensemble&&<>
            <span>ML:<span className={cn("font-mono",pred.ensemble.ml_score>0?"text-emerald-400/60":"text-red-400/60")}>{pred.ensemble.ml_score>0?"+":""}{pred.ensemble.ml_score?.toFixed(2)}</span></span>
            <span>Rules:<span className={cn("font-mono",pred.ensemble.rules_score>0?"text-emerald-400/60":"text-red-400/60")}>{pred.ensemble.rules_score>0?"+":""}{pred.ensemble.rules_score?.toFixed(2)}</span></span>
          </>}
          <span className="ml-auto">{(pred.confidence*100).toFixed(0)}% conf · {pred.method}</span>
        </div>

        {/* Score trend */}
        {trend.length>1&&(
          <div className="flex items-center gap-1 text-[9px]">
            <span className="text-zinc-600">Trend:</span>
            {trend.map((s,i)=>(
              <span key={i} className={cn("font-mono tabular-nums",s>0?"text-emerald-400/50":"text-red-400/50")}>{s>0?"+":""}{s.toFixed(2)}</span>
            ))}
          </div>
        )}

        {/* S/R + decision */}
        {(pred.levels?.levels?.length>0||decision)&&(
          <div className="flex items-center gap-1.5 text-[9px] text-zinc-600 border-t border-zinc-800/20 pt-1.5">
            {pred.levels?.levels?.length>0&&(()=>{
              const lvls=pred.levels.levels;
              const sup=lvls.filter((l:any)=>l.type==="support"&&l.price<price).slice(-1)[0];
              const res=lvls.filter((l:any)=>l.type==="resistance"&&l.price>price)[0];
              return<>
                {sup&&<span className="text-emerald-500/40 font-mono">S:{sup.name}={sup.price}</span>}
                {res&&<span className="text-red-500/40 font-mono">R:{res.name}={res.price}</span>}
              </>;
            })()}
            {pred.levels?.cpr&&<span className={pred.levels.cpr.day_type==="trending"?"text-blue-400/50":"text-amber-400/50"}>{pred.levels.cpr.day_type}</span>}
            {decision&&<span className="ml-auto"><Zap className="inline h-2.5 w-2.5 text-blue-500/40 -mt-px"/> <span className="font-semibold">{decision.action}</span></span>}
          </div>
        )}
      </div>

      {/* Position stripe */}
      {pos&&(
        <div className={cn("px-3 py-1.5 border-t flex items-center justify-between text-[11px]",
          pos.side==="LONG"?"bg-emerald-950/20 border-emerald-500/10":"bg-red-950/20 border-red-500/10")}>
          <span className="text-zinc-500"><span className={cn("font-bold",pos.side==="LONG"?"text-emerald-400":"text-red-400")}>{pos.side}</span> {pos.quantity}u@₹{pos.entry_price?.toFixed(2)}</span>
          <span className={cn("font-bold font-mono tabular-nums",pos.unrealized_pnl>=0?"text-emerald-400":"text-red-400")}>{pos.unrealized_pnl>=0?"+":""}₹{pos.unrealized_pnl?.toFixed(2)}</span>
        </div>
      )}
    </div>
  );
}

function Cell({l,v,c}:{l:string;v:string;c:string}){
  return<div className="bg-zinc-800/20 py-1 text-center"><p className="text-[8px] text-zinc-600 uppercase leading-none">{l}</p><p className={cn("text-[11px] font-mono font-semibold tabular-nums leading-tight",c)}>{v}</p></div>;
}
