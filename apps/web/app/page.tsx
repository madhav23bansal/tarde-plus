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
} from "lucide-react";

function useTick(ms=1000){const[,s]=useState(0);useEffect(()=>{const i=setInterval(()=>s(t=>t+1),ms);return()=>clearInterval(i)},[ms])}
function parseTimeSec(s:string):number{const m=s.match(/(?:(\d+)\s*days?,?\s*)?(\d+):(\d+):(\d+)/);if(!m)return 0;return +(m[1]||0)*86400+ +m[2]*3600+ +m[3]*60+ +m[4]}
function fmtDur(s:number):string{if(s<=0)return"0s";const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;if(h>0)return`${h}h${String(m).padStart(2,"0")}m`;return m>0?`${m}m${String(sec).padStart(2,"0")}s`:`${sec}s`}

const INST:Record<string,{label:string;short:string;icon:typeof Globe}>={
  NIFTYBEES:{label:"Nifty 50",short:"NIFTY",icon:BarChart3},
  BANKBEES:{label:"Bank Nifty",short:"BANK",icon:Landmark},
  SETFNIF50:{label:"SBI Nifty",short:"SBI",icon:BarChart3},
};

export default function Home(){
  useTick();
  const{connected,predictions,status,updateSeq,trading,activity,momentum,livePrices,lastWsMessage,updatedAt,collectionCount}=useStore();
  const hasPreds=predictions.length>0;
  const tto=status?.market?.time_to_open?parseTimeSec(status.market.time_to_open):0;
  const elapsed=lastWsMessage?Math.floor((Date.now()-lastWsMessage)/1000):0;
  const remaining=Math.max(0,tto-elapsed);
  const session=status?.market?.session??"closed";
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
        <Link href="/trades" className="text-zinc-500 hover:text-zinc-200 transition-colors border border-zinc-800 hover:border-zinc-600 px-2 py-0.5 rounded">Trades</Link>

        {/* Session */}
        <span className={cn("px-1.5 py-px rounded font-bold tracking-widest text-[9px]",
          session==="regular"?"text-emerald-400 bg-emerald-500/10":"text-zinc-500 bg-zinc-800")}>
          {session==="regular"?"LIVE":session==="pre_market"?"PRE-MKT":"CLOSED"}
        </span>

        <span className="ml-auto"/>

        {/* Trading P&L always visible */}
        {trading&&(
          <Link href="/trades" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
            <span className={cn("font-mono font-bold",trading.day_pnl>=0?"text-emerald-400":"text-red-400")}>{trading.day_pnl>=0?"+":""}₹{trading.day_pnl?.toFixed(2)}</span>
            <span className="text-zinc-600">{trading.day_trades}t</span>
            {trading.open_position_count>0&&<span className="text-blue-400">{trading.open_position_count}p</span>}
          </Link>
        )}

        <span className="text-zinc-700">|</span>
        <span className="font-mono tabular-nums text-zinc-300">{now}</span>
        {session!=="regular"&&remaining>0&&<span className="text-amber-400 font-mono tabular-nums"><Timer className="h-3 w-3 inline -mt-px mr-0.5"/>{fmtDur(remaining)}</span>}
        <span className={cn("text-sm",connected?"text-emerald-500":"text-red-500")}>●</span>
      </div>

      {/* ━━━ ALERTS ━━━ */}
      {!connected&&!hasPreds&&(
        <div className="mx-4 mt-3 flex items-center gap-2 bg-amber-500/5 border border-amber-500/15 rounded-lg px-3 py-2 text-xs text-amber-400/80"><Loader2 className="h-3.5 w-3.5 animate-spin"/>Connecting to API...</div>
      )}
      {status?.market?.should_squareoff&&(
        <div className="mx-4 mt-3 flex items-center gap-2 bg-red-500/8 border border-red-500/20 rounded-lg px-3 py-2 text-xs text-red-400 font-bold animate-pulse"><AlertTriangle className="h-3.5 w-3.5"/>SQUARE OFF</div>
      )}

      {/* ━━━ MAIN CONTENT ━━━ */}
      <div className="flex-1 max-w-[1440px] mx-auto w-full px-4 py-3 space-y-3">

        {/* Market context - compact horizontal strip */}
        {hasPreds&&(()=>{
          const p=predictions[0];
          const nse=p.nse_data;const ss=p.sector_signals;
          const items:[string,number|undefined,boolean?][]=[
            ["S&P",ss?.sp500_change],["Crude",ss?.crude_oil_change],
            ["VIX",nse?.india_vix,true],["FII",nse?.fii_net,true],["DII",nse?.dii_net,true],
          ];
          return(
            <div className="flex gap-1.5">
              {items.map(([l,v,abs])=>(
                <div key={l as string} className="bg-[#0c0c11] border border-zinc-800/30 rounded px-2.5 py-1 min-w-[72px]">
                  <p className="text-[8px] text-zinc-600 uppercase">{l as string}</p>
                  <p className={cn("text-[12px] font-mono font-bold tabular-nums",
                    v==null?"text-zinc-700":abs?(typeof v==="number"&&Math.abs(v)>20?"text-amber-400":"text-zinc-300"):
                    (typeof v==="number"&&v>0?"text-emerald-400":typeof v==="number"&&v<0?"text-red-400":"text-zinc-500"))}>
                    {v!=null?(abs?
                      (typeof v==="number"&&Math.abs(v)>100?`${(v/1000).toFixed(1)}K`:typeof v==="number"?v.toFixed(1):"--"):
                      `${typeof v==="number"&&v>0?"+":""}${typeof v==="number"?v.toFixed(2):"--"}%`):"--"}
                  </p>
                </div>
              ))}
            </div>
          );
        })()}

        {/* ━━━ INSTRUMENT CARDS ━━━ */}
        {hasPreds?(
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {predictions.map(p=><Card key={p.instrument} pred={p} seq={updateSeq}/>)}
          </div>
        ):(
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {[0,1,2].map(i=><div key={i} className="bg-[#0c0c11] border border-zinc-800/30 rounded-xl h-[220px] animate-pulse"/>)}
          </div>
        )}

        {/* ━━━ PIPELINE + SYSTEM ━━━ */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
          {/* Pipeline runs - 3/4 width */}
          <div className="lg:col-span-3 bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
            <div className="px-3 py-2 border-b border-zinc-800/20 flex items-center justify-between text-[10px]">
              <span className="text-zinc-500 font-semibold uppercase tracking-wider">Pipeline</span>
              <span className="text-zinc-600 font-mono">{activity.length} runs · cycle #{collectionCount}</span>
            </div>
            {!activity.length?(
              <div className="p-4 text-xs text-zinc-600 text-center">Waiting for first cycle...</div>
            ):(
              <div className="max-h-[200px] overflow-y-auto">
                {[...activity].reverse().map((a,i)=>{
                  const time=a.timestamp?.split("T")[1]?.substring(0,8)??"";
                  const nextAt=a.next_run_at??0;
                  const rem=i===0&&nextAt>0?Math.max(0,Math.floor(nextAt-Date.now()/1000)):0;
                  return(
                    <div key={a.run_id||a.cycle} className={cn("px-3 py-1.5 flex items-center gap-2 text-[11px] border-b border-zinc-800/10",i===0&&"bg-blue-500/[0.02]")}>
                      {a.status==="ok"?<CheckCircle2 className="h-3 w-3 text-emerald-500/70 shrink-0"/>:<XCircle className="h-3 w-3 text-red-500/70 shrink-0"/>}
                      <span className="font-mono text-zinc-500 tabular-nums w-16">{time}</span>
                      {a.predictions&&Object.entries(a.predictions).map(([t,p]:[string,any])=>(
                        <span key={t} className={cn("font-mono tabular-nums",p.direction==="LONG"?"text-emerald-400/80":p.direction==="SHORT"?"text-red-400/80":"text-zinc-600")}>
                          {INST[t]?.short??t} {p.score>0?"+":""}{p.score?.toFixed(2)}
                        </span>
                      ))}
                      {a.duration_sec!=null&&<span className="text-zinc-700 font-mono ml-auto">{a.duration_sec}s</span>}
                      {i===0&&rem>0&&<span className="text-amber-400/80 font-mono tabular-nums"><Timer className="h-2.5 w-2.5 inline -mt-px"/> {fmtDur(rem)}</span>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* System - 1/4 width */}
          <div className="bg-[#0c0c11] border border-zinc-800/30 rounded-xl p-3 text-[11px] space-y-1.5">
            <p className="text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">System</p>
            {status&&(<>
              <Row l="Session" v={session} c={session==="regular"?"text-emerald-400":undefined}/>
              <Row l="Trading" v={status.market.can_trade?"Yes":"No"} c={status.market.can_trade?"text-emerald-400":"text-zinc-600"}/>
              {status.market.is_holiday&&<Row l="Holiday" v="Yes" c="text-amber-400"/>}
              <Row l="Redis" v="●" c={status.server.db.redis?"text-emerald-400":"text-red-400"}/>
              <Row l="TSDB" v="●" c={status.server.db.timescaledb?"text-emerald-400":"text-red-400"}/>
              <Row l="Broker" v={trading?.broker??"—"}/>
              <Row l="Capital" v={`₹${trading?.capital?.toFixed(0)??"50,000"}`}/>
              <Row l="Leverage" v={`${trading?.leverage??5}x`}/>
            </>)}
          </div>
        </div>
      </div>

      {/* ━━━ BOTTOM BAR ━━━ */}
      <div className="sticky bottom-0 bg-[#0a0a0f] border-t border-zinc-800/60 px-4 py-1.5 flex items-center gap-4 text-[10px] z-50">
        {trading&&<>
          <span className="text-zinc-600">Pos <span className={trading.open_position_count>0?"text-blue-400 font-bold":"text-zinc-500"}>{trading.open_position_count}</span></span>
          <span className="text-zinc-600">P&L <span className={cn("font-mono font-bold",trading.day_pnl>=0?"text-emerald-400":"text-red-400")}>{trading.day_pnl>=0?"+":""}₹{trading.day_pnl?.toFixed(2)}</span></span>
          <span className="text-zinc-600">Unrlz <span className={cn("font-mono",trading.total_unrealized_pnl>=0?"text-emerald-400/70":"text-red-400/70")}>{trading.total_unrealized_pnl>=0?"+":""}₹{trading.total_unrealized_pnl?.toFixed(2)}</span></span>
          <span className="text-zinc-600">Trades <span className="text-zinc-400">{trading.day_trades}</span></span>
          {trading.day_trades>0&&<span className="text-zinc-600">Win <span className="text-zinc-400">{(trading.win_rate*100).toFixed(0)}%</span></span>}
        </>}
        <span className="ml-auto text-zinc-700 font-mono tabular-nums">#{collectionCount}{updAgo!=null?` · ${updAgo}s`:""}</span>
        <span className={cn("text-base leading-none",connected?"text-emerald-500":"text-red-500")}>●</span>
      </div>
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────

function Row({l,v,c}:{l:string;v:string;c?:string}){
  return<div className="flex justify-between"><span className="text-zinc-600">{l}</span><span className={c??"text-zinc-300"}>{v}</span></div>;
}

// ── Instrument Card ─────────────────────────────────────────────

function Card({pred,seq}:{pred:Prediction;seq:number}){
  const md=pred.market_data;
  const meta=INST[pred.instrument]??{label:pred.instrument,short:pred.instrument.slice(0,4),icon:Globe};
  const Icon=meta.icon;
  const{trading,livePrices}=useStore();
  const pos=trading?.positions?.[pred.instrument];
  const lp=livePrices?.[pred.instrument];
  const price=lp?.price||md?.price||0;
  const isUp=(md?.change_pct??0)>=0;
  const prev=useRef(seq);const[flash,setFlash]=useState(false);
  useEffect(()=>{if(seq!==prev.current){prev.current=seq;setFlash(true);const t=setTimeout(()=>setFlash(false),600);return()=>clearTimeout(t)}},[seq]);
  const dc=pred.direction==="LONG"?"emerald":pred.direction==="SHORT"?"red":"zinc";

  return(
    <div className={cn("rounded-xl border bg-[#0c0c11] overflow-hidden",
      pred.direction==="LONG"?"border-emerald-500/15":pred.direction==="SHORT"?"border-red-500/15":"border-zinc-800/40")}>
      <div className={cn("h-[2px]",`bg-${dc}-500/40`)}/>

      <div className="p-3 space-y-2">
        {/* Header: name + direction + score — all on one dense line */}
        <div className="flex items-center gap-2">
          <Icon className={cn("h-3.5 w-3.5",`text-${dc}-400`)}/>
          <span className="text-sm font-semibold text-zinc-200 flex-1">{meta.label}</span>
          <span className={cn("text-[10px] font-black tracking-wider px-1.5 py-px rounded",
            `text-${dc}-400 bg-${dc}-500/10`)}>
            {pred.direction==="LONG"?<TrendingUp className="inline h-3 w-3 mr-0.5 -mt-px"/>:
             pred.direction==="SHORT"?<TrendingDown className="inline h-3 w-3 mr-0.5 -mt-px"/>:
             <Minus className="inline h-3 w-3 mr-0.5 -mt-px"/>}
            {pred.direction}
          </span>
          <span className={cn("text-lg font-bold font-mono tabular-nums",
            pred.score>0.05?"text-emerald-400":pred.score<-0.05?"text-red-400":"text-zinc-600")}>
            {pred.score>0?"+":""}{pred.score?.toFixed(2)}
          </span>
        </div>

        {/* Price — big and prominent */}
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

        {/* Reasons — compact */}
        {pred.reasons && pred.reasons.length > 0 && (
          <p className="text-[10px] text-zinc-500 leading-snug">
            {pred.reasons.slice(0, 2).join(" | ")}
          </p>
        )}

        {/* Data grid: RSI, 1D, 5D, AI — dense 4-col */}
        {md&&(
          <div className="grid grid-cols-4 gap-px rounded overflow-hidden text-center">
            {([
              ["RSI",md.rsi_14?.toFixed(0),md.rsi_14<30?"text-emerald-400":md.rsi_14>70?"text-red-400":"text-zinc-300"],
              ["1D",`${md.returns_1d>0?"+":""}${md.returns_1d?.toFixed(1)}%`,md.returns_1d>0?"text-emerald-400/80":"text-red-400/80"],
              ["5D",`${md.returns_5d>0?"+":""}${md.returns_5d?.toFixed(1)}%`,md.returns_5d>0?"text-emerald-400/80":"text-red-400/80"],
              ["Conf",`${(pred.confidence*100).toFixed(0)}%`,"text-zinc-400"],
            ] as const).map(([l,v,c])=>(
              <div key={l} className="bg-zinc-800/20 py-1">
                <p className="text-[8px] text-zinc-600 uppercase">{l}</p>
                <p className={cn("text-[11px] font-mono font-semibold tabular-nums",c)}>{v}</p>
              </div>
            ))}
          </div>
        )}

        {/* S/R Levels + decision — one compact line */}
        {(pred.levels?.levels?.length>0||pred.decision)&&(
          <div className="flex items-center gap-1.5 text-[9px] text-zinc-600 pt-0.5">
            {pred.levels?.levels?.length>0&&(()=>{
              const lvls=pred.levels.levels;
              const sup=lvls.filter((l:any)=>l.type==="support"&&l.price<price).slice(-1)[0];
              const res=lvls.filter((l:any)=>l.type==="resistance"&&l.price>price)[0];
              return<>
                {sup&&<span className="text-emerald-500/50 font-mono">S:{sup.price}</span>}
                {res&&<span className="text-red-500/50 font-mono">R:{res.price}</span>}
              </>;
            })()}
            {pred.levels?.cpr&&<span className={pred.levels.cpr.day_type==="trending"?"text-blue-400/60":"text-amber-400/60"}>{pred.levels.cpr.day_type}</span>}
            {pred.decision&&<span className="ml-auto"><Zap className="inline h-2.5 w-2.5 text-blue-500/50 -mt-px"/> {pred.decision.action}</span>}
          </div>
        )}
      </div>

      {/* Position stripe */}
      {pos&&(
        <div className={cn("px-3 py-1.5 border-t flex items-center justify-between text-[11px]",
          pos.side==="LONG"?"bg-emerald-500/[0.03] border-emerald-500/10":"bg-red-500/[0.03] border-red-500/10")}>
          <span className="text-zinc-500">
            <span className={cn("font-bold",pos.side==="LONG"?"text-emerald-400":"text-red-400")}>{pos.side}</span>
            {" "}{pos.quantity}u@₹{pos.entry_price?.toFixed(2)}
          </span>
          <span className={cn("font-bold font-mono tabular-nums",pos.unrealized_pnl>=0?"text-emerald-400":"text-red-400")}>
            {pos.unrealized_pnl>=0?"+":""}₹{pos.unrealized_pnl?.toFixed(2)}
          </span>
        </div>
      )}
    </div>
  );
}
