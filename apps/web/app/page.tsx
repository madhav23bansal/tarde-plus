"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useStore, type Prediction } from "@/lib/ws";
import { Tip } from "@/components/tip";
import { cn } from "@/lib/cn";
import {
  TrendingUp, TrendingDown, Minus, Activity, Clock, BarChart3,
  AlertTriangle, Wifi, WifiOff, ArrowUpRight, ArrowDownRight,
  Globe, Landmark, Zap, Timer, Loader2, Radio, ExternalLink,
  CheckCircle2, XCircle, DollarSign,
} from "lucide-react";

function useTick(ms=1000){const[,s]=useState(0);useEffect(()=>{const i=setInterval(()=>s(t=>t+1),ms);return()=>clearInterval(i)},[ms])}
function parseTimeSec(s:string):number{const m=s.match(/(?:(\d+)\s*days?,?\s*)?(\d+):(\d+):(\d+)/);if(!m)return 0;return +(m[1]||0)*86400+ +m[2]*3600+ +m[3]*60+ +m[4]}
function fmtDur(s:number):string{if(s<=0)return"0s";const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;if(h>0)return`${h}h ${String(m).padStart(2,"0")}m ${String(sec).padStart(2,"0")}s`;return`${m}m ${String(sec).padStart(2,"0")}s`}

const INST:Record<string,{label:string;icon:typeof Globe;color:string}>={
  NIFTYBEES:{label:"Nifty 50",icon:BarChart3,color:"text-blue-400"},
  BANKBEES:{label:"Bank Nifty",icon:Landmark,color:"text-purple-400"},
  SETFNIF50:{label:"SBI Nifty 50",icon:BarChart3,color:"text-cyan-400"},
};

const GLOBAL_TIPS:Record<string,string>={
  "S&P 500":"US large-cap index — strongest predictor of Nifty opening",
  "Crude":"WTI Crude Oil — rising crude is bearish for India",
  "USD/INR":"Dollar vs Rupee — rising = INR weakening = FII exit",
};
const NSE_TIPS:Record<string,string>={
  "VIX":"India VIX — >20 = fear (contrarian bullish), <12 = complacency",
  "VIX Chg":"VIX daily change — sharp spikes precede reversals",
  "FII":"FII net buy/sell (crores) — strongest Indian predictor",
  "DII":"DII net buy/sell — counterbalances FII",
};

// ── Header ──────────────────────────────────────────────────────

function Header(){
  useTick();
  const{connected,status,session,collectionCount,updatedAt,lastWsMessage}=useStore();
  const tto=status?.market?.time_to_open?parseTimeSec(status.market.time_to_open):0;
  const elapsed=lastWsMessage?Math.floor((Date.now()-lastWsMessage)/1000):0;
  const remaining=Math.max(0,tto-elapsed);
  const updAgo=updatedAt?Math.floor(Date.now()/1000-updatedAt):null;
  const[mounted,setMounted]=useState(false);
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
          <Zap className="h-4 w-4 text-blue-500"/>
          <Link href="/" className="font-bold text-sm tracking-tight text-zinc-100 hover:text-white">TRADE-PLUS</Link>
          <Link href="/trades" className="text-[10px] text-zinc-500 hover:text-zinc-300 border border-zinc-800 hover:border-zinc-600 px-2 py-0.5 rounded transition-colors">Trades</Link>
          <Tip text="Current NSE market session">
            <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded border font-bold tracking-widest text-[10px] cursor-help",s.c)}>
              {s.dot&&<span className="relative flex h-1.5 w-1.5"><span className="animate-ping absolute h-full w-full rounded-full bg-current opacity-40"/><span className="relative rounded-full h-1.5 w-1.5 bg-current"/></span>}
              {s.l}
            </span>
          </Tip>
        </div>
        <div className="flex items-center gap-3 font-mono tabular-nums text-zinc-300">
          <span className="text-sm text-zinc-100">{now}</span>
          <span className="text-zinc-600">IST</span>
          {session!=="regular"&&remaining>0&&(<>
            <span className="text-zinc-800">|</span>
            <Tip text="Countdown to NSE market open"><span className="flex items-center gap-1.5 text-amber-400 cursor-help"><Timer className="h-3.5 w-3.5"/>{fmtDur(remaining)}</span></Tip>
          </>)}
          {session==="regular"&&<span className="text-emerald-400 font-bold ml-1">TRADING</span>}
        </div>
        <div className="flex items-center gap-4">
          {updAgo!=null&&<Tip text="Seconds since last collection"><span className="text-zinc-600 cursor-help">{updAgo}s ago</span></Tip>}
          <Tip text="Pipeline cycles"><span className="text-zinc-700 font-mono cursor-help">#{collectionCount}</span></Tip>
          <Tip text={connected?"WebSocket connected":"Disconnected"}>
            <span className={cn("flex items-center gap-1 font-semibold cursor-help",connected?"text-emerald-500":"text-red-500")}>
              {connected?<><Wifi className="h-3.5 w-3.5"/>WS</>:<><WifiOff className="h-3.5 w-3.5"/>OFF</>}
            </span>
          </Tip>
        </div>
      </div>
    </header>
  );
}

