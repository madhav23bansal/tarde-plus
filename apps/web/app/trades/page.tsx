"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useStore, type TradingStatus } from "@/lib/ws";
import { cn } from "@/lib/cn";
import {
  ArrowLeft, Zap, Activity, TrendingUp, TrendingDown,
  ChevronDown, DollarSign,
} from "lucide-react";

function useTick(ms=1000){const[,s]=useState(0);useEffect(()=>{const i=setInterval(()=>s(t=>t+1),ms);return()=>clearInterval(i)},[ms])}
const N:Record<string,string>={NIFTYBEES:"Nifty",BANKBEES:"Bank",SETFNIF50:"SBI"};

export default function TradesPage(){
  useTick();
  const{trading,connected}=useStore();
  const[rest,setRest]=useState<TradingStatus|null>(null);
  useEffect(()=>{
    const f=()=>fetch("/api/trading").then(r=>r.json()).then(d=>{if(!d.error)setRest(d)}).catch(()=>{});
    f();const i=setInterval(f,3000);return()=>clearInterval(i);
  },[]);
  const t=trading??rest;

  if(!t)return(
    <div className="min-h-screen bg-[#08080c] text-zinc-100 flex items-center justify-center">
      <Activity className="h-6 w-6 animate-pulse text-zinc-600"/>
    </div>
  );

  const returnPct=((t.capital/t.starting_capital-1)*100);

  return(
    <div className="min-h-screen bg-[#08080c] text-zinc-100 font-sans">
      {/* Header */}
      <div className="bg-[#0a0a0f] border-b border-zinc-800/60 px-4 py-2 flex items-center gap-3 text-[11px] sticky top-0 z-50">
        <Link href="/" className="text-zinc-400 hover:text-zinc-200 transition-colors"><ArrowLeft className="h-4 w-4"/></Link>
        <Zap className="h-4 w-4 text-blue-500"/>
        <span className="font-bold text-sm text-zinc-100">Trades</span>
        <span className={cn("font-mono font-bold text-base ml-1",t.day_pnl>=0?"text-emerald-400":"text-red-400")}>{t.day_pnl>=0?"+":""}₹{t.day_pnl?.toFixed(2)}</span>
        <span className="ml-auto text-zinc-500 font-mono">₹{t.capital?.toFixed(0)} · {t.broker}</span>
      </div>

      <div className="max-w-[1440px] mx-auto px-4 py-4 space-y-4">

        {/* ━━━ P&L + STATS — one dense row ━━━ */}
        <div className="grid grid-cols-[1fr_auto] gap-4">
          {/* P&L number — large */}
          <div className={cn("rounded-xl p-5 relative overflow-hidden",
            t.day_pnl>=0?"bg-gradient-to-r from-emerald-500/[0.05] to-transparent border border-emerald-500/10":
            "bg-gradient-to-r from-red-500/[0.05] to-transparent border border-red-500/10")}>
            <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1">Today's Net P&L</p>
            <p className={cn("text-5xl font-bold font-mono tabular-nums leading-none tracking-tight",
              t.day_pnl>=0?"text-emerald-400":"text-red-400")}>
              {t.day_pnl>=0?"+":""}₹{t.day_pnl?.toFixed(2)}
            </p>
            <div className="flex gap-4 mt-2 text-xs text-zinc-500">
              <span>Gross ₹{(t.day_pnl+t.day_charges)?.toFixed(2)}</span>
              <span>Charges ₹{t.day_charges?.toFixed(2)}</span>
            </div>
          </div>

          {/* Stats grid */}
          <div className="grid grid-cols-2 gap-2 min-w-[200px]">
            <StatBox label="Capital" value={`₹${t.capital?.toFixed(0)}`} sub={`${returnPct>=0?"+":""}${returnPct.toFixed(2)}%`} subColor={returnPct>=0?"text-emerald-400":"text-red-400"}/>
            <StatBox label="Trades" value={t.day_trades} sub={`${t.day_wins}W ${t.day_losses}L`}/>
            <StatBox label="Win Rate" value={`${(t.win_rate*100).toFixed(0)}%`} sub={t.win_rate>0.5?"Good":t.win_rate>0?"Weak":"—"} subColor={t.win_rate>0.5?"text-emerald-400":t.win_rate>0?"text-amber-400":undefined}/>
            <StatBox label="Drawdown" value={`${(t.max_drawdown*100).toFixed(1)}%`} sub={`${t.leverage}x leverage`}/>
          </div>
        </div>

        {/* ━━━ POSITIONS ━━━ */}
        {Object.keys(t.positions).length>0&&(
          <div className="bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
            <div className="px-3 py-2 border-b border-zinc-800/20 flex items-center justify-between text-[10px]">
              <span className="text-zinc-500 font-semibold uppercase tracking-wider">Positions</span>
              <span className={cn("font-mono font-bold",t.total_unrealized_pnl>=0?"text-emerald-400":"text-red-400")}>
                {t.total_unrealized_pnl>=0?"+":""}₹{t.total_unrealized_pnl?.toFixed(2)}
              </span>
            </div>
            {Object.entries(t.positions).map(([inst,pos]:[string,any])=>(
              <div key={inst} className="px-3 py-2 flex items-center gap-3 text-xs border-b border-zinc-800/10 last:border-0">
                <span className="font-medium text-zinc-200 w-16">{N[inst]??inst}</span>
                <Side s={pos.side}/>
                <span className="font-mono text-zinc-500">{pos.quantity}u</span>
                <span className="font-mono text-zinc-500">₹{pos.entry_price?.toFixed(2)}</span>
                <span className="text-zinc-700">→</span>
                <span className="font-mono text-zinc-300">₹{pos.current_price?.toFixed(2)}</span>
                <span className={cn("font-mono font-bold ml-auto tabular-nums",pos.unrealized_pnl>=0?"text-emerald-400":"text-red-400")}>
                  {pos.unrealized_pnl>=0?"+":""}₹{pos.unrealized_pnl?.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* ━━━ TRADE HISTORY ━━━ */}
        <div className="bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
          <div className="px-3 py-2 border-b border-zinc-800/20 text-[10px] text-zinc-500 font-semibold uppercase tracking-wider">
            Trade History <span className="text-zinc-600 font-mono font-normal ml-1">{t.closed_trades?.length??0}</span>
          </div>
          {!t.closed_trades?.length?(
            <div className="p-6 text-center text-xs text-zinc-600">No completed trades</div>
          ):(
            <div className="divide-y divide-zinc-800/10">
              {[...t.closed_trades].reverse().map((trade:any,i:number)=><TradeRow key={i} trade={trade}/>)}
            </div>
          )}
        </div>

        {/* ━━━ ORDERS ━━━ */}
        <div className="bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
          <div className="px-3 py-2 border-b border-zinc-800/20 text-[10px] text-zinc-500 font-semibold uppercase tracking-wider">
            Orders <span className="text-zinc-600 font-mono font-normal ml-1">{t.recent_orders?.length??0}</span>
          </div>
          {!t.recent_orders?.length?(
            <div className="p-6 text-center text-xs text-zinc-600">No orders</div>
          ):(
            <div className="divide-y divide-zinc-800/10">
              {[...t.recent_orders].reverse().map((o:any,i:number)=>{
                const time=o.placed_at?new Date(o.placed_at*1000).toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour12:false}):"";
                return(
                  <div key={i} className="px-3 py-2 flex items-center gap-3 text-xs">
                    <span className="font-mono text-zinc-500 w-16">{time}</span>
                    <span className="text-zinc-300 w-12">{N[o.instrument]??o.instrument}</span>
                    <Side s={o.side}/>
                    <span className="font-mono text-zinc-500">{o.quantity}u</span>
                    <span className="font-mono text-zinc-500">₹{o.signal_price?.toFixed(2)}</span>
                    <span className="text-zinc-700">→</span>
                    <span className="font-mono text-zinc-300">₹{o.fill_price?.toFixed(2)}</span>
                    <span className="font-mono text-zinc-600">-₹{o.charges?.toFixed(2)}</span>
                    {o.pnl?<span className={cn("font-mono font-bold ml-auto",o.pnl>=0?"text-emerald-400":"text-red-400")}>{o.pnl>=0?"+":""}₹{o.pnl?.toFixed(2)}</span>:null}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatBox({label,value,sub,subColor}:{label:string;value:any;sub?:string;subColor?:string}){
  return(
    <div className="bg-[#0c0c11] border border-zinc-800/30 rounded-lg px-3 py-2">
      <p className="text-[8px] text-zinc-600 uppercase tracking-wider">{label}</p>
      <p className="text-base font-bold font-mono tabular-nums text-zinc-200">{value}</p>
      {sub&&<p className={cn("text-[10px] font-mono",subColor??"text-zinc-500")}>{sub}</p>}
    </div>
  );
}

function Side({s}:{s:string}){
  return<span className={cn("text-[9px] font-bold px-1 py-px rounded",
    s==="BUY"||s==="LONG"?"text-emerald-400 bg-emerald-500/10":"text-red-400 bg-red-500/10")}>{s}</span>;
}

function TradeRow({trade}:{trade:any}){
  const[open,setOpen]=useState(false);
  const time=trade.exit_time?new Date(trade.exit_time*1000).toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour12:false}):"";
  const hold=trade.exit_time&&trade.entry_time?((trade.exit_time-trade.entry_time)/60).toFixed(0):"?";
  return(
    <div className={cn("cursor-pointer transition-colors",trade.net_pnl>=0?"hover:bg-emerald-500/[0.02]":"hover:bg-red-500/[0.02]")} onClick={()=>setOpen(o=>!o)}>
      <div className="px-3 py-2 flex items-center gap-3 text-xs">
        <span className="font-mono text-zinc-500 w-16">{time}</span>
        <span className="text-zinc-300 w-12">{N[trade.instrument]??trade.instrument}</span>
        <Side s={trade.side}/>
        <span className="font-mono text-zinc-500">₹{trade.entry_price?.toFixed(2)}→₹{trade.exit_price?.toFixed(2)}</span>
        <span className="text-zinc-600">{hold}m</span>
        <span className={cn("font-bold font-mono ml-auto tabular-nums",trade.net_pnl>=0?"text-emerald-400":"text-red-400")}>{trade.net_pnl>=0?"+":""}₹{trade.net_pnl?.toFixed(2)}</span>
        <ChevronDown className={cn("h-3 w-3 text-zinc-700 transition-transform shrink-0",open&&"rotate-180")}/>
      </div>
      {open&&(
        <div className="px-3 pb-2 text-[10px] text-zinc-500 ml-16">
          Gross ₹{trade.gross_pnl?.toFixed(2)} · Charges ₹{trade.charges?.toFixed(2)} · {trade.reason}
        </div>
      )}
    </div>
  );
}
