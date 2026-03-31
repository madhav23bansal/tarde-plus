"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useStore, type TradingStatus } from "@/lib/ws";
import { cn } from "@/lib/cn";
import {
  ArrowLeft, Zap, Activity, TrendingUp, TrendingDown,
  ChevronDown, DollarSign, Brain, Layers, Timer, Shield,
  Target, BarChart3, ArrowUpRight, ArrowDownRight,
} from "lucide-react";

function useTick(ms=1000){const[,s]=useState(0);useEffect(()=>{const i=setInterval(()=>s(t=>t+1),ms);return()=>clearInterval(i)},[ms])}
const N:Record<string,string>={NIFTYBEES:"Nifty",BANKBEES:"Bank",SETFNIF50:"SBI"};

function useMomentum(){
  const[data,setData]=useState<any>(null);
  useEffect(()=>{
    const f=()=>fetch("/api/trading/momentum").then(r=>r.json()).then(d=>{if(!d.error)setData(d)}).catch(()=>{});
    f();const i=setInterval(f,10000);return()=>clearInterval(i);
  },[]);
  const wsMom=useStore(s=>s.momentum);
  return{momentum:wsMom??data?.momentum,fastLoopCount:data?.fast_loop_count??0,fastInterval:data?.fast_loop_interval??30};
}

function useAccuracy(){
  const[data,setData]=useState<any>(null);
  useEffect(()=>{
    fetch("/api/accuracy").then(r=>r.json()).then(d=>setData(d)).catch(()=>{});
  },[]);
  return data;
}

function useDayResult(){
  const[data,setData]=useState<any>(null);
  useEffect(()=>{
    const f=()=>fetch("/api/trading/day-result").then(r=>r.json()).then(d=>{if(!d.error)setData(d)}).catch(()=>{});
    f();const i=setInterval(f,5000);return()=>clearInterval(i);
  },[]);
  return data;
}