// ── Global + NSE Data Bars ──────────────────────────────────────

function MarketBar(){
  const{predictions}=useStore();
  const idx=predictions.find(p=>p.instrument==="NIFTYBEES")||predictions[0];
  const ss=idx?.sector_signals;
  const nse=idx?.nse_data;
  if(!ss&&!nse)return null;

  return(
    <div className="grid grid-cols-7 gap-px bg-zinc-800/30 rounded-lg overflow-hidden border border-zinc-800/50">
      {([
        ["S&P 500",ss?.sp500_change,GLOBAL_TIPS["S&P 500"]],
        ["Crude",ss?.crude_oil_change,GLOBAL_TIPS["Crude"]],
        ["USD/INR",nse?.india_vix_change,GLOBAL_TIPS["USD/INR"]],
        ["VIX",nse?.india_vix,NSE_TIPS["VIX"],true],
        ["FII",nse?.fii_net,NSE_TIPS["FII"],true],
        ["DII",nse?.dii_net,NSE_TIPS["DII"],true],
        ["VIX Chg",nse?.india_vix_change,NSE_TIPS["VIX Chg"]],
      ] as const).map(([label,val,tip,isLevel])=>(
        <Tip key={label as string} text={(tip as string)||label as string}>
          <div className="bg-[#0d0d12] px-3 py-2 text-center cursor-help">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-0.5">{label as string}</p>
            <p className={cn("text-xs font-mono font-bold tabular-nums flex items-center justify-center gap-0.5",
              val==null?"text-zinc-800":
              isLevel?(typeof val==="number"&&val>20?"text-amber-400":"text-zinc-300"):
              (typeof val==="number"&&val>0.01?"text-emerald-400":typeof val==="number"&&val<-0.01?"text-red-400":"text-zinc-500")
            )}>
              {typeof val==="number"&&!isLevel&&val>0.01&&<ArrowUpRight className="h-2.5 w-2.5"/>}
              {typeof val==="number"&&!isLevel&&val<-0.01&&<ArrowDownRight className="h-2.5 w-2.5"/>}
              {val!=null?(isLevel?`${typeof val==="number"?val.toFixed(1):val}`:`${typeof val==="number"&&val>0?"+":""}${typeof val==="number"?val.toFixed(2):val}${!isLevel&&typeof val==="number"&&Math.abs(val)<1000?"%":""}`):"--"}
            </p>
          </div>
        </Tip>
      ))}
    </div>
  );
}

// ── Instrument Card ─────────────────────────────────────────────

