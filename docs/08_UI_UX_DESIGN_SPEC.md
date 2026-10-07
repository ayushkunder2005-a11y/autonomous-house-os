# Architecture Document 08: UI/UX Design & Front-End Specification

> **Component:** Autonomous House OS — Presentation Layer & User Experience  
> **Target Framework:** Modern SPA (Vue 3 / Vite or React 18+ / Vite + TailwindCSS + Three.js / Canvas 2.5D)  
> **Target Implementer:** CODEX  

---

## 1. Design Philosophy & Aesthetic System

The user interface of House OS must look and feel like an **advanced aerospace cockpit meets minimalist architectural elegance**. It must instantly communicate the living state of the residence to a regular family member while providing deep telemetry and control for power users.

### 1.1 Aesthetic & Visual Tokens
- **Theme:** Default Obsidian Dark Mode with subtle glassmorphic layers and luminous status accents.
- **Color Palette (Tailwind Tokens):**
  - Background Base: `#0B0F17` (Deep Obsidian Void)
  - Surface Card: `rgba(18, 24, 38, 0.75)` (Glassmorphism with `backdrop-blur-md`)
  - Border Accents: `rgba(255, 255, 255, 0.08)`
  - Primary Accent (AI & Energy): `#38BDF8` (Cyan Neon)
  - Success / Safe State: `#10B981` (Emerald Glow)
  - Warning / Drift: `#F59E0B` (Amber Radiant)
  - Critical / Emergency: `#EF4444` (Crimson Pulse)
  - Water / Hydraulic: `#06B6D4` (Aqua Ocean)
- **Typography:** Inter / Outfit for clean readability; JetBrains Mono for system metrics, hex codes, and telemetry values.
- **Motion & Micro-interactions:** Fluid CSS transitions (200ms ease-out), pulsating indicators for live sensors, smooth camera transitions in the 2.5D twin.

---

## 2. Screen & Module Architecture (The 10 Core Views)

```
  +─────────────────────────────────────────────────────────────────────────────+
  |  TOP STATUS BAR: [House Health: 98/100] [Security: HOME] [P: 2.4kW] [W: 82%] |
  +───────────┬─────────────────────────────────────────────────────────────────+
  | SIDEBAR   | MAIN WORKSPACE VIEWPORT                                         |
  |           |                                                                 |
  | [Twin]    |   +---------------------------------------------------------+   |
  | [Rooms]   |   |                                                         |   |
  | [Devices] |   |              2.5D DIGITAL TWIN FLOORPLAN                |   |
  | [AI Brain]|   |        (Interactive Rooms, Thermal Heatmap, Lux)        |   |
  | [Memory]  |   |                                                         |   |
  | [Energy]  |   +---------------------------------------------------------+   |
  | [Water]   |                                                                 |
  | [Security]|   +────────────────────────+   +────────────────────────────+   |
  | [Health]  |   | QUICK SCENES & INTENTS |   | REAL-TIME RADAR & TELEMETRY|   |
  | [BlackBox]|   +────────────────────────+   +────────────────────────────+   |
  +───────────┴─────────────────────────────────────────────────────────────────+
```

### 2.1 View 1: Executive Master Dashboard & Digital Twin
- **Interactive 2.5D Floorplan Canvas:**
  - Displays floors with toggleable layers: **Thermal Heatmap**, **Lighting Lux**, **Occupancy Glow**, and **Security Zones**.
  - Clicking any room opens an instant spatial control modal (climate, lighting, shades, active devices).
- **Executive Status Bar:**
  - **House Health Pill:** Real-time radial score badge (e.g., `96/100`).
  - **Security State Capsule:** One-tap modal to toggle `HOME`, `SLEEP`, `AWAY` with PIN entry.
  - **Live Power Meter:** Real-time grid draw in kW with sparkline graph.
  - **Main Tank Level:** Water volume percentage gauge.
- **Natural Language Intent Input:** Global floating command bar (`Ctrl + K` / Voice Mic) with auto-suggestions and intent preview.

### 2.2 View 2: Spatial & Rooms Matrix
- Filterable cards for each room showing:
  - Temperature, humidity, illuminance, and occupancy indicator.
  - Active equipment count.
  - Sliders for lighting brightness and climate setpoint.
  - "Sleep Mode" and "Eco Mode" room toggle buttons.

### 2.3 View 3: Devices & Sensors Matrix
- Tabular and card views of all registered hardware nodes:
  - Connectivity status (Online / Offline / RSSI dBm signal bar).
  - ESP32 node IP, firmware version, and uptime counter.
  - Live capability toggles (e.g., dimming %, fan speed 1-4, valve open/close).
  - Diagnostic ping button to verify latency.

