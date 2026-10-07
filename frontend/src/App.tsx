import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Activity, Brain, Building2, Database, Droplets, Gauge, HeartPulse,
  LayoutDashboard, Lightbulb, LogOut, Menu, Shield, Wrench,
} from "lucide-react";

type Twin = {
  name: string; security_mode: string; health_score: number; active_power_watts: number;
  daily_energy_kwh: number; main_tank_level_pct: number; water_flow_lpm: number;
  floors: Array<{ floor_id: string; name: string; rooms: Room[] }>;
};
type Room = { room_id: string; name: string; current_temperature?: number; current_humidity?: number; occupancy_detected: boolean; devices: Device[] };
type Device = { device_id: string; name: string; category: string; is_online: boolean; current_state: Record<string, unknown>; health_score: number };

const views = [
  ["Dashboard", LayoutDashboard], ["Rooms", Building2], ["Devices", Lightbulb],
  ["Brain", Brain], ["Memory", Database], ["Energy", Activity], ["Water", Droplets],
  ["Security", Shield], ["Health", HeartPulse], ["Maintenance", Wrench],
] as const;

async function api<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(init?.headers || {}) },
  });
  if (!response.ok) throw new Error((await response.json()).error?.message || response.statusText);
  return response.json();
}

function Login({ onToken }: { onToken: (token: string) => void }) {
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const form = new FormData(event.currentTarget);
    const body = new URLSearchParams({ username: String(form.get("email")), password: String(form.get("password")) });
    const response = await fetch("/api/v1/auth/token", { method: "POST", body });
    const data = await response.json();
    if (!response.ok) return setError(data.error?.message || "Sign in failed");
    localStorage.setItem("house_token", data.access_token); onToken(data.access_token);
  }
  return <main className="login-shell"><form className="login-card" onSubmit={submit}>
    <div className="brand-mark"><Gauge size={26} /></div><p className="eyebrow">LOCAL EDGE CONSOLE</p>
    <h1>House OS</h1><p className="muted">Your home, understood as one living system.</p>
    <label>Email<input name="email" type="email" required autoComplete="username" /></label>
    <label>Password<input name="password" type="password" required autoComplete="current-password" /></label>
    {error && <p className="error">{error}</p>}<button>Enter console</button>
  </form></main>;
}

function Metric({ label, value, unit, tone = "cyan" }: { label: string; value: string | number; unit?: string; tone?: string }) {
  return <article className={`metric ${tone}`}><p>{label}</p><strong>{value}</strong>{unit && <span>{unit}</span>}</article>;
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem("house_token") || "");
  const [view, setView] = useState("Dashboard"); const [twin, setTwin] = useState<Twin | null>(null);
  const [error, setError] = useState(""); const [open, setOpen] = useState(false);
  const devices = useMemo(() => twin?.floors.flatMap(f => f.rooms.flatMap(r => r.devices)) || [], [twin]);
  async function refresh() { try { setTwin(await api<Twin>("/twin/state", token)); setError(""); } catch (e) { setError(String(e)); } }
  useEffect(() => { if (!token) return; refresh(); const id = window.setInterval(refresh, 5000); return () => clearInterval(id); }, [token]);
  useEffect(() => {
    if (!token) return; const scheme = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${location.host}/api/v1/ws/live-stream?token=${encodeURIComponent(token)}`);
    ws.onopen = () => ws.send(JSON.stringify({ action: "SUBSCRIBE", channels: ["twin:rooms:*", "energy:live", "water:tank", "security:status", "emergency:alerts"] }));
    ws.onmessage = event => { const message = JSON.parse(event.data); if (message.type === "PING") ws.send(JSON.stringify({ type: "PONG" })); else if (message.event === "STATE_DELTA") refresh(); };
    return () => ws.close();
  }, [token]);
  if (!token) return <Login onToken={setToken} />;
  const rooms = twin?.floors.flatMap(f => f.rooms) || [];
  return <div className="app-shell">
    <aside className={open ? "open" : ""}><div className="brand"><div className="brand-mark"><Gauge /></div><div><b>HOUSE OS</b><small>EDGE ONLINE</small></div></div>
      <nav>{views.map(([name, Icon]) => <button key={name} className={view === name ? "active" : ""} onClick={() => { setView(name); setOpen(false); }}><Icon size={18} />{name}</button>)}</nav>
      <button className="logout" onClick={() => { localStorage.removeItem("house_token"); setToken(""); }}><LogOut size={18} /> Sign out</button>
    </aside>
    <main className="content"><header><button className="menu" onClick={() => setOpen(!open)}><Menu /></button><div><p className="eyebrow">AUTONOMOUS HOUSE OPERATING SYSTEM</p><h1>{view}</h1></div><span className={`mode ${twin?.security_mode?.toLowerCase()}`}>{twin?.security_mode || "—"}</span></header>
      {error && <div className="alert">{error}</div>}
      {view === "Dashboard" && <><section className="hero"><div><p className="eyebrow">LIVE DIGITAL TWIN</p><h2>{twin?.name || "Synchronizing…"}</h2><p className="muted">{rooms.length} rooms · {devices.filter(d => d.is_online).length}/{devices.length} devices online</p></div><div className="health-ring" style={{ "--score": twin?.health_score || 0 } as React.CSSProperties}><strong>{twin?.health_score || 0}</strong><span>Health</span></div></section>
        <section className="metrics"><Metric label="Live demand" value={Math.round(twin?.active_power_watts || 0)} unit="W" /><Metric label="Energy today" value={(twin?.daily_energy_kwh || 0).toFixed(2)} unit="kWh" tone="violet" /><Metric label="Main tank" value={Math.round(twin?.main_tank_level_pct || 0)} unit="%" tone="blue" /><Metric label="Water flow" value={(twin?.water_flow_lpm || 0).toFixed(1)} unit="L/min" tone="green" /></section>
        <h3>Spatial overview</h3><section className="room-grid">{rooms.map(room => <article className="room-card" key={room.room_id}><div><h4>{room.name}</h4><span className={room.occupancy_detected ? "presence active" : "presence"}>{room.occupancy_detected ? "Occupied" : "Quiet"}</span></div><p className="temperature">{room.current_temperature?.toFixed(1) ?? "—"}<small>°C</small></p><p className="muted">{room.current_humidity?.toFixed(0) ?? "—"}% humidity · {room.devices.length} devices</p></article>)}</section></>}
      {view === "Rooms" && <section className="room-grid">{rooms.map(room => <article className="room-card" key={room.room_id}><h3>{room.name}</h3><p>{room.current_temperature ?? "—"} °C</p><p className="muted">{room.devices.length} connected fixtures</p></article>)}</section>}
      {view === "Devices" && <section className="table-card">{devices.map(device => <div className="device-row" key={device.device_id}><span className={device.is_online ? "dot online" : "dot"} /><div><b>{device.name}</b><small>{device.category}</small></div><code>{JSON.stringify(device.current_state)}</code><strong>{device.health_score}%</strong></div>)}</section>}
      {!['Dashboard','Rooms','Devices'].includes(view) && <section className="empty-state"><div className="brand-mark">{view === 'Brain' ? <Brain /> : <Gauge />}</div><h2>{view} workspace</h2><p className="muted">Connected to the local House OS service. Domain data and realtime alerts appear here as they become available.</p></section>}
    </main>
  </div>;
}