function Card({pred,seq}:{pred:Prediction;seq:number}){
  const md=pred.market_data;
  const meta=INST[pred.instrument]??{label:pred.instrument,icon:Globe,color:"text-zinc-400"};
  const Icon=meta.icon;
  const isUp=(md?.change_pct??0)>=0;
  const prev=useRef(seq);const[flash,setFlash]=useState(false);
  useEffect(()=>{if(seq!==prev.current){prev.current=seq;setFlash(true);const t=setTimeout(()=>setFlash(false),800);return()=>clearTimeout(t)}},[seq]);
  const{trading,momentum,livePrices}=useStore();
  const pos=trading?.positions?.[pred.instrument];
  const mom=(momentum as any)?.decisions?.[pred.instrument];
  const lp=livePrices?.[pred.instrument];
  const dc=pred.direction==="LONG"?"emerald":pred.direction==="SHORT"?"red":"zinc";

  // Use live price if available, fall back to snapshot
  const displayPrice=lp?.price||md?.price||0;

  return(
    <div className={cn("rounded-xl border bg-[#0c0c11] transition-all duration-300 relative",
      pred.direction==="LONG"?"border-emerald-900/40":pred.direction==="SHORT"?"border-red-900/40":"border-zinc-800/50")}>
      <div className={cn("h-0.5 rounded-t-xl",`bg-${dc}-500/50`)}/>

      <div className="p-4 space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className={cn("h-4 w-4",meta.color)}/>
            <span className="text-sm font-semibold text-zinc-200">{meta.label}</span>
            <span className="text-[10px] text-zinc-600">{pred.instrument}</span>
            <span className="text-[8px] text-zinc-600 bg-zinc-800 px-1 py-px rounded uppercase tracking-wider">{pred.method||"rules"}</span>
          </div>
          <Tip text={pred.direction==="LONG"?"BUY signal":pred.direction==="SHORT"?"SELL signal":"No signal"}>
            <span className={cn("text-[10px] font-black tracking-widest px-2 py-0.5 rounded cursor-help",
              pred.direction==="LONG"?"text-emerald-400 bg-emerald-500/10":pred.direction==="SHORT"?"text-red-400 bg-red-500/10":"text-zinc-600 bg-zinc-800")}>
              {pred.direction==="LONG"&&<TrendingUp className="inline h-3 w-3 mr-1 -mt-px"/>}
              {pred.direction==="SHORT"&&<TrendingDown className="inline h-3 w-3 mr-1 -mt-px"/>}
              {pred.direction==="FLAT"&&<Minus className="inline h-3 w-3 mr-1 -mt-px"/>}
              {pred.direction}
            </span>
          </Tip>
        </div>

        {/* Price + Score */}
        <div className="flex items-end justify-between">
          <div>
            <span className={cn("text-2xl font-bold font-mono tabular-nums tracking-tight transition-colors duration-800",flash?"text-blue-200":"text-zinc-50")}>
              {displayPrice>0?`₹${displayPrice.toFixed(2)}`:"--"}
            </span>
            {md&&<span className={cn("text-sm font-mono font-semibold ml-2",isUp?"text-emerald-400":"text-red-400")}>
              {isUp?<ArrowUpRight className="inline h-3.5 w-3.5 -mt-0.5"/>:<ArrowDownRight className="inline h-3.5 w-3.5 -mt-0.5"/>}
              {md.change_pct>=0?"+":""}{md.change_pct?.toFixed(2)}%
            </span>}
          </div>
          <Tip text="Score: -1 (strong sell) to +1 (strong buy)">
            <div className="text-right cursor-help">
              <span className={cn("text-xl font-bold font-mono tabular-nums",pred.score>0.05?"text-emerald-400":pred.score<-0.05?"text-red-400":"text-zinc-600")}>{pred.score>0?"+":""}{pred.score?.toFixed(2)}</span>
              <p className="text-[10px] text-zinc-500">{(pred.confidence*100)?.toFixed(0)}% conf</p>
            </div>
          </Tip>
        </div>

        {/* Score bar */}
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden relative">
          <div className="absolute top-0 bottom-0 left-1/2 w-px bg-zinc-700 z-10"/>
          <div className={cn("absolute top-0 bottom-0 rounded-full transition-all duration-500",pred.score>0?"bg-emerald-500":"bg-red-500")} style={{left:pred.score>=0?"50%":`${50-Math.abs(pred.score)*50}%`,width:`${Math.abs(pred.score)*50}%`}}/>
        </div>

        {/* Reasons */}
        <div className="space-y-0.5">
          {pred.reasons?.slice(0,3).map((r,i)=>(<p key={i} className="text-[11px] text-zinc-400 leading-snug"><span className={cn("inline-block h-1 w-1 rounded-full mr-1.5 align-middle",pred.direction==="LONG"?"bg-emerald-600":pred.direction==="SHORT"?"bg-red-600":"bg-zinc-700")}/>{r}</p>))}
        </div>

        {/* Key metrics */}
        {md&&(
          <div className="grid grid-cols-4 gap-px bg-zinc-800/30 rounded overflow-hidden">
            {([
              ["RSI",md.rsi_14?.toFixed(0),md.rsi_14<30?"text-emerald-400":md.rsi_14>70?"text-red-400":"text-zinc-300","RSI(14) — <30 oversold, >70 overbought"],
              ["Vol",md.volume_ratio?.toFixed(1)+"x",md.volume_ratio>1.5?"text-blue-400":"text-zinc-400","Volume vs 20-day avg"],
              ["1D",`${md.returns_1d>0?"+":""}${md.returns_1d?.toFixed(1)}%`,md.returns_1d>0?"text-emerald-400":"text-red-400","1-day return"],
              ["5D",`${md.returns_5d>0?"+":""}${md.returns_5d?.toFixed(1)}%`,md.returns_5d>0?"text-emerald-400":"text-red-400","5-day return"],
            ] as const).map(([l,v,c,t])=>(
              <Tip key={l} text={t as string}><div className="bg-[#0a0a0f] py-1.5 px-1 text-center cursor-help">
                <p className="text-[9px] text-zinc-600 uppercase">{l}</p>
                <p className={cn("text-xs font-mono font-semibold tabular-nums",c)}>{v}</p>
              </div></Tip>
            ))}
          </div>
        )}

        {/* Ensemble breakdown */}
        {pred.ensemble&&(
          <div className="flex gap-3 text-[10px]">
            <span className="text-zinc-600">ML:{pred.ensemble.ml_score>0?"+":""}{pred.ensemble.ml_score?.toFixed(2)}</span>
            <span className="text-zinc-600">Rules:{pred.ensemble.rules_score>0?"+":""}{pred.ensemble.rules_score?.toFixed(2)}</span>
            {lp&&<span className="text-zinc-700 ml-auto font-mono">{lp.fetch_ms?.toFixed(0)}ms</span>}
          </div>
        )}

        {/* S/R Levels (if computed) */}
        {pred.levels&&pred.levels.levels?.length>0&&(
          <div className="flex items-center gap-2 text-[10px] border-t border-zinc-800/30 pt-2">
            <span className="text-zinc-600">S/R:</span>
            {(()=>{
              const lvls=pred.levels.levels;
              const price=displayPrice;
              const supports=lvls.filter((l:any)=>l.price<price&&l.type!=="resistance").slice(-2);
              const resistances=lvls.filter((l:any)=>l.price>price&&l.type!=="support").slice(0,2);
              return(<>
                {supports.map((l:any)=>(<span key={l.name} className="text-emerald-500/60 font-mono">{l.name}={l.price}</span>))}
                <span className="text-zinc-700">|</span>
                {resistances.map((l:any)=>(<span key={l.name} className="text-red-500/60 font-mono">{l.name}={l.price}</span>))}
              </>);
            })()}
          </div>
        )}

        {/* Intraday decision (from engine) */}
        {mom&&(
          <div className="flex items-center gap-2 text-[10px] border-t border-zinc-800/30 pt-2">
            <Zap className="h-3 w-3 text-blue-500/70"/>
            <span className={cn("font-semibold",
              mom.action==="ENTER_LONG"||mom.action==="HOLD"&&pred.direction==="LONG"?"text-emerald-400":
              mom.action==="ENTER_SHORT"||mom.action==="HOLD"&&pred.direction==="SHORT"?"text-red-400":"text-zinc-500"
            )}>
              {mom.action}
            </span>
            {mom.reasons?.[0]&&<span className="text-zinc-600 truncate">{mom.reasons[0]}</span>}
          </div>
        )}
      </div>

      {/* Position stripe (bottom of card) */}
      {pos&&(
        <div className={cn("px-4 py-2 rounded-b-xl border-t flex items-center justify-between",
          pos.side==="LONG"?"bg-emerald-500/5 border-emerald-900/30":"bg-red-500/5 border-red-900/30")}>
          <span className="text-[10px] text-zinc-500">
            <span className={pos.side==="LONG"?"text-emerald-400":"text-red-400"}>{pos.side}</span>
            {" "}{pos.quantity}u @ ₹{pos.entry_price?.toFixed(2)}
          </span>
          <span className={cn("text-sm font-bold font-mono tabular-nums",pos.unrealized_pnl>=0?"text-emerald-400":"text-red-400")}>
            {pos.unrealized_pnl>=0?"+":""}₹{pos.unrealized_pnl?.toFixed(2)}
          </span>
        </div>
      )}
    </div>
  );
}

