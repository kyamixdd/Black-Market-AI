"use client";
import { useState } from "react";
export default function Login() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const response = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Login failed");
      location.assign("/");
    } catch (err) { setError(err instanceof Error ? err.message : "Login failed"); }
    finally { setBusy(false); }
  }
  return <main className="login-shell"><form className="login-card" onSubmit={submit}>
    <div className="eyebrow">PRIVATE TRADING TERMINAL</div><div className="brand-mark">BM<span>.</span></div>
    <h1>BlackMarket AI</h1><p>Sign in to your private market intelligence workspace.</p>
    <label htmlFor="password">Access password</label><input id="password" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required autoFocus />
    {error && <div className="error">{error}</div>}<button disabled={busy}>{busy ? "Authenticating…" : "Enter workspace"}</button>
    <small>Remote access is protected. Your API credentials remain server-side.</small>
  </form></main>;
}