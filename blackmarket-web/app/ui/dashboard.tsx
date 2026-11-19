"use client";
import { useCallback, useEffect, useState } from "react";
type Data = Record<string, any>;
const sections = ["Overview","Markets","Signals","Portfolio","Positions","Trades","Intelligence","Learning","Risk","Activity","Settings"] as const;
const endpoints: Record<string,string[]> = {
  Overview:["portfolio/summary","risk/status","learning/status","signals/stats","markets"],
  Markets:["markets","markets/symbols","markets/heatmap"],
  Signals:["signals","signals/stats"],
  Portfolio:["portfolio/balance","portfolio/summary"],
  Positions:["positions"],
  Trades:["trades","trades/stats"],
  Intelligence:["intelligence/strategies","intelligence/weights"],
  Learning:["learning/status","learning/predictions","learning/models"],
  Risk:["risk/status","risk/alerts"],
  Activity:["activity"],
  Settings:["settings"]
};
async function api(path:string, init?:RequestInit) {
  const response=await fetch("/api/backend/"+path,{...init,cache:"no-store",headers:{"Content-Type":"application/json",...(init?.headers||{})}});
  const data=await response.json().catch(()=>({}));
  if(response.status===401){location.assign("/login");throw new Error("Session expired");}
  if(!response.ok) throw new Error(data.detail||data.error||("API error "+response.status));
  return data;
}
function pretty(value:any):string {
  if(value===null||value===undefined)return "—";
  if(typeof value==="number")return Number.isFinite(value)?value.toLocaleString(undefined,{maximumFractionDigits:4}):"—";
  if(typeof value==="string")return value;
  return JSON.stringify(value,null,2);
}
function Card({title,children}:{title:string;children:React.ReactNode}){return <section className="panel"><h3>{title}</h3>{children}</section>}
export default function Dashboard(){
 const [section,setSection]=useState<(typeof sections)[number]>("Overview");
 const [data,setData]=useState<Record<string,Data>>({});
 const [error,setError]=useState(""); const [busy,setBusy]=useState(false); const [updated,setUpdated]=useState("");
 const load=useCallback(async()=>{
   setBusy(true);setError("");
   try{const paths=endpoints[section]||[];const values=await Promise.all(paths.map(async p=>[p,await api(p)] as const));setData(prev=>({...prev,...Object.fromEntries(values)}));setUpdated(new Date().toLocaleTimeString());}
   catch(e){setError(e instanceof Error?e.message:"Unable to load data");}
   finally{setBusy(false);}
 },[section]);
 useEffect(()=>{void load();const timer=window.setInterval(()=>void load(),15000);return()=>window.clearInterval(timer);},[load]);
 async function logout(){await fetch("/api/logout",{method:"POST"});location.assign("/login");}
 const entries=Object.entries(data).filter(([key])=>(endpoints[section]||[]).includes(key));
 return <main className="app-shell">
  <aside className="sidebar"><div className="brand"><b>BM<span>.</span></b><div>BLACKMARKET AI<small>MARKET INTELLIGENCE</small></div></div>
   <div className="nav-label">WORKSPACE</div>{sections.map(s=><button key={s} className={"nav-item "+(section===s?"active":"")} onClick={()=>setSection(s)}>{s}</button>)}
   <div className="sidebar-bottom"><div className="connection"><i/> API SESSION</div><button className="logout" onClick={logout}>Sign out ↗</button></div>
  </aside>
  <section className="main-area"><header className="topbar"><div><div className="eyebrow">BLACKMARKET / {section.toUpperCase()}</div><h1>{section}</h1></div><div className="top-actions"><span className="status"><i/> PAPER MODE</span><button className="refresh" onClick={()=>void load()} disabled={busy}>{busy?"Refreshing…":"↻ Refresh"}</button></div></header>
   <div className="content"><div className="welcome-row"><div><h2>{section==="Overview"?"Market overview":section+" workspace"}</h2><p>Exchange research · Strategy intelligence · Simulated execution</p></div><small>Updated {updated||"—"}</small></div>
    {error&&<div className="error-banner"><b>Connection issue</b> {error}. Check backend availability and deployment environment variables.</div>}
    {section==="Overview"&&<div className="metric-grid">{["portfolio/summary","risk/status","learning/status","signals/stats"].map(k=><Card key={k} title={k.split("/").join(" · ")}><pre>{pretty(data[k])}</pre></Card>)}</div>}
    {section==="Settings"&&<SettingsPanel current={data["settings"]} onSave={async(value)=>{const result=await api("settings",{method:"POST",body:JSON.stringify(value)});await load();return result;}}/>}
    <div className="data-grid">{entries.filter(([k])=>section!=="Overview"||k==="markets").map(([key,value])=><Card key={key} title={key.replaceAll("/"," · ")}><DataView value={value}/></Card>)}</div>
    {entries.length===0&&!error&&<div className="empty">No response data yet. Refresh after the backend has started.</div>}
    <div className="notice">Research and paper-trading interface. No live exchange orders are submitted by this web dashboard.</div>
   </div>
  </section>
 </main>;
}
function DataView({value}:{value:any}){
 if(Array.isArray(value)){if(!value.length)return <div className="muted">No records returned.</div>;return <div className="table-wrap"><table><tbody>{value.slice(0,100).map((row:any,i)=><tr key={i}><td>{typeof row==="object"?Object.entries(row).slice(0,5).map(([k,v])=><div key={k}><b>{k}</b> {pretty(v)}</div>).reduce((a,b)=>[a,b] as any):pretty(row)}</td></tr>)}</tbody></table></div>}
 if(value&&typeof value==="object")return <div className="kv">{Object.entries(value).map(([k,v])=><div key={k}><span>{k.replaceAll("_"," ")}</span><b>{typeof v==="object"?pretty(v):pretty(v)}</b></div>)}</div>;
 return <pre>{pretty(value)}</pre>;
}
function SettingsPanel({current,onSave}:{current:any;onSave:(value:any)=>Promise<any>}){
 const [draft,setDraft]=useState<any>(current??{});const [timeframes,setTimeframes]=useState((current?.timeframes??[]).join(", "));
 const [saving,setSaving]=useState(false);const [message,setMessage]=useState("");const [restartRequired,setRestartRequired]=useState<string[]>(current?.restart_required??[]);
 useEffect(()=>{if(current){setDraft(current);setTimeframes((current.timeframes??[]).join(", "));setRestartRequired(current.restart_required??[]);}},[current]);
 const toggle=(key:string,value:boolean)=>setDraft((old:any)=>({...old,[key]:value}));
 const number=(key:string,label:string,min:number,max:number,step=1)=><label className="settings-field"><span>{label}</span><input type="number" min={min} max={max} step={step} value={draft[key]??""} onChange={e=>setDraft((old:any)=>({...old,[key]:e.target.value===""?undefined:Number(e.target.value)}))}/></label>;
 async function save(){
  setSaving(true);setMessage("");
  try{
   const payload={spot_enabled:draft.spot_enabled,futures_enabled:draft.futures_enabled,scan_all_eligible_symbols:draft.scan_all_eligible_symbols,telegram_enabled:draft.telegram_enabled,timeframes:timeframes.split(",").map((v:string)=>v.trim()).filter(Boolean),spot_initial_balance:draft.spot_initial_balance,futures_initial_balance:draft.futures_initial_balance,risk_per_trade_pct:draft.risk_per_trade_pct,risk_max_daily_loss_pct:draft.risk_max_daily_loss_pct,risk_max_total_open_pct:draft.risk_max_total_open_pct,risk_max_leverage:draft.risk_max_leverage,max_spot_positions:draft.max_spot_positions,max_futures_positions:draft.max_futures_positions};
   const result=await onSave(payload);const required=result.restart_required??[];setRestartRequired(required);
   setMessage(required.length?"Saved. Restart the backend to apply: "+required.join(", "):"Settings saved and applied.");
  }catch(e){setMessage(e instanceof Error?e.message:"Save failed");}
  finally{setSaving(false);}
 }
 return <Card title="Shared engine configuration">
  <p className="muted">These settings are stored in the shared backend database and are used by the desktop and website. Secret credentials are never shown or editable here.</p>
  {!current?<p className="muted">Settings are unavailable until the backend connects.</p>:<>
   <div className="settings-toggle-grid">
    {([["spot_enabled","Spot market data"],["futures_enabled","USDⓈ-M futures"],["scan_all_eligible_symbols","Scan all eligible symbols"],["telegram_enabled","Telegram notifications"]] as [string,string][]).map(([key,label])=><label className="settings-toggle" key={key}><input type="checkbox" checked={Boolean(draft[key])} onChange={e=>toggle(key,e.target.checked)}/><span>{label}</span></label>)}
   </div>
   <div className="settings-fields">
    {number("spot_initial_balance","Spot virtual capital",0.01,1000000000,0.01)}
    {number("futures_initial_balance","Futures virtual capital",0.01,1000000000,0.01)}
    {number("risk_per_trade_pct","Risk per trade (%)",0.01,10,0.01)}
    {number("risk_max_daily_loss_pct","Maximum daily loss (%)",0.01,20,0.01)}
    {number("risk_max_total_open_pct","Maximum open risk (%)",0.01,50,0.01)}
    {number("risk_max_leverage","Maximum leverage",1,20,0.1)}
    {number("max_spot_positions","Maximum spot positions",1,100)}
    {number("max_futures_positions","Maximum futures positions",1,100)}
    <label className="settings-field settings-timeframes"><span>Analysis timeframes · comma separated</span><input value={timeframes} onChange={e=>setTimeframes(e.target.value)} placeholder="1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"/></label>
   </div>
   <div className="settings-save-row"><button className="primary" disabled={saving} onClick={()=>void save()}>{saving?"Saving…":"Save shared settings"}</button><span role="status">{message}</span></div>
   {restartRequired.length>0&&<p className="settings-warning" role="status">Restart required before these changes take effect: {restartRequired.join(", ")}.</p>}
   <p className="muted">Virtual capital cannot be changed while positions or orders are open. Telegram can only be enabled after credentials are configured securely. Real-money execution remains disabled.</p>
   <div className="settings-credential-status"><span>Telegram bot token <b>{current.telegram_bot_token_configured?"Configured":"Not configured"}</b></span><span>Telegram chat ID <b>{current.telegram_chat_id_configured?"Configured":"Not configured"}</b></span></div>
  </>}
 </Card>;
}