// ── Pipeline Activity ───────────────────────────────────────────

function ActivityLog(){
  const{activity,collectionCount,lastActivityAt}=useStore();useTick();
  if(!activity.length&&collectionCount===0)return(
    <div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] p-4 flex items-center gap-3 text-zinc-400 text-sm"><Loader2 className="h-4 w-4 animate-spin text-blue-500"/>Waiting for pipeline...</div>
  );
  return(
    <div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] overflow-hidden flex flex-col">
      <div className="px-4 py-2 border-b border-zinc-800/40 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2"><Radio className="h-3.5 w-3.5 text-blue-500"/><span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-[0.08em]">Pipeline Activity</span></div>
        <span className="text-[10px] text-zinc-600 font-mono">{activity.length} runs</span>
      </div>
      <div className="flex-1 overflow-y-auto max-h-[300px]">
        {[...activity].reverse().map((a,i)=>{
          const isOk=a.status==="ok";
          const time=a.timestamp?.split("T")[1]?.substring(0,8)??"";
          const nextRunAt=a.next_run_at??0;
          const liveRem=i===0&&nextRunAt>0?Math.max(0,Math.floor(nextRunAt-Date.now()/1000)):0;
          return(
            <Link key={a.run_id||a.cycle} href={`/run/${a.run_id||a.cycle}`} className={cn("block px-4 py-2 border-b border-zinc-800/20 hover:bg-zinc-800/20 transition-colors",i===0&&"bg-blue-500/[0.03]")}>
              <div className="flex items-center gap-2 mb-1">
                {isOk?<CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0"/>:<XCircle className="h-3.5 w-3.5 text-red-500 shrink-0"/>}
                <span className="font-mono text-xs text-zinc-300 tabular-nums">{time}</span>
                <span className="text-xs text-zinc-600">#{a.cycle}</span>
                <ExternalLink className="h-3 w-3 text-zinc-700 ml-auto shrink-0"/>
                {i===0&&liveRem>0&&<span className="text-xs text-amber-400 font-mono font-bold tabular-nums flex items-center gap-1"><Timer className="h-3 w-3"/>next {fmtDur(liveRem)}</span>}
              </div>
              {isOk&&a.predictions&&(
                <div className="flex flex-wrap gap-x-4 gap-y-0.5 ml-6 text-xs">
                  {Object.entries(a.predictions).map(([ticker,p]:[string,any])=>(
                    <div key={ticker} className="flex items-center gap-1.5">
                      <span className="text-zinc-500">{INST[ticker]?.label??ticker}</span>
                      <span className={cn("font-mono font-bold tabular-nums",p.direction==="LONG"?"text-emerald-400":p.direction==="SHORT"?"text-red-400":"text-zinc-600")}>{p.score>0?"+":""}{p.score?.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

// ── System Info ─────────────────────────────────────────────────

function SystemInfo(){
  const{status,predictions,collectionCount,trading}=useStore();
  const ms=status?.market;const sv=status?.server;
  if(!ms)return null;
  return(
    <div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] p-4 space-y-3">
      <p className="text-[11px] font-semibold text-zinc-400 uppercase tracking-[0.08em]">System</p>
      <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs">
        <div className="flex justify-between"><span className="text-zinc-500">Trading Day</span><span className={ms.is_trading_day?"text-emerald-400":"text-zinc-600"}>{ms.is_trading_day?"Yes":"No"}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">Can Trade</span><span className={ms.can_trade?"text-emerald-400":"text-zinc-600"}>{ms.can_trade?"Yes":"No"}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">Holiday</span><span className={ms.is_holiday?"text-amber-400":"text-zinc-600"}>{ms.is_holiday?"Yes":"No"}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">Instruments</span><span className="text-zinc-300">{predictions.length}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">Cycles</span><span className="text-zinc-300">{collectionCount}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">WS Clients</span><span className="text-zinc-300">{sv?.ws_clients??0}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">Redis</span><span className={sv?.db?.redis?"text-emerald-400":"text-red-400"}>{sv?.db?.redis?"OK":"Down"}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">TimescaleDB</span><span className={sv?.db?.timescaledb?"text-emerald-400":"text-red-400"}>{sv?.db?.timescaledb?"OK":"Down"}</span></div>
        {trading&&<>
          <div className="flex justify-between"><span className="text-zinc-500">Capital</span><span className="text-zinc-300">₹{trading.capital?.toFixed(0)}</span></div>
          <div className="flex justify-between"><span className="text-zinc-500">Broker</span><span className="text-zinc-300">{trading.broker}</span></div>
        </>}
      </div>
    </div>
  );
}

// ── Bottom Status Bar ───────────────────────────────────────────

function BottomBar(){
  useTick();
  const{trading,connected,collectionCount,updatedAt}=useStore();
  const updAgo=updatedAt?Math.floor(Date.now()/1000-updatedAt):null;
  return(
    <div className="fixed bottom-0 left-0 right-0 h-8 bg-[#0a0a0f]/95 border-t border-zinc-800/60 flex items-center px-5 gap-5 text-[10px] z-50 backdrop-blur-sm">
      <span className="text-zinc-600">Positions: <span className={cn("font-bold",trading&&trading.open_position_count>0?"text-blue-400":"text-zinc-500")}>{trading?.open_position_count??0}</span></span>
      {trading&&trading.total_unrealized_pnl!==0&&(
        <span className="text-zinc-600">Unrealized: <span className={cn("font-bold font-mono",trading.total_unrealized_pnl>=0?"text-emerald-400":"text-red-400")}>{trading.total_unrealized_pnl>=0?"+":""}₹{trading.total_unrealized_pnl?.toFixed(2)}</span></span>
      )}
      {trading&&trading.day_pnl!==0&&(
        <span className="text-zinc-600">Day P&L: <span className={cn("font-bold font-mono",trading.day_pnl>=0?"text-emerald-400":"text-red-400")}>{trading.day_pnl>=0?"+":""}₹{trading.day_pnl?.toFixed(2)}</span></span>
      )}
      <span className="text-zinc-600">Trades: <span className="text-zinc-400">{trading?.day_trades??0}</span></span>
      <span className="ml-auto text-zinc-700 font-mono">#{collectionCount}{updAgo!=null?` · ${updAgo}s ago`:""}</span>
      <span className={cn("font-semibold",connected?"text-emerald-500":"text-red-500")}>{connected?"●":"○"}</span>
    </div>
  );
}

// ── Main ────────────────────────────────────────────────────────

export default function Home(){
  useTick();
  const{connected,predictions,status,updateSeq,activity,trading}=useStore();
  const hasPreds=predictions.length>0;

  return(
    <div className="flex flex-col min-h-screen bg-[#08080c] text-zinc-100 font-sans pb-8">
      <Header/>
      <main className="flex-1 max-w-[1600px] mx-auto w-full px-5 py-3 flex flex-col gap-3">
        {/* Alerts */}
        {!connected&&!hasPreds&&(
          <div className="flex items-center gap-2 bg-amber-500/5 border border-amber-500/15 rounded-lg px-4 py-3 text-xs text-amber-400/80"><Loader2 className="h-4 w-4 animate-spin"/>Connecting... run <code className="font-mono bg-zinc-800 px-1.5 py-0.5 rounded">python -m trade_plus.api</code></div>
        )}
        {status?.market?.should_squareoff&&(
          <div className="flex items-center gap-2 bg-red-500/8 border border-red-500/20 rounded-lg px-4 py-2.5 text-xs text-red-400 font-bold animate-pulse"><AlertTriangle className="h-4 w-4"/>SQUARE OFF — Close MIS before 3:20 PM</div>
        )}

        {/* Trading summary bar */}
        {trading&&(
          <Link href="/trades" className={cn("flex items-center justify-between rounded-lg border px-4 py-2.5 transition-colors hover:brightness-110",
            !trading.day_trades?"border-zinc-800/50 bg-zinc-900/30":trading.day_pnl>=0?"border-emerald-900/30 bg-emerald-500/[0.03]":"border-red-900/30 bg-red-500/[0.03]")}>
            <div className="flex items-center gap-5 text-xs">
              <div className="flex items-center gap-1.5"><DollarSign className="h-3.5 w-3.5 text-zinc-500"/><span className="text-zinc-400 font-semibold">Paper Trading</span></div>
              <span className="text-zinc-500">₹{trading.capital?.toFixed(0)}</span>
              <span className={cn("font-mono font-bold",trading.day_pnl>=0?"text-emerald-400":"text-red-400")}>P&L: {trading.day_pnl>=0?"+":""}₹{trading.day_pnl?.toFixed(2)}</span>
              <span className="text-zinc-600">Trades: {trading.day_trades}</span>
              {trading.day_trades>0&&<span className="text-zinc-600">Win: {(trading.win_rate*100)?.toFixed(0)}%</span>}
              <span className={cn("text-zinc-600",trading.open_position_count>0&&"text-blue-400")}>Pos: {trading.open_position_count}</span>
            </div>
            <span className="text-[10px] text-zinc-600">View details →</span>
          </Link>
        )}

        {/* Market data bar */}
        <MarketBar/>

        {/* Instrument cards — 3 columns */}
        {hasPreds?(
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {predictions.map(p=><Card key={p.instrument} pred={p} seq={updateSeq}/>)}
          </div>
        ):(
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {[1,2,3].map(i=>(
              <div key={i} className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] p-4 space-y-3 animate-pulse">
                <div className="flex justify-between"><div className="h-4 w-24 bg-zinc-800 rounded"/><div className="h-5 w-14 bg-zinc-800 rounded"/></div>
                <div className="h-7 w-32 bg-zinc-800 rounded"/>
                <div className="h-1.5 w-full bg-zinc-800 rounded-full"/>
                <div className="space-y-1"><div className="h-3 w-full bg-zinc-800 rounded"/><div className="h-3 w-4/5 bg-zinc-800 rounded"/></div>
                <div className="grid grid-cols-4 gap-1">{[1,2,3,4].map(j=>(<div key={j} className="h-10 bg-zinc-800/50 rounded"/>))}</div>
              </div>
            ))}
          </div>
        )}

        {/* Bottom: Activity + System */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 flex-1 min-h-0">
          <div className="lg:col-span-2"><ActivityLog/></div>
          <SystemInfo/>
        </div>
      </main>

      <BottomBar/>

      <footer className="border-t border-zinc-800/30 py-2.5 text-center text-[10px] text-zinc-700 mb-8">
        Trade-Plus v0.2 | Level-based intraday trading | Not financial advice
      </footer>
    </div>
  );
}