### 2.4 View 4: Automation & Conflict Studio
- **Visual Rule Builder:** Drag-and-drop or node-based trigger/condition/action creator.
- **Live Priority Matrix Inspector:** Shows which rule currently holds control over each actuator.
- **Conflict Visualizer:** Highlights competing rules and indicates why a lower-priority rule was preempted.

### 2.5 View 5: AI Assistant & Natural Language Console
- **Interactive Conversational Feed:**
  - User can type or speak queries.
  - Responses display structured cards with **Explainable AI (XAI) Badges**:
    - Tap `[Why?]` on any action to expand contributing sensor factors, weights, and evaluated alternatives.
  - **What-If Sandbox Panel:** Slider-driven sandbox allowing users to preview cost and power impact before executing macro changes.

### 2.6 View 6: House Memory & Black Box Time-Machine
- **Scrubbable Historical Timeline:**
  - Drag timeline scrubber to view historical house states at any moment in the past 30 days.
  - Searchable audit log: Filter by entity, user, priority tier, or incident keyword.
  - Forensic playback of alarm events (e.g., exact sequence of a water leak detection).

### 2.7 View 7: Energy Intelligence Center
- Real-time sankey diagram showing power flow (Grid / Solar / Battery $\to$ Circuit Sub-panels $\to$ Major Loads).
- Phase load balancing gauge (L1, L2, L3 currents).
- Hourly/Daily kWh bar chart with cost projections and peak-tariff alerts.
- Top power-draining appliances breakdown.

### 2.8 View 8: Water Intelligence Center
- Live 3D isometric representation of Underground Storage Tank and Overhead Tank.
- Booster pump operating state, continuous run timer, and dry-run protector indicator.
- Instantaneous flow rate (L/min) and acoustic leak risk index.

### 2.9 View 9: Security & Emergency Operations Console
- Arm / Disarm controls with secure on-screen numeric keypad.
- Perimeter sensor status list (Doors, Windows, Motion PIR).
- Prominent **Emergency Panic Trip Button** (guarded with slide-to-confirm gesture).
- Emergency Incident Reset console requiring administrative PIN.

### 2.10 View 10: Predictive Maintenance & House Health Radar
- **House Health Radar Chart:** 9-axis polygon (Safety, Security, Energy, Water, Devices, Sensors, Network, Environment, Maintenance).
- **Component Wear Indicators:** Progress bars for HVAC filter life, pump impeller hours, and valve cycles.
- **House Experiment Lab:** Launch and monitor controlled A/B energy trials with live comparison charts.

---

## 3. Responsive Breakpoints & Multi-Device Adaptation

CODEX must ensure full layout adaptability across all viewports:

| Device Category | Resolution Range | Layout Strategy |
| :--- | :--- | :--- |
| **Desktop / Wall Panel** | $\ge 1440\text{px}$ | 3-column cockpit: Fixed sidebar, full 2.5D interactive canvas, right telemetry dock. |
| **Laptop** | $1024\text{px} - 1439\text{px}$ | 2-column layout: Collapsible sidebar, main canvas with floating slide-out drawer. |
| **Tablet (Landscape/Portrait)** | $768\text{px} - 1023\text{px}$ | Touch-optimized cards, swipeable room carousels, bottom sheet modals for device settings. |
| **Mobile Smartphone** | $< 768\text{px}$ | Single-column view with bottom navigation bar (Home, Rooms, AI Brain, Security, Health). Minimalist cards with quick toggle buttons. |

---

## 4. Front-End Architecture & State Management

```
  +──────────────────────────────────────────────────────────────+
  |                   PINIA / REDUX GLOBAL STORE                 |
  |                                                              |
  |  - `twinStore`: In-memory replica of Digital Twin Snapshot   |
  |  - `wsStore`: WebSocket connection & channel subscriptions   |
  |  - `securityStore`: Mode, arming status, emergency flags    |
  |  - `uiStore`: Active view, theme, modals, notifications      |
  +──────────────────────────────┬───────────────────────────────+
                                 │
                   ┌─────────────┴─────────────┐
                   ▼                           ▼
        [WebSocket Delta Worker]    [HTTP Axios / Fetch Client]
        Receives instant deltas      Handles REST commands & auth
        Mutates store in-place       Dispatches with JWT headers
```

---

## 5. CODEX Implementation Directives

1. Use Vue 3 (Composition API `<script setup>`) with Vite, Pinia, and TailwindCSS (or equivalent React + Vite stack).
2. All real-time telemetry updates must bind directly to the Pinia store via the WebSocket stream without page reloads.
3. Interactive emergency controls must feature fail-safe UI elements (slide-to-activate, double-tap confirmation) to prevent accidental clicks.
4. Provide clean component decomposition in `frontend/src/components/` (`twin/`, `rooms/`, `devices/`, `brain/`, `energy/`, `water/`, `security/`, `health/`).