export default function TradesPage(){
  useTick();
  const{trading,connected,predictions}=useStore();
  const[rest,setRest]=useState<TradingStatus|null>(null);
  useEffect(()=>{
    const f=()=>fetch("/api/trading").then(r=>r.json()).then(d=>{if(!d.error)setRest(d)}).catch(()=>{});
    f();const i=setInterval(f,3000);return()=>clearInterval(i);
  },[]);
  const t=trading??rest;
  const{momentum,fastLoopCount,fastInterval}=useMomentum();
  const accuracy=useAccuracy();
  const dayResult=useDayResult();

  if(!t)return(
    <div className="min-h-screen bg-[#08080c] text-zinc-100 flex items-center justify-center">
      <Activity className="h-6 w-6 animate-pulse text-zinc-600"/>
    </div>
  );

  const returnPct=((t.capital/t.starting_capital-1)*100);
  const netEquity=t.capital+(t.total_unrealized_pnl??0);

  return(
    <div className="min-h-screen bg-[#08080c] text-zinc-100 font-sans">
      {/* Header */}
      <div className="bg-[#0a0a0f] border-b border-zinc-800/60 px-4 py-2 flex items-center gap-3 text-[11px] sticky top-0 z-50">
        <Link href="/" className="text-zinc-400 hover:text-zinc-200 transition-colors"><ArrowLeft className="h-4 w-4"/></Link>
        <Zap className="h-4 w-4 text-blue-500"/>
        <span className="font-bold text-sm text-zinc-100">Trading</span>
        <span className={cn("font-mono font-bold text-base ml-1",t.day_pnl>=0?"text-emerald-400":"text-red-400")}>{t.day_pnl>=0?"+":""}₹{t.day_pnl?.toFixed(2)}</span>
        <span className="ml-auto flex items-center gap-3">
          <span className="text-zinc-600">{t.day_trades} trades</span>
          <span className="text-zinc-600">{t.open_position_count} open</span>
          <span className="text-zinc-500 font-mono">₹{t.capital?.toFixed(0)} · {t.broker}</span>
          <span className={cn("text-sm",connected?"text-emerald-500":"text-red-500")}>●</span>
        </span>
      </div>

      <div className="max-w-[1440px] mx-auto px-4 py-3 space-y-3">

        {/* ━━━ ROW 1: P&L Hero + Stats Grid + Day Result ━━━ */}
        <div className="grid grid-cols-12 gap-3">
          {/* P&L Hero */}
          <div className={cn("col-span-5 rounded-xl p-4 relative overflow-hidden",
            t.day_pnl>=0?"bg-gradient-to-br from-emerald-500/[0.06] to-transparent border border-emerald-500/10":
            "bg-gradient-to-br from-red-500/[0.06] to-transparent border border-red-500/10")}>
            <p className="text-[9px] text-zinc-500 uppercase tracking-widest mb-1">Today's Net P&L</p>
            <p className={cn("text-4xl font-bold font-mono tabular-nums leading-none tracking-tight",
              t.day_pnl>=0?"text-emerald-400":"text-red-400")}>
              {t.day_pnl>=0?"+":""}₹{t.day_pnl?.toFixed(2)}
            </p>
            <div className="flex gap-3 mt-2 text-[10px] text-zinc-500">
              <span>Gross ₹{(t.day_pnl+t.day_charges)?.toFixed(2)}</span>
              <span>Charges ₹{t.day_charges?.toFixed(2)}</span>
              <span>Return {returnPct>=0?"+":""}{returnPct.toFixed(2)}%</span>
            </div>
            {dayResult&&(
              <div className="flex gap-3 mt-1 text-[10px] text-zinc-600">
                <span>Start ₹{dayResult.starting_capital?.toFixed(0)}</span>
                <span>End ₹{dayResult.ending_capital?.toFixed(0)}</span>
              </div>
            )}
          </div>

          {/* Stats Grid — 3x2 */}
          <div className="col-span-4 grid grid-cols-3 grid-rows-2 gap-2">
            <Stat label="Capital" value={`₹${t.capital?.toFixed(0)}`} sub={`${returnPct>=0?"+":""}${returnPct.toFixed(2)}%`} subC={returnPct>=0?"text-emerald-400":"text-red-400"}/>
            <Stat label="Buying Power" value={`₹${t.buying_power?.toFixed(0)}`} sub={`${t.leverage}x leverage`}/>
            <Stat label="Net Equity" value={`₹${netEquity.toFixed(0)}`} sub={netEquity>=t.starting_capital?"Above start":"Below start"} subC={netEquity>=t.starting_capital?"text-emerald-400/60":"text-red-400/60"}/>
            <Stat label="Trades" value={t.day_trades} sub={`${t.day_wins}W ${t.day_losses}L`}/>
            <Stat label="Win Rate" value={t.day_trades>0?`${(t.win_rate*100).toFixed(0)}%`:"—"} sub={t.win_rate>0.5?"Good":t.win_rate>0?"Weak":"—"} subC={t.win_rate>0.5?"text-emerald-400":t.win_rate>0?"text-amber-400":undefined}/>
            <Stat label="Drawdown" value={`${(t.max_drawdown*100).toFixed(1)}%`} sub={t.max_drawdown>0.02?"Caution":"Safe"} subC={t.max_drawdown>0.02?"text-amber-400":"text-emerald-400/60"}/>
          </div>

          {/* Engine Status */}
          <div className="col-span-3 bg-[#0c0c11] border border-zinc-800/30 rounded-xl p-3 text-[11px] space-y-1">
            <div className="flex items-center gap-1.5 text-[10px] text-zinc-500 font-semibold uppercase tracking-wider mb-1.5">
              <Brain className="h-3 w-3 text-blue-500/70"/>Engine
            </div>
            {momentum?<>
              <ER l="Mode" v={momentum.mode}/>
              <ER l="Window" v={momentum.time_window?.toUpperCase()??"—"} c={momentum.time_window==="prime"?"text-emerald-400":momentum.time_window==="orb"?"text-amber-400":undefined}/>
              <ER l="Levels" v={momentum.levels_computed?"Computed":"Pending"} c={momentum.levels_computed?"text-emerald-400":"text-zinc-600"}/>
              <ER l="ORB" v={momentum.orb_set?"Set":"Pending"} c={momentum.orb_set?"text-emerald-400":"text-zinc-600"}/>
              <ER l="Fast Loop" v={`${fastLoopCount} · ${fastInterval}s`}/>
            </>:<span className="text-zinc-600">Loading...</span>}
          </div>
        </div>

        {/* ━━━ ROW 2: Positions + OI + Levels ━━━ */}
        <div className="grid grid-cols-12 gap-3">
          {/* Positions */}
          <div className="col-span-5 bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
            <div className="px-3 py-2 border-b border-zinc-800/20 flex items-center justify-between text-[10px]">
              <span className="text-zinc-500 font-semibold uppercase tracking-wider">Positions</span>
              <span className={cn("font-mono font-bold",t.total_unrealized_pnl>=0?"text-emerald-400":"text-red-400")}>
                {t.total_unrealized_pnl>=0?"+":""}₹{t.total_unrealized_pnl?.toFixed(2)} unrealized
              </span>
            </div>
            {Object.keys(t.positions).length===0?(
              <div className="p-4 text-center text-xs text-zinc-600">No open positions</div>
            ):Object.entries(t.positions).map(([inst,pos]:[string,any])=>(
              <div key={inst} className="px-3 py-2 flex items-center gap-2 text-xs border-b border-zinc-800/10 last:border-0">
                <span className="font-medium text-zinc-200 w-14">{N[inst]??inst}</span>
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

          {/* OI Data */}
          <div className="col-span-4 bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
            <div className="px-3 py-2 border-b border-zinc-800/20 flex items-center gap-2 text-[10px]">
              <Layers className="h-3 w-3 text-blue-500/60"/>
              <span className="text-zinc-500 font-semibold uppercase tracking-wider">Option Chain OI</span>
            </div>
            {momentum?.oi&&Object.keys(momentum.oi).length>0?(
              <div className="divide-y divide-zinc-800/10">
                {Object.entries(momentum.oi).map(([idx,oi]:[string,any])=>(
                  <div key={idx} className="px-3 py-2 space-y-1">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-semibold text-zinc-300">{idx}</span>
                      <span className={cn("text-[9px] font-bold px-1 py-px rounded",
                        oi.oi_buildup==="bullish"?"text-emerald-400 bg-emerald-500/10":
                        oi.oi_buildup==="bearish"?"text-red-400 bg-red-500/10":"text-zinc-500 bg-zinc-800")}>{oi.oi_buildup??'—'}</span>
                    </div>
                    <div className="grid grid-cols-4 gap-1">
                      <MiniStat l="Resistance" v={oi.oi_resistance} c="text-red-400/70"/>
                      <MiniStat l="Support" v={oi.oi_support} c="text-emerald-400/70"/>
                      <MiniStat l="Max Pain" v={oi.max_pain}/>
                      <MiniStat l="PCR" v={oi.pcr?.toFixed(2)} c={oi.pcr>1.2?"text-emerald-400/70":oi.pcr<0.8?"text-red-400/70":undefined}/>
                    </div>
                  </div>
                ))}
              </div>
            ):(
              <div className="p-4 text-center text-xs text-zinc-600">OI data loads at market open</div>
            )}
          </div>

          {/* Levels */}
          <div className="col-span-3 bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
            <div className="px-3 py-2 border-b border-zinc-800/20 text-[10px] text-zinc-500 font-semibold uppercase tracking-wider">
              S/R Levels
            </div>
            {momentum?.levels&&Object.keys(momentum.levels).length>0?(
              <div className="divide-y divide-zinc-800/10 max-h-[200px] overflow-y-auto">
                {Object.entries(momentum.levels).map(([ticker,dl]:[string,any])=>(
                  <div key={ticker} className="px-3 py-2">
                    <p className="text-[9px] text-zinc-500 font-semibold mb-1">{N[ticker]??ticker}</p>
                    <div className="flex flex-wrap gap-1">
                      {dl.levels?.sort((a:any,b:any)=>a.price-b.price).map((lv:any)=>(
                        <span key={lv.name} className={cn("text-[9px] font-mono px-1 py-px rounded",
                          lv.type==="support"?"text-emerald-400/60 bg-emerald-500/5":
                          lv.type==="resistance"?"text-red-400/60 bg-red-500/5":"text-zinc-500 bg-zinc-800/50")}>
                          {lv.name}:{lv.price}
                        </span>
                      ))}
                      {(!dl.levels||dl.levels.length===0)&&<span className="text-[9px] text-zinc-700">At market open</span>}
                    </div>
                    {dl.cpr&&<p className="text-[9px] text-zinc-600 mt-0.5">CPR: {dl.cpr.tc}–{dl.cpr.bc} ({dl.cpr.day_type})</p>}
                    {dl.orb?.set&&<p className="text-[9px] text-zinc-600">ORB: {dl.orb.high}–{dl.orb.low}</p>}
                  </div>
                ))}
              </div>
            ):(
              <div className="p-4 text-center text-xs text-zinc-600">Levels compute at 8:45 AM</div>
            )}
          </div>
        </div>

        {/* ━━━ ROW 3: Decisions + Predictions ━━━ */}
        {(momentum?.decisions&&Object.keys(momentum.decisions).length>0||predictions.length>0)&&(
          <div className="grid grid-cols-12 gap-3">
            {/* Engine Decisions */}
            <div className="col-span-6 bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
              <div className="px-3 py-2 border-b border-zinc-800/20 flex items-center gap-2 text-[10px]">
                <Target className="h-3 w-3 text-blue-500/60"/>
                <span className="text-zinc-500 font-semibold uppercase tracking-wider">Engine Decisions</span>
              </div>
              {momentum?.decisions&&Object.keys(momentum.decisions).length>0?(
                <div className="divide-y divide-zinc-800/10">
                  {Object.entries(momentum.decisions).map(([ticker,d]:[string,any])=>(
                    <div key={ticker} className="px-3 py-2 space-y-1">
                      <div className="flex items-center gap-2 text-xs">
                        <span className="text-zinc-300 font-medium w-14">{N[ticker]??ticker}</span>
                        <span className={cn("text-[9px] font-bold px-1.5 py-px rounded",
                          d.action?.includes("ENTER")?"text-blue-400 bg-blue-500/10":
                          d.action==="EXIT"?"text-amber-400 bg-amber-500/10":
                          d.action==="HOLD"?"text-zinc-300 bg-zinc-700":"text-zinc-600 bg-zinc-800/50")}>{d.action}</span>
                        {d.level&&<span className="text-[10px] font-mono text-zinc-500">@{d.level.name}={d.level.price}</span>}
                        <span className="text-[10px] font-mono text-zinc-600 ml-auto">{d.confidence?.toFixed(0)}% conf</span>
                      </div>
                      {d.reasons?.length>0&&(
                        <div className="text-[10px] text-zinc-600 leading-snug">
                          {d.reasons.map((r:string,i:number)=><p key={i}>{r}</p>)}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ):(
                <div className="p-4 text-center text-xs text-zinc-600">No active decisions</div>
              )}
            </div>

            {/* Predictions */}
            <div className="col-span-6 bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
              <div className="px-3 py-2 border-b border-zinc-800/20 text-[10px] text-zinc-500 font-semibold uppercase tracking-wider">
                Bias Predictions
              </div>
              {predictions.length>0?(
                <div className="divide-y divide-zinc-800/10">
                  {predictions.map(p=>{
                    const md=p.market_data;
                    return(
                      <div key={p.instrument} className="px-3 py-2">
                        <div className="flex items-center gap-2 text-xs">
                          <span className="text-zinc-300 font-medium w-14">{N[p.instrument]??p.instrument}</span>
                          <span className={cn("text-[9px] font-bold px-1.5 py-px rounded",
                            p.direction==="LONG"?"text-emerald-400 bg-emerald-500/10":
                            p.direction==="SHORT"?"text-red-400 bg-red-500/10":"text-zinc-500 bg-zinc-800")}>{p.direction}</span>
                          <span className={cn("font-mono font-bold text-sm",
                            p.score>0?"text-emerald-400":p.score<0?"text-red-400":"text-zinc-500")}>{p.score>0?"+":""}{p.score?.toFixed(2)}</span>
                          <span className="text-zinc-600 text-[10px]">{(p.confidence*100).toFixed(0)}% · {p.method}</span>
                        </div>
                        <div className="flex gap-3 mt-1 text-[10px] text-zinc-600">
                          {p.ensemble&&<>
                            <span>ML: <span className={cn("font-mono",p.ensemble.ml_score>0?"text-emerald-400/60":"text-red-400/60")}>{p.ensemble.ml_score>0?"+":""}{p.ensemble.ml_score?.toFixed(2)}</span></span>
                            <span>Rules: <span className={cn("font-mono",p.ensemble.rules_score>0?"text-emerald-400/60":"text-red-400/60")}>{p.ensemble.rules_score>0?"+":""}{p.ensemble.rules_score?.toFixed(2)}</span></span>
                          </>}
                          {md&&<>
                            <span>RSI:{md.rsi_14?.toFixed(0)}</span>
                            <span>Vol:{md.volume_ratio?.toFixed(1)}x</span>
                            <span>1D:{md.returns_1d>0?"+":""}{md.returns_1d?.toFixed(1)}%</span>
                          </>}
                        </div>
                        {p.reasons?.length>0&&<p className="text-[10px] text-zinc-600 mt-0.5">{p.reasons.slice(0,2).join(" | ")}</p>}
                      </div>
                    );
                  })}
                </div>
              ):(
                <div className="p-4 text-center text-xs text-zinc-600">No predictions yet</div>
              )}
            </div>
          </div>
        )}

        {/* ━━━ TRADE HISTORY ━━━ */}
        <div className="bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
          <div className="px-3 py-2 border-b border-zinc-800/20 flex items-center justify-between text-[10px]">
            <span className="text-zinc-500 font-semibold uppercase tracking-wider">
              Trade History <span className="text-zinc-600 font-mono font-normal ml-1">{t.closed_trades?.length??0}</span>
            </span>
            {t.closed_trades?.length>0&&(()=>{
              const totalPnl=t.closed_trades.reduce((s:number,tr:any)=>s+(tr.net_pnl??0),0);
              return<span className={cn("font-mono font-bold",totalPnl>=0?"text-emerald-400":"text-red-400")}>{totalPnl>=0?"+":""}₹{totalPnl.toFixed(2)} total</span>;
            })()}
          </div>
          {!t.closed_trades?.length?(
            <div className="p-6 text-center text-xs text-zinc-600">No completed trades yet</div>
          ):(
            <div className="divide-y divide-zinc-800/10">
              {/* Header row */}
              <div className="px-3 py-1.5 flex items-center gap-3 text-[9px] text-zinc-600 uppercase tracking-wider">
                <span className="w-16">Time</span>
                <span className="w-12">Inst</span>
                <span className="w-10">Side</span>
                <span className="w-32">Entry → Exit</span>
                <span className="w-10">Hold</span>
                <span className="w-16">Gross</span>
                <span className="w-16">Charges</span>
                <span className="w-20 text-right">Net P&L</span>
                <span className="w-4"/>
              </div>
              {[...t.closed_trades].reverse().map((trade:any,i:number)=><TradeRow key={i} trade={trade}/>)}
            </div>
          )}
        </div>

        {/* ━━━ ORDERS ━━━ */}
        <div className="bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
          <div className="px-3 py-2 border-b border-zinc-800/20 flex items-center justify-between text-[10px]">
            <span className="text-zinc-500 font-semibold uppercase tracking-wider">
              Orders <span className="text-zinc-600 font-mono font-normal ml-1">{t.recent_orders?.length??0}</span>
            </span>
            {t.recent_orders?.length>0&&(()=>{
              const totalCharges=t.recent_orders.reduce((s:number,o:any)=>s+(o.charges??0),0);
              return<span className="text-zinc-600 font-mono">₹{totalCharges.toFixed(2)} charges</span>;
            })()}
          </div>
          {!t.recent_orders?.length?(
            <div className="p-6 text-center text-xs text-zinc-600">No orders today</div>
          ):(
            <div className="divide-y divide-zinc-800/10">
              <div className="px-3 py-1.5 flex items-center gap-3 text-[9px] text-zinc-600 uppercase tracking-wider">
                <span className="w-16">Time</span>
                <span className="w-12">Inst</span>
                <span className="w-10">Side</span>
                <span className="w-10">Qty</span>
                <span className="w-32">Signal → Fill</span>
                <span className="w-16">Charges</span>
                <span className="w-20 text-right">P&L</span>
              </div>
              {[...t.recent_orders].reverse().map((o:any,i:number)=>{
                const time=o.placed_at?new Date(o.placed_at*1000).toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour12:false}):"";
                return(
                  <div key={i} className="px-3 py-1.5 flex items-center gap-3 text-xs">
                    <span className="font-mono text-zinc-500 w-16">{time}</span>
                    <span className="text-zinc-300 w-12">{N[o.instrument]??o.instrument}</span>
                    <Side s={o.side}/>
                    <span className="font-mono text-zinc-500 w-10">{o.quantity}u</span>
                    <span className="font-mono text-zinc-500 w-32">₹{o.signal_price?.toFixed(2)} → ₹{o.fill_price?.toFixed(2)}</span>
                    <span className="font-mono text-zinc-600 w-16">-₹{o.charges?.toFixed(2)}</span>
                    {o.pnl!=null?<span className={cn("font-mono font-bold w-20 text-right",o.pnl>=0?"text-emerald-400":"text-red-400")}>{o.pnl>=0?"+":""}₹{o.pnl?.toFixed(2)}</span>:<span className="w-20"/>}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ━━━ ACCURACY ━━━ */}
        {accuracy&&Object.keys(accuracy).length>0&&(
          <div className="bg-[#0c0c11] border border-zinc-800/30 rounded-xl overflow-hidden">
            <div className="px-3 py-2 border-b border-zinc-800/20 flex items-center gap-2 text-[10px]">
              <Shield className="h-3 w-3 text-blue-500/60"/>
              <span className="text-zinc-500 font-semibold uppercase tracking-wider">Accuracy Tracker</span>
            </div>
            <div className="grid grid-cols-3 divide-x divide-zinc-800/10">
              {Object.entries(accuracy).map(([inst,acc]:[string,any])=>(
                <div key={inst} className="px-3 py-2">
                  <p className="text-[11px] font-medium text-zinc-300 mb-1">{N[inst]??inst}</p>
                  {acc.overall&&Object.keys(acc.overall).length>0?(
                    <div className="space-y-0.5 text-[10px]">
                      {acc.overall.total_trades!=null&&<MR l="Total Trades" v={acc.overall.total_trades}/>}
                      {acc.overall.win_rate!=null&&<MR l="Win Rate" v={`${(acc.overall.win_rate*100).toFixed(0)}%`}/>}
                      {acc.overall.avg_rr!=null&&<MR l="Avg R:R" v={acc.overall.avg_rr?.toFixed(2)}/>}
                      {acc.overall.expectancy!=null&&<MR l="Expectancy" v={acc.overall.expectancy?.toFixed(2)}/>}
                      {acc.overall.sharpe!=null&&<MR l="Sharpe" v={acc.overall.sharpe?.toFixed(2)}/>}
                    </div>
                  ):(
                    <p className="text-[10px] text-zinc-600">No trades recorded</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

function Stat({label,value,sub,subC}:{label:string;value:any;sub?:string;subC?:string}){
  return(
    <div className="bg-[#0c0c11] border border-zinc-800/30 rounded-lg px-3 py-2">
      <p className="text-[8px] text-zinc-600 uppercase tracking-wider leading-none">{label}</p>
      <p className="text-sm font-bold font-mono tabular-nums text-zinc-200 leading-tight">{value}</p>
      {sub&&<p className={cn("text-[10px] font-mono leading-none",subC??"text-zinc-500")}>{sub}</p>}
    </div>
  );
}

function ER({l,v,c}:{l:string;v:string;c?:string}){
  return<div className="flex justify-between text-[11px]"><span className="text-zinc-600">{l}</span><span className={c??"text-zinc-300"}>{v}</span></div>;
}

function MR({l,v}:{l:string;v:any}){
  return<div className="flex justify-between"><span className="text-zinc-600">{l}</span><span className="text-zinc-300 font-mono">{v}</span></div>;
}

function MiniStat({l,v,c}:{l:string;v:any;c?:string}){
  return(
    <div className="text-center">
      <p className="text-[8px] text-zinc-600 uppercase leading-none">{l}</p>
      <p className={cn("text-[11px] font-mono font-semibold tabular-nums leading-tight",c??"text-zinc-300")}>{v??'—'}</p>
    </div>
  );
}

function Side({s}:{s:string}){
  return<span className={cn("text-[9px] font-bold px-1 py-px rounded w-10 text-center inline-block",
    s==="BUY"||s==="LONG"?"text-emerald-400 bg-emerald-500/10":"text-red-400 bg-red-500/10")}>{s}</span>;
}

function TradeRow({trade}:{trade:any}){
  const[open,setOpen]=useState(false);
  const time=trade.exit_time?new Date(trade.exit_time*1000).toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour12:false}):"";
  const hold=trade.exit_time&&trade.entry_time?((trade.exit_time-trade.entry_time)/60).toFixed(0):"?";
  return(
    <div className={cn("cursor-pointer transition-colors",trade.net_pnl>=0?"hover:bg-emerald-500/[0.02]":"hover:bg-red-500/[0.02]")} onClick={()=>setOpen(o=>!o)}>
      <div className="px-3 py-1.5 flex items-center gap-3 text-xs">
        <span className="font-mono text-zinc-500 w-16">{time}</span>
        <span className="text-zinc-300 w-12">{N[trade.instrument]??trade.instrument}</span>
        <Side s={trade.side}/>
        <span className="font-mono text-zinc-500 w-32">₹{trade.entry_price?.toFixed(2)} → ₹{trade.exit_price?.toFixed(2)}</span>
        <span className="text-zinc-600 w-10">{hold}m</span>
        <span className="font-mono text-zinc-500 w-16">₹{trade.gross_pnl?.toFixed(2)}</span>
        <span className="font-mono text-zinc-600 w-16">-₹{trade.charges?.toFixed(2)}</span>
        <span className={cn("font-bold font-mono w-20 text-right tabular-nums",trade.net_pnl>=0?"text-emerald-400":"text-red-400")}>{trade.net_pnl>=0?"+":""}₹{trade.net_pnl?.toFixed(2)}</span>
        <ChevronDown className={cn("h-3 w-3 text-zinc-700 transition-transform shrink-0",open&&"rotate-180")}/>
      </div>
      {open&&(
        <div className="px-3 pb-2 text-[10px] text-zinc-500 ml-16 space-y-0.5">
          <p>Entry: ₹{trade.entry_price?.toFixed(2)} at {trade.entry_time?new Date(trade.entry_time*1000).toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour12:false}):""}</p>
          <p>Exit: ₹{trade.exit_price?.toFixed(2)} at {time}</p>
          <p>Gross: ₹{trade.gross_pnl?.toFixed(2)} | Charges: ₹{trade.charges?.toFixed(2)} | Net: {trade.net_pnl>=0?"+":""}₹{trade.net_pnl?.toFixed(2)}</p>
          <p>Reason: {trade.reason}</p>
        </div>
      )}
    </div>
  );
}
