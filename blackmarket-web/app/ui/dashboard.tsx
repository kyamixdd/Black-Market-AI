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
    {section==="Settings"&&<SettingsPanel current={data["settings"]} onSave={async(value)=>{await api("settings",{method:"POST",body:JSON.stringify(value)});await load();}}/>}
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
function SettingsPanel({current,onSave}:{current:any;onSave:(value:any)=>Promise<void>}){
 const [text,setText]=useState("");const [saving,setSaving]=useState(false);const [message,setMessage]=useState("");
 useEffect(()=>{setText(JSON.stringify(current??{},null,2));},[current]);
 return <Card title="Runtime configuration"><p className="muted">Edit the backend-supported settings payload. Secret values are not displayed here.</p><textarea value={text} onChange={e=>setText(e.target.value)} rows={12}/><button className="primary" disabled={saving} onClick={async()=>{setSaving(true);setMessage("");try{await onSave(JSON.parse(text));setMessage("Settings saved.");}catch(e){setMessage(e instanceof Error?e.message:"Save failed");}finally{setSaving(false);}}}>{saving?"Saving…":"Save settings"}</button>{message&&<p className="muted">{message}</p>}</Card>;
}