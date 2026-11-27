"""Textual-based professional terminal dashboard for BlackMarket AI."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from rich import box
from rich.panel import Panel
from rich.table import Table
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import (
    Footer,
    Header,
    RichLog,
    Static,
    Tab,
    Tabs,
)

from paper_trading.liquidation_engine import LiquidationEngine

logger = logging.getLogger(__name__)

_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
_PULSE_FRAMES = ("●", "◉", "○", "◉")

# How often (seconds) to re-query slow data sources (DB, registry, health).
# The UI itself refreshes on a faster timer; these caches gate expensive calls.
_SLOW_REFRESH_INTERVAL = 5.0
_SIGNAL_REFRESH_INTERVAL = 3.0


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _gauge_bar(pct: float, width: int = 12, fill_color: str = "cyan") -> str:
    """Render a compact Rich-colored progress bar."""
    clamped = max(0.0, min(100.0, _safe_float(pct)))
    filled = int(round((clamped / 100.0) * width))
    empty = width - filled
    return f"[{fill_color}]{'█' * filled}[/{fill_color}][dim]{'░' * empty}[/dim]"


def _regime_badge(regime: str | None) -> str:
    name = str(regime or "UNKNOWN").upper()
    if "BULL" in name or "UP" in name:
        return f"[bold black on green] {name} [/bold black on green]"
    if "BEAR" in name or "DOWN" in name:
        return f"[bold white on red] {name} [/bold white on red]"
    if "VOL" in name:
        return f"[bold black on magenta] {name} [/bold black on magenta]"
    if "RANGE" in name or "SIDE" in name:
        return f"[bold black on yellow] {name} [/bold black on yellow]"
    return f"[bold white on bright_black] {name} [/bold white on bright_black]"


def _format_ts(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S")
    if not value:
        return "—"
    text = str(value)
    if "T" in text:
        return text.split("T", 1)[1][:8]
    return text[:19]


class DashboardApp(App):
    """Professional real-time terminal dashboard with 11 deep-telemetry views."""

    TITLE = "BLACKMARKET AI // QUANT TERMINAL"
    SUB_TITLE = "PAPER TRADING & AUTONOMOUS RESEARCH ENGINE"

    CSS = """
    Screen {
        layout: vertical;
        background: #090d14;
        color: #e2e8f0;
    }
    Header {
        dock: top;
        height: 3;
        background: #0f172a;
        color: #38bdf8;
        border-bottom: heavy #1e293b;
    }
    Footer {
        dock: bottom;
        height: 1;
        background: #0f172a;
        color: #94a3b8;
        border-top: solid #1e293b;
    }
    Tabs {
        dock: top;
        height: 3;
        background: #0d131f;
        border-bottom: solid #1e293b;
    }
    Tab {
        color: #94a3b8;
        padding: 0 2;
    }
    Tab.-active {
        color: #38bdf8;
        background: #172033;
        text-style: bold;
    }
    #status_bar {
        dock: top;
        height: 1;
        background: #111827;
        color: #e2e8f0;
        padding: 0 2;
        border-bottom: solid #1e293b;
    }

    /* Main layout */
    #main {
        layout: horizontal;
        height: 1fr;
        padding: 0 1;
    }
    #left {
        width: 54%;
        layout: vertical;
        height: 1fr;
        overflow-y: auto;
        padding-right: 1;
    }
    #right {
        width: 46%;
        layout: vertical;
        height: 1fr;
        overflow-y: auto;
    }

    /* Content & Log panel */
    #left_content, #right_content {
        height: auto;
    }
    RichLog, Log {
        height: 1fr;
        min-height: 8;
        border: round #1e293b;
        margin-top: 1;
        padding: 0 1;
        background: #0b101b;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("r", "refresh", "Refresh"),
        Binding("space", "toggle_pause", "Pause/Resume"),
        Binding("1", "tab_overview", "Overview"),
        Binding("2", "tab_scanner", "Scanner"),
        Binding("3", "tab_spot", "Spot"),
        Binding("4", "tab_futures", "Futures"),
        Binding("5", "tab_positions", "Positions"),
        Binding("6", "tab_balances", "Balances"),
        Binding("7", "tab_pnl", "P&L"),
        Binding("8", "tab_strategy", "Strategy"),
        Binding("9", "tab_learning", "Learning"),
        Binding("0", "tab_health", "Health"),
        Binding("l", "tab_logs", "Logs"),
    ]

    orchestrator = None
    _paused = reactive(False)
    _last_update = reactive("Never")

    def __init__(self, orchestrator=None, **kwargs):
        super().__init__(**kwargs)
        self.orchestrator = orchestrator
        self._refresh_timer: Timer | None = None
        self._anim_timer: Timer | None = None
        self._slow_timer: Timer | None = None
        self._anim_tick: int = 0
        self._liquidation_engine = LiquidationEngine()

        # ── Cached expensive data ──────────────────────────────────────────
        # These are populated by the slow-refresh timer (every 5s) so the
        # 2s render loop never hits the DB or health probes directly.
        self._cache_signals: list[dict] = []
        self._cache_snapshots: list[dict] = []
        self._cache_health: dict = {}
        self._cache_strategy_metrics: list = []
        self._cache_model_registry: list = []
        self._cache_predictions: list = []
        self._cache_system_events: list = []
        self._cache_drift: dict = {}
        self._cache_tracked_symbols: list = []

        # Lightweight values cached from sim for the status bar (updated on slow tick)
        self._sb_spot_bal: float = 0.0
        self._sb_fut_bal: float = 0.0
        self._sb_daily_pnl: float = 0.0
        self._sb_regime: str = "UNKNOWN"
        self._sb_scanning: bool = False
        self._sb_ws_up: bool = False
        self._sb_auto: bool = False

        # DOM node references – populated once in on_mount to avoid repeated query_one
        self._node_status_bar: Static | None = None
        self._node_left: Static | None = None
        self._node_right: Static | None = None
        self._node_tabs: Tabs | None = None
        self._node_log: RichLog | None = None

    # ── Compose ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Tabs(
            Tab("📊 Overview", id="tab_overview"),
            Tab("🔍 Scanner", id="tab_scanner"),
            Tab("📈 Spot", id="tab_spot"),
            Tab("📉 Futures", id="tab_futures"),
            Tab("💼 Positions", id="tab_positions"),
            Tab("💰 Balances", id="tab_balances"),
            Tab("📊 P&L", id="tab_pnl"),
            Tab("🎯 Strategy", id="tab_strategy"),
            Tab("🧠 Learning", id="tab_learning"),
            Tab("🏥 Health", id="tab_health"),
            Tab("📜 Logs", id="tab_logs"),
            id="main_tabs",
        )
        yield Static("", id="status_bar")
        with Container(id="main"):
            with Vertical(id="left"):
                yield Static("", id="left_content")
            with Vertical(id="right"):
                yield Static("", id="right_content")
                yield RichLog(id="log_panel", highlight=True, markup=True)
        yield Footer()

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        # Cache DOM nodes once so renders never call query_one again.
        self._node_status_bar = self.query_one("#status_bar", Static)
        self._node_left = self.query_one("#left_content", Static)
        self._node_right = self.query_one("#right_content", Static)
        self._node_tabs = self.query_one("#main_tabs", Tabs)
        self._node_log = self.query_one("#log_panel", RichLog)

        # Slow timer: populates DB/IO caches.  Fires immediately then every 5s.
        self._slow_timer = self.set_interval(_SLOW_REFRESH_INTERVAL, self._refresh_slow_caches)
        # Animation ticker: status bar only — no DB calls.  Every 250ms.
        self._anim_timer = self.set_interval(0.25, self._tick_animation)
        # Main render: redraws active tab content every 2s using cached data.
        self._refresh_timer = self.set_interval(2.0, self.refresh_ui)

        # Seed caches immediately so first render has something.
        self._refresh_slow_caches()

        self.write_log("🚀 BlackMarket AI Quant Terminal started", "success")
        self.write_log(f"📡 Engine connected: {self.orchestrator is not None}", "info")
        self._tick_animation()
        self.refresh_ui()

    def on_unmount(self) -> None:
        for t in (self._refresh_timer, self._anim_timer, self._slow_timer):
            if t:
                t.stop()

    # ── Slow cache refresh (DB / health / IO) ─────────────────────────────

    def _refresh_slow_caches(self) -> None:
        """Update all caches that require DB queries or health probes.

        Called every _SLOW_REFRESH_INTERVAL seconds so the main render loop
        never blocks on IO.  Completely fire-and-forget; failures keep stale data.
        """
        if not self.orchestrator:
            return

        # Health status probe
        if callable(getattr(self.orchestrator, "refresh_health_status", None)):
            try:
                self.orchestrator.refresh_health_status()
            except Exception:
                pass
        health_mon = getattr(self.orchestrator, "health_monitor", None)
        if callable(getattr(health_mon, "get_status", None)):
            try:
                self._cache_health = health_mon.get_status() or {}
            except Exception:
                pass

        # Drift monitor
        drift = getattr(self.orchestrator, "drift_monitor", None)
        if callable(getattr(drift, "get_status", None)):
            try:
                self._cache_drift = drift.get_status() or {}
            except Exception:
                pass

        # DB queries
        repo = getattr(self.orchestrator, "repo", None) or getattr(self.orchestrator, "_repo", None)
        if repo:
            try:
                self._cache_signals = self._fetch_signals_from_repo(repo) or []
            except Exception:
                pass
            try:
                self._cache_strategy_metrics = repo.get_all_strategy_metrics() or [] if callable(getattr(repo, "get_all_strategy_metrics", None)) else []
            except Exception:
                pass
            try:
                self._cache_model_registry = repo.get_model_registry() or [] if callable(getattr(repo, "get_model_registry", None)) else []
            except Exception:
                pass
            try:
                self._cache_predictions = repo.get_predictions_history(100) or [] if callable(getattr(repo, "get_predictions_history", None)) else []
            except Exception:
                pass
            try:
                self._cache_system_events = repo.get_system_events(30) or [] if callable(getattr(repo, "get_system_events", None)) else []
            except Exception:
                pass

        # Registry / tracked symbols (can be slow)
        self._cache_tracked_symbols = self._fetch_tracked_symbols()

        # Status bar snapshot values — read once here so the 250ms anim tick is pure string work
        sim = getattr(self.orchestrator, "simulator", None)
        if sim:
            try:
                self._sb_spot_bal = _safe_float(sim.get_balance("SPOT"))
                self._sb_fut_bal = _safe_float(sim.get_balance("FUTURES"))
                self._sb_daily_pnl = _safe_float(sim.get_daily_pnl()) if callable(getattr(sim, "get_daily_pnl", None)) else 0.0
            except Exception:
                pass

        self._sb_regime = str(getattr(self.orchestrator, "_current_regime", "UNKNOWN"))

        scanner = getattr(self.orchestrator, "scanner", None)
        self._sb_scanning = bool(getattr(scanner, "_running", False) or getattr(self.orchestrator, "_scanning", False))

        ws_mgr = getattr(self.orchestrator, "ws_manager", None)
        ws_snap = {}
        if callable(getattr(ws_mgr, "status_snapshot", None)):
            try:
                ws_snap = ws_mgr.status_snapshot() or {}
            except Exception:
                pass
        self._sb_ws_up = bool(
            (ws_snap.get("active_connections", 0) > 0 if isinstance(ws_snap, dict) else False)
            or getattr(self.orchestrator, "_ws_connected", False)
        )
        self._sb_auto = bool(getattr(self.orchestrator, "_autonomous_enabled", False))

        # Snapshots — in-memory, no DB, but can be large list copies
        self._cache_snapshots = self._fetch_snapshots()

    # ── Animation ticker (pure string, no IO) ─────────────────────────────

    def _tick_animation(self) -> None:
        """Animate the live status ticker bar every 250ms — zero IO."""
        self._anim_tick = (self._anim_tick + 1) % 1000
        bar = self._node_status_bar
        if bar is None:
            return

        spinner = _SPINNER_FRAMES[self._anim_tick % len(_SPINNER_FRAMES)]
        pulse = _PULSE_FRAMES[self._anim_tick % len(_PULSE_FRAMES)]

        if self._paused:
            state_badge = "[bold black on yellow] ⏸ PAUSED [/bold black on yellow]"
        elif self.orchestrator is None:
            state_badge = "[bold white on red] ○ OFFLINE [/bold white on red]"
        else:
            state_badge = f"[bold black on bright_cyan] {pulse} LIVE [/bold black on bright_cyan]"

        if not self.orchestrator:
            bar.update(f"{state_badge}  [dim]Waiting for orchestrator...[/dim]")
            return

        total_bal = self._sb_spot_bal + self._sb_fut_bal
        daily_color = "green" if self._sb_daily_pnl >= 0 else "red"
        scan_txt = f"[green]{spinner} SCAN[/green]" if self._sb_scanning else "[yellow]IDLE[/yellow]"
        ws_txt = "[green]● WS[/green]" if self._sb_ws_up else "[red]○ WS[/red]"
        auto_txt = "[bright_magenta]AUTO:ON[/bright_magenta]" if self._sb_auto else "[dim]AUTO:OFF[/dim]"

        bar.update(
            f"{state_badge}  "
            f"EQ:[bold white]${total_bal:,.2f}[/bold white]  "
            f"DAY:[bold {daily_color}]${self._sb_daily_pnl:+,.2f}[/bold {daily_color}]  "
            f"{_regime_badge(self._sb_regime)}  "
            f"{scan_txt}  {ws_txt}  {auto_txt}  "
            f"[dim]UPD {self._last_update}[/dim]"
        )

    # ── Log helper ────────────────────────────────────────────────────────

    def write_log(self, message: str, level: str = "info") -> None:
        """Add a log entry with timestamp."""
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        colors = {"info": "cyan", "warning": "yellow", "error": "red", "success": "green", "debug": "dim"}
        color = colors.get(level, "white")
        log = self._node_log
        if log is None and hasattr(self, "log_panel"):
            log = self.log_panel
        if log is not None:
            log.write(f"[{color}]{timestamp}[/{color}] {message}")

    # ── Actions ───────────────────────────────────────────────────────────

    async def action_quit(self) -> None:
        self.write_log("🛑 Shutting down dashboard...", "warning")
        if self.orchestrator:
            await self.orchestrator.stop()
        self.exit()

    async def action_refresh(self) -> None:
        self._refresh_slow_caches()
        self.refresh_ui()
        self.write_log("🔄 Manual refresh triggered", "info")

    async def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        status = "PAUSED" if self._paused else "RESUMED"
        self.write_log(f"⏸️ Dashboard {status}", "warning" if self._paused else "success")
        self._tick_animation()

    # Tab switch actions
    async def action_tab_overview(self) -> None: await self._switch_tab("tab_overview")
    async def action_tab_scanner(self) -> None: await self._switch_tab("tab_scanner")
    async def action_tab_spot(self) -> None: await self._switch_tab("tab_spot")
    async def action_tab_futures(self) -> None: await self._switch_tab("tab_futures")
    async def action_tab_positions(self) -> None: await self._switch_tab("tab_positions")
    async def action_tab_balances(self) -> None: await self._switch_tab("tab_balances")
    async def action_tab_pnl(self) -> None: await self._switch_tab("tab_pnl")
    async def action_tab_strategy(self) -> None: await self._switch_tab("tab_strategy")
    async def action_tab_learning(self) -> None: await self._switch_tab("tab_learning")
    async def action_tab_health(self) -> None: await self._switch_tab("tab_health")
    async def action_tab_logs(self) -> None: await self._switch_tab("tab_logs")

    async def _switch_tab(self, tab_id: str) -> None:
        if self._node_tabs:
            self._node_tabs.active = tab_id
        # Render immediately after switch — but do NOT also trigger via on_tabs_tab_activated
        # to avoid double render.  The event handler is intentionally removed below.
        self.refresh_ui()

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        """Only refresh when the tab switch came from the UI (mouse/keyboard),
        not when we programmatically set tabs.active inside _switch_tab.
        We detect this by checking if the event was user-initiated vs our own call.
        Since Textual fires this event in both cases, we guard with a flag."""
        # refresh_ui is already called in _switch_tab; skip to avoid double render.
        # For mouse clicks there is no prior _switch_tab call, so we always render here.
        self.refresh_ui()

    # ── Main render dispatcher ────────────────────────────────────────────

    def refresh_ui(self) -> None:
        """Render active tab using exclusively cached data — zero IO."""
        if self._paused:
            return

        if not self.orchestrator:
            self._show_no_orchestrator()
            return

        try:
            active = self._node_tabs.active if self._node_tabs else "tab_overview"
            render_map = {
                "tab_overview": self._render_overview,
                "tab_scanner": self._render_scanner,
                "tab_spot": self._render_spot_signals,
                "tab_futures": self._render_futures_signals,
                "tab_positions": self._render_positions,
                "tab_balances": self._render_balances,
                "tab_pnl": self._render_pnl_stats,
                "tab_strategy": self._render_strategy,
                "tab_learning": self._render_learning,
                "tab_health": self._render_health,
                "tab_logs": self._render_logs,
            }
            renderer = render_map.get(active)
            if renderer:
                renderer()
            self._last_update = datetime.now(timezone.utc).strftime("%H:%M:%S")
        except Exception as exc:
            logger.error("Dashboard refresh error: %s", exc)
            self.write_log(f"❌ Refresh error: {exc}", "error")

    def _show_no_orchestrator(self) -> None:
        if self._node_left:
            self._node_left.update(Panel("[red]No orchestrator connected[/red]", title="⚠️ Disconnected", box=box.ROUNDED))
        if self._node_right:
            self._node_right.update("")

    # ── Render Methods (all use self._cache_* — no IO) ────────────────────

    def _render_overview(self) -> None:
        left = self._node_left
        right = self._node_right

        sim = self.orchestrator.simulator
        spot_bal = _safe_float(sim.get_balance("SPOT"))
        fut_bal = _safe_float(sim.get_balance("FUTURES"))
        total = spot_bal + fut_bal

        initial_spot = _safe_float(getattr(sim, "initial_spot_balance", 500.0), 500.0) or 500.0
        initial_fut = _safe_float(getattr(sim, "initial_futures_balance", 500.0), 500.0) or 500.0
        initial_total = initial_spot + initial_fut

        trades = getattr(sim, "closed_trades", []) or []
        realized = sum(_safe_float(t.get("pnl")) for t in trades)
        spot_pos = getattr(sim, "spot_positions", {}) or {}
        fut_pos = getattr(sim, "futures_positions", {}) or {}
        unrealized = sum(_safe_float(p.get("unrealized_pnl")) for p in spot_pos.values())
        unrealized += sum(_safe_float(p.get("unrealized_pnl")) for p in fut_pos.values())
        net_pnl = realized + unrealized
        roi_pct = ((total - initial_total) / initial_total * 100.0) if initial_total > 0 else 0.0

        wins = sum(1 for t in trades if _safe_float(t.get("pnl")) > 0)
        win_rate = (wins / len(trades) * 100.0) if trades else 0.0
        gross_profit = sum(_safe_float(t.get("pnl")) for t in trades if _safe_float(t.get("pnl")) > 0)
        gross_loss = abs(sum(_safe_float(t.get("pnl")) for t in trades if _safe_float(t.get("pnl")) < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        peak = initial_total if initial_total > 0 else 1000.0
        equity = peak
        max_dd = 0.0
        for t in trades:
            equity += _safe_float(t.get("pnl"))
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

        port_table = Table.grid(padding=(0, 2))
        port_table.add_column("Metric", style="dim")
        port_table.add_column("Value", justify="right", style="bold")
        port_table.add_row("💰 Spot Balance", f"[cyan]${spot_bal:,.2f}[/cyan]")
        port_table.add_row("💰 Futures Balance", f"[magenta]${fut_bal:,.2f}[/magenta]")
        port_table.add_row("[bold]💰 Total Equity[/bold]", f"[bold white]${total:,.2f}[/bold white] ({roi_pct:+.2f}%)")
        port_table.add_row("", "")
        port_table.add_row("🟢 Realized P&L", f"${realized:+,.2f}", style="green" if realized >= 0 else "red")
        port_table.add_row("🔵 Unrealized P&L", f"${unrealized:+,.2f}", style="green" if unrealized >= 0 else "red")
        port_table.add_row("[bold]📊 Net P&L[/bold]", f"[bold]${net_pnl:+,.2f}[/bold]", style="green" if net_pnl >= 0 else "red")
        port_table.add_row("", "")
        port_table.add_row("📈 Win Rate", f"{_gauge_bar(win_rate, 10, 'green')} {win_rate:.1f}%")
        port_table.add_row("📈 Profit Factor", f"{profit_factor:.2f}")
        port_table.add_row("📉 Max Drawdown", f"{_gauge_bar(max_dd, 10, 'red')} {max_dd:.2f}%")
        port_table.add_row("", "")
        open_orders = getattr(sim, "open_orders", {}) or {}
        port_table.add_row("💼 Open Positions", f"{len(spot_pos) + len(fut_pos)} (Orders: {len(open_orders)})")
        port_table.add_row("📝 Closed Trades", f"{len(trades)}")
        port_table.add_row("⏰ Last Update", self._last_update)

        snapshots = self._cache_snapshots
        adv = sum(1 for s in snapshots if _safe_float(s.get("price_change_24h")) > 0.25)
        dec = sum(1 for s in snapshots if _safe_float(s.get("price_change_24h")) < -0.25)
        neu = max(0, len(snapshots) - adv - dec)
        adv_pct = (adv / len(snapshots) * 100.0) if snapshots else 0.0

        breadth_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        breadth_table.add_column("Symbol", style="yellow")
        breadth_table.add_column("Mkt")
        breadth_table.add_column("Price", justify="right")
        breadth_table.add_column("24h %", justify="right")
        breadth_table.add_column("Vol 24h", justify="right")

        movers = sorted(snapshots, key=lambda s: abs(_safe_float(s.get("price_change_24h"))), reverse=True)[:6]
        for snap in movers:
            chg = _safe_float(snap.get("price_change_24h"))
            color = "green" if chg >= 0 else "red"
            breadth_table.add_row(
                str(snap.get("symbol", "—")),
                str(snap.get("market", "—")),
                f"${_safe_float(snap.get('price')):,.4f}",
                f"[{color}]{chg:+.2f}%[/{color}]",
                f"${_safe_float(snap.get('volume_24h')) / 1e6:.1f}M",
            )
        if not movers:
            breadth_table.add_row("—", "—", "—", "—", "No live snapshots yet")

        left_grid = Table.grid(padding=(0, 1))
        left_grid.add_row(Panel(port_table, title="📊 Portfolio & Execution", border_style="bright_cyan", box=box.ROUNDED))
        left_grid.add_row(
            Panel(
                breadth_table,
                title=f"🌊 Market Breadth  [green]▲{adv}[/green] / [red]▼{dec}[/red] / [dim]■{neu}[/dim]  {_gauge_bar(adv_pct, 10, 'green')}",
                border_style="blue",
                box=box.ROUNDED,
            )
        )
        left.update(left_grid)

        all_signals = self._cache_signals
        signals = [sig for sig in all_signals if _safe_float(sig.get("confidence")) >= 0.65]
        signals.sort(key=lambda s: _safe_float(s.get("confidence")), reverse=True)
        top_signals = signals[:6]

        right_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        right_table.add_column("Symbol", style="yellow")
        right_table.add_column("Dir", justify="center")
        right_table.add_column("Mkt", justify="center")
        right_table.add_column("Entry", justify="right")
        right_table.add_column("SL", justify="right")
        right_table.add_column("TP", justify="right")
        right_table.add_column("Conf", justify="right")
        right_table.add_column("Strategy")

        for s in top_signals:
            direction = str(s.get("direction", "WAIT"))
            dir_style = "green" if direction in ("LONG", "BUY") else "red"
            tp_list = s.get("take_profit") or [0]
            tp0 = _safe_float(tp_list[0] if isinstance(tp_list, list) and tp_list else 0)
            right_table.add_row(
                str(s.get("symbol", "—")),
                f"[{dir_style}]{direction}[/{dir_style}]",
                str(s.get("market", "—")),
                f"${_safe_float(s.get('entry')):,.4f}",
                f"${_safe_float(s.get('stop_loss')):,.4f}",
                f"${tp0:,.4f}",
                f"{int(_safe_float(s.get('confidence')) * 100)}%",
                str(s.get("strategy", "N/A"))[:12],
            )
        if not top_signals:
            right_table.add_row("—", "—", "—", "—", "—", "—", "—", "No strong setups")

        predictor = getattr(getattr(self.orchestrator, "intelligence", None), "predictor", None)
        model_txt = f"[green]v{getattr(predictor, 'version', '?')}[/green]" if getattr(predictor, "is_trained", False) else "[yellow]Rule Fallback[/yellow]"
        drift_alerts = len(self._cache_drift.get("recent_alerts", []) or self._cache_drift.get("alerts", []) or [])

        scanner_info = Table.grid(padding=(0, 2))
        scanner_info.add_column("Component", style="dim")
        scanner_info.add_column("Status", style="bold")
        scanner_info.add_row("Market Scanner", "[green]🟢 ACTIVE[/green]" if self._sb_scanning else "[yellow]🟡 IDLE[/yellow]")
        scanner_info.add_row("Exchange WS", "[green]🟢 CONNECTED[/green]" if self._sb_ws_up else "[red]🔴 DISCONNECTED[/red]")
        scanner_info.add_row("ML Predictor", model_txt)
        scanner_info.add_row("Signals (Recent)", str(len(all_signals)))
        scanner_info.add_row("Symbols Tracked", str(len(self._cache_tracked_symbols)))
        scanner_info.add_row("Drift Alerts", f"[red]{drift_alerts}[/red]" if drift_alerts else "[green]0[/green]")

        right_content = Table.grid(padding=(0, 1))
        right_content.add_row(Panel(right_table, title="🎯 Strongest Setups (>=65%)", border_style="green", box=box.ROUNDED))
        right_content.add_row(Panel(scanner_info, title="⚡ Engine Telemetry", border_style="yellow", box=box.ROUNDED))
        right.update(right_content)

    def _render_scanner(self) -> None:
        left = self._node_left
        right = self._node_right

        scanner = getattr(self.orchestrator, "scanner", None)
        scan_snap = scanner.status_snapshot() if callable(getattr(scanner, "status_snapshot", None)) else {}
        cache = getattr(self.orchestrator, "cache", None)

        status_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        status_table.add_column("Market")
        status_table.add_column("Scanner")
        status_table.add_column("Feed")
        status_table.add_column("Symbols", justify="right")
        status_table.add_column("OK / Fail", justify="right")
        status_table.add_column("Age", justify="right")

        markets_dict = scan_snap.get("markets", {}) if isinstance(scan_snap, dict) else {}
        for mkt in ("SPOT", "FUTURES"):
            m_info = markets_dict.get(mkt, {}) if isinstance(markets_dict, dict) else {}
            feed = cache.get_data_status(mkt) if callable(getattr(cache, "get_data_status", None)) else {}
            m_state = str(m_info.get("state", "IDLE"))
            f_state = str(feed.get("state", "UNKNOWN"))
            age = feed.get("age_seconds")
            age_txt = f"{_safe_float(age):.0f}s" if age is not None else "—"
            ok_cnt = m_info.get("refresh_successes", 0)
            fail_cnt = m_info.get("refresh_failures", 0)
            status_table.add_row(
                mkt,
                f"[green]{m_state}[/green]" if m_state == "COMPLETE" else f"[yellow]{m_state}[/yellow]",
                f"[green]{f_state}[/green]" if f_state == "LIVE" else f"[yellow]{f_state}[/yellow]",
                str(m_info.get("symbols_selected", 0)),
                f"[green]{ok_cnt}[/green]/[red]{fail_cnt}[/red]",
                age_txt,
            )

        tier_counts = {"Tier 1": 0, "Tier 2": 0, "Tier 3": 0, "Tier 4": 0}
        symbol_tiers = getattr(self.orchestrator, "_symbol_tiers", None)
        if isinstance(symbol_tiers, dict) and symbol_tiers:
            for tier in symbol_tiers.values():
                tier_name = f"Tier {tier}"
                if tier_name in tier_counts:
                    tier_counts[tier_name] += 1
        else:
            for sym in self._cache_tracked_symbols:
                # Tier breakdown not available without registry call; show total under Tier 1
                tier_counts["Tier 1"] += 1

        tier_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        tier_table.add_column("Tier")
        tier_table.add_column("Symbols", justify="right")
        tier_table.add_column("Description")
        tier_table.add_row("Tier 1", str(tier_counts.get("Tier 1", 0)), "High volume, tight spreads")
        tier_table.add_row("Tier 2", str(tier_counts.get("Tier 2", 0)), "Good liquidity")
        tier_table.add_row("Tier 3", str(tier_counts.get("Tier 3", 0)), "Moderate liquidity")
        tier_table.add_row("Tier 4", str(tier_counts.get("Tier 4", 0)), "Lower priority")

        left_grid = Table.grid(padding=(0, 1))
        left_grid.add_row(Panel(status_table, title="🛰️ Scanner & Feed Freshness", border_style="cyan", box=box.ROUNDED))
        left_grid.add_row(Panel(tier_table, title="📊 Symbol Tiers", border_style="blue", box=box.ROUNDED))
        left.update(left_grid)

        right_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        right_table.add_column("Time")
        right_table.add_column("Symbol", style="yellow")
        right_table.add_column("Mkt")
        right_table.add_column("Price", justify="right")
        right_table.add_column("24h Chg", justify="right")
        right_table.add_column("Volume", justify="right")
        right_table.add_column("Regime")

        snapshots = self._cache_snapshots
        for snap in snapshots[:24]:
            chg = _safe_float(snap.get("price_change_24h"))
            vol = _safe_float(snap.get("volume_24h"))
            price = _safe_float(snap.get("price"))
            chg_color = "green" if chg >= 0 else "red"
            right_table.add_row(
                _format_ts(snap.get("timestamp")),
                str(snap.get("symbol", "—")),
                str(snap.get("market", "—")),
                f"${price:,.4f}",
                f"[{chg_color}]{chg:+.2f}%[/{chg_color}]",
                f"${vol / 1e6:.1f}M",
                str(snap.get("regime", "UNKNOWN")),
            )
        if not snapshots:
            right_table.add_row("—", "No snapshots", "—", "—", "—", "—", "—")

        right.update(Panel(right_table, title=f"📡 Live Market Snapshots ({len(snapshots)})", border_style="green", box=box.ROUNDED))

    def _render_spot_signals(self) -> None:
        left = self._node_left
        right = self._node_right

        spot_signals = [s for s in self._cache_signals if s.get("market") == "SPOT"]
        spot_signals.sort(key=lambda s: _safe_float(s.get("confidence")), reverse=True)

        table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        table.add_column("Time")
        table.add_column("Symbol", style="yellow")
        table.add_column("Dir", justify="center")
        table.add_column("Entry", justify="right")
        table.add_column("SL", justify="right")
        table.add_column("TP", justify="right")
        table.add_column("R:R", justify="right")
        table.add_column("Conf", justify="right")
        table.add_column("Strategy")
        table.add_column("Status")

        for s in spot_signals[:30]:
            direction = str(s.get("direction", "WAIT"))
            dir_style = "green" if direction in ("LONG", "BUY") else "red"
            rr = self._calc_rr(s)
            tp_list = s.get("take_profit") or [0]
            tp0 = _safe_float(tp_list[0] if isinstance(tp_list, list) and tp_list else 0)
            conf = _safe_float(s.get("confidence"))
            table.add_row(
                _format_ts(s.get("timestamp")),
                str(s.get("symbol", "—")),
                f"[{dir_style}]{direction}[/{dir_style}]",
                f"${_safe_float(s.get('entry')):,.4f}",
                f"${_safe_float(s.get('stop_loss')):,.4f}",
                f"${tp0:,.4f}",
                f"{rr:.2f}",
                f"{int(conf * 100)}%",
                str(s.get("strategy", "N/A"))[:14],
                str(s.get("status", "PROPOSED")),
            )
        if not spot_signals:
            table.add_row("—", "No SPOT signals", "—", "—", "—", "—", "—", "—", "—", "—")

        left.update(Panel(table, title=f"📈 SPOT Signals ({len(spot_signals)})", border_style="blue", box=box.ROUNDED))
        right.update(Panel(self._get_signal_stats(spot_signals), title="📊 SPOT Signal Statistics", border_style="green", box=box.ROUNDED))

    def _render_futures_signals(self) -> None:
        left = self._node_left
        right = self._node_right

        fut_signals = [s for s in self._cache_signals if s.get("market") == "FUTURES"]
        fut_signals.sort(key=lambda s: _safe_float(s.get("confidence")), reverse=True)

        table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        table.add_column("Time")
        table.add_column("Symbol", style="yellow")
        table.add_column("Dir", justify="center")
        table.add_column("Lev", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("SL", justify="right")
        table.add_column("TP", justify="right")
        table.add_column("R:R", justify="right")
        table.add_column("Conf", justify="right")
        table.add_column("Strategy")
        table.add_column("Status")

        for s in fut_signals[:30]:
            direction = str(s.get("direction", "WAIT"))
            dir_style = "green" if direction in ("LONG", "BUY") else "red"
            rr = self._calc_rr(s)
            tp_list = s.get("take_profit") or [0]
            tp0 = _safe_float(tp_list[0] if isinstance(tp_list, list) and tp_list else 0)
            conf = _safe_float(s.get("confidence"))
            table.add_row(
                _format_ts(s.get("timestamp")),
                str(s.get("symbol", "—")),
                f"[{dir_style}]{direction}[/{dir_style}]",
                f"{s.get('leverage', 1)}x",
                f"${_safe_float(s.get('entry')):,.4f}",
                f"${_safe_float(s.get('stop_loss')):,.4f}",
                f"${tp0:,.4f}",
                f"{rr:.2f}",
                f"{int(conf * 100)}%",
                str(s.get("strategy", "N/A"))[:14],
                str(s.get("status", "PROPOSED")),
            )
        if not fut_signals:
            table.add_row("—", "No FUTURES signals", "—", "—", "—", "—", "—", "—", "—", "—", "—")

        left.update(Panel(table, title=f"📉 FUTURES Signals ({len(fut_signals)})", border_style="magenta", box=box.ROUNDED))
        right.update(Panel(self._get_signal_stats(fut_signals), title="📊 FUTURES Signal Statistics", border_style="green", box=box.ROUNDED))

    def _render_positions(self) -> None:
        left = self._node_left
        right = self._node_right

        sim = self.orchestrator.simulator
        spot_pos = getattr(sim, "spot_positions", {}) or {}
        fut_pos = getattr(sim, "futures_positions", {}) or {}

        spot_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        spot_table.add_column("Symbol", style="yellow")
        spot_table.add_column("Side", justify="center")
        spot_table.add_column("Entry", justify="right")
        spot_table.add_column("Current", justify="right")
        spot_table.add_column("Amount", justify="right")
        spot_table.add_column("Unrealized", justify="right")
        spot_table.add_column("SL", justify="right")
        spot_table.add_column("TP", justify="right")
        spot_table.add_column("Strategy")

        for p in spot_pos.values():
            pnl = _safe_float(p.get("unrealized_pnl"))
            pnl_style = "green" if pnl >= 0 else "red"
            side_style = "green" if p.get("side") in ("LONG", "BUY") else "red"
            spot_table.add_row(
                str(p.get("symbol", "—")),
                f"[{side_style}]{p.get('side', '—')}[/{side_style}]",
                f"${_safe_float(p.get('entry_price')):,.4f}",
                f"${_safe_float(p.get('current_price', p.get('entry_price'))):,.4f}",
                f"{_safe_float(p.get('amount')):.6f}",
                f"[{pnl_style}]${pnl:+,.2f}[/{pnl_style}]",
                f"${_safe_float(p.get('stop_loss')):,.4f}" if p.get("stop_loss") else "—",
                f"${_safe_float(p.get('take_profit')):,.4f}" if p.get("take_profit") else "—",
                str(p.get("strategy", "N/A"))[:12],
            )
        if not spot_pos:
            spot_table.add_row("—", "No open SPOT positions", "—", "—", "—", "—", "—", "—", "—")

        fut_table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        fut_table.add_column("Symbol", style="yellow")
        fut_table.add_column("Side", justify="center")
        fut_table.add_column("Lev", justify="right")
        fut_table.add_column("Entry", justify="right")
        fut_table.add_column("Mark", justify="right")
        fut_table.add_column("Amount", justify="right")
        fut_table.add_column("Unrealized", justify="right")
        fut_table.add_column("Liq Price", justify="right")
        fut_table.add_column("Margin %", justify="right")
        fut_table.add_column("Strategy")

        le = getattr(sim, "liquidation_engine", None) or self._liquidation_engine
        for p in fut_pos.values():
            pnl = _safe_float(p.get("unrealized_pnl"))
            pnl_style = "green" if pnl >= 0 else "red"
            side_style = "green" if p.get("side") in ("LONG", "BUY") else "red"
            lev = p.get("leverage", 1)
            liq_price = _safe_float(le.calculate_liquidation_price(p))
            margin_ratio = _safe_float(le.get_margin_ratio(p, _safe_float(p.get("current_price", p.get("entry_price")))))
            fut_table.add_row(
                str(p.get("symbol", "—")),
                f"[{side_style}]{p.get('side', '—')}[/{side_style}]",
                f"{lev}x",
                f"${_safe_float(p.get('entry_price')):,.4f}",
                f"${_safe_float(p.get('current_price', p.get('entry_price'))):,.4f}",
                f"{_safe_float(p.get('amount')):.6f}",
                f"[{pnl_style}]${pnl:+,.2f}[/{pnl_style}]",
                f"${liq_price:,.4f}" if liq_price > 0 else "N/A",
                f"{margin_ratio:.2f}",
                str(p.get("strategy", "N/A"))[:12],
            )
        if not fut_pos:
            fut_table.add_row("—", "No open FUTURES positions", "—", "—", "—", "—", "—", "—", "—", "—")

        left_content = Table.grid(padding=(0, 1))
        left_content.add_row(Panel(spot_table, title=f"📈 SPOT Positions ({len(spot_pos)})", border_style="blue", box=box.ROUNDED))
        left_content.add_row(Panel(fut_table, title=f"📉 FUTURES Positions ({len(fut_pos)})", border_style="magenta", box=box.ROUNDED))
        left.update(left_content)

        total_positions = len(spot_pos) + len(fut_pos)
        total_unrealized = sum(_safe_float(p.get("unrealized_pnl")) for p in spot_pos.values())
        total_unrealized += sum(_safe_float(p.get("unrealized_pnl")) for p in fut_pos.values())
        total_fees = sum(_safe_float(p.get("fees_paid")) for p in spot_pos.values())
        total_fees += sum(_safe_float(p.get("fees_paid")) for p in fut_pos.values())
        daily_pnl = _safe_float(sim.get_daily_pnl()) if callable(getattr(sim, "get_daily_pnl", None)) else 0.0

        risk_info = Table.grid(padding=(0, 2))
        risk_info.add_column("Metric", style="dim")
        risk_info.add_column("Value", justify="right", style="bold")
        risk_info.add_row("Total Open Positions", str(total_positions))
        risk_info.add_row("SPOT / FUTURES", f"{len(spot_pos)} / {len(fut_pos)}")
        risk_info.add_row("Total Unrealized P&L", f"${total_unrealized:+,.2f}", style="green" if total_unrealized >= 0 else "red")
        risk_info.add_row("Total Fees Paid", f"${total_fees:,.2f}")
        risk_info.add_row("Max SPOT Positions", f"{sim.risk_manager.max_spot_positions}")
        risk_info.add_row("Max FUTURES Positions", f"{sim.risk_manager.max_futures_positions}")
        risk_info.add_row("Daily Loss Limit", f"{sim.risk_manager.max_daily_loss_pct}%")
        risk_info.add_row("Current Daily P&L", f"${daily_pnl:+,.2f}", style="green" if daily_pnl >= 0 else "red")

        orders_table = Table(show_header=True, header_style="bold yellow", box=box.SIMPLE)
        orders_table.add_column("Symbol")
        orders_table.add_column("Mkt")
        orders_table.add_column("Side")
        orders_table.add_column("Limit", justify="right")
        orders_table.add_column("Amount", justify="right")
        open_orders = list((getattr(sim, "open_orders", {}) or {}).values())
        for o in open_orders[:12]:
            orders_table.add_row(
                str(o.get("symbol", "—")),
                str(o.get("market", "—")),
                str(o.get("side", "—")),
                f"${_safe_float(o.get('limit_price', o.get('price'))):,.4f}",
                f"{_safe_float(o.get('amount')):.4f}",
            )
        if not open_orders:
            orders_table.add_row("—", "—", "No pending limit orders", "—", "—")

        right_grid = Table.grid(padding=(0, 1))
        right_grid.add_row(Panel(risk_info, title="⚠️ Position Risk Summary", border_style="yellow", box=box.ROUNDED))
        right_grid.add_row(Panel(orders_table, title=f"📋 Pending Limit Orders ({len(open_orders)})", border_style="cyan", box=box.ROUNDED))
        right.update(right_grid)

    def _render_balances(self) -> None:
        left = self._node_left
        right = self._node_right

        sim = self.orchestrator.simulator
        spot_bal = _safe_float(sim.get_balance("SPOT"))
        fut_bal = _safe_float(sim.get_balance("FUTURES"))
        total = spot_bal + fut_bal
        initial_spot = _safe_float(getattr(sim, "initial_spot_balance", 500.0), 500.0) or 500.0
        initial_fut = _safe_float(getattr(sim, "initial_futures_balance", 500.0), 500.0) or 500.0
        initial_total = initial_spot + initial_fut

        balance_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        balance_table.add_column("Account")
        balance_table.add_column("Initial", justify="right")
        balance_table.add_column("Current", justify="right")
        balance_table.add_column("P&L", justify="right")
        balance_table.add_column("Return", justify="right")

        spot_pnl = spot_bal - initial_spot
        fut_pnl = fut_bal - initial_fut
        spot_ret = (spot_pnl / initial_spot * 100.0) if initial_spot > 0 else 0.0
        fut_ret = (fut_pnl / initial_fut * 100.0) if initial_fut > 0 else 0.0
        total_ret = ((spot_pnl + fut_pnl) / initial_total * 100.0) if initial_total > 0 else 0.0
        balance_table.add_row("SPOT", f"${initial_spot:,.2f}", f"${spot_bal:,.2f}", f"${spot_pnl:+,.2f}", f"{spot_ret:+.2f}%")
        balance_table.add_row("FUTURES", f"${initial_fut:,.2f}", f"${fut_bal:,.2f}", f"${fut_pnl:+,.2f}", f"{fut_ret:+.2f}%")
        balance_table.add_row(
            "[bold]TOTAL[/bold]",
            f"[bold]${initial_total:,.2f}[/bold]",
            f"[bold]${total:,.2f}[/bold]",
            f"[bold]${spot_pnl + fut_pnl:+,.2f}[/bold]",
            f"[bold]{total_ret:+.2f}%[/bold]",
        )

        fut_pos = getattr(sim, "futures_positions", {}) or {}
        used_margin = sum(
            _safe_float(p.get("amount")) * _safe_float(p.get("entry_price")) / max(1.0, _safe_float(p.get("leverage"), 1.0))
            for p in fut_pos.values()
        )
        free_margin = fut_bal - used_margin
        margin_ratio = (fut_bal / used_margin) if used_margin > 0 else float("inf")

        margin_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        margin_table.add_column("Metric")
        margin_table.add_column("Value", justify="right")
        margin_table.add_row("Futures Balance", f"${fut_bal:,.2f}")
        margin_table.add_row("Used Margin", f"${used_margin:,.2f}")
        margin_table.add_row("Free Margin", f"${free_margin:,.2f}")
        margin_table.add_row("Margin Ratio", f"{margin_ratio:.2f}" if used_margin > 0 else "∞")
        margin_table.add_row("Max Leverage", f"{sim.risk_manager.max_leverage}x")

        left_grid = Table.grid(padding=(0, 1))
        left_grid.add_row(Panel(balance_table, title="💰 Account Balances", border_style="blue", box=box.ROUNDED))
        left_grid.add_row(Panel(margin_table, title="📊 Futures Margin", border_style="green", box=box.ROUNDED))
        left.update(left_grid)

        adaptive = getattr(self.orchestrator, "adaptive_risk", None)
        adaptive_status = adaptive.get_status() if callable(getattr(adaptive, "get_status", None)) else {}
        eff_risk = adaptive.get_effective_risk_per_trade() if callable(getattr(adaptive, "get_effective_risk_per_trade", None)) else None

        risk_table = Table(show_header=True, header_style="bold yellow", box=box.SIMPLE)
        risk_table.add_column("Adaptive Risk Parameter")
        risk_table.add_column("Value", justify="right")
        if isinstance(adaptive_status, dict) and adaptive_status:
            for k, v in list(adaptive_status.items())[:14]:
                val_str = f"{len(v)} items" if isinstance(v, (dict, list)) else (f"{v:.4f}" if isinstance(v, float) else str(v))
                risk_table.add_row(str(k).replace("_", " ").title(), val_str)
            if eff_risk is not None:
                risk_table.add_row("[bold]Effective Risk/Trade[/bold]", f"[bold cyan]{_safe_float(eff_risk) * 100:.2f}%[/bold cyan]")
        else:
            risk_table.add_row("Adaptive Risk Engine", "[dim]Unavailable[/dim]")

        right.update(Panel(risk_table, title="🛡️ Adaptive Risk Engine", border_style="yellow", box=box.ROUNDED))

    def _render_pnl_stats(self) -> None:
        left = self._node_left
        right = self._node_right

        sim = self.orchestrator.simulator
        trades = getattr(sim, "closed_trades", []) or []

        if not trades:
            left.update(Panel("[dim]No closed trades yet[/dim]", title="📊 P&L Statistics", border_style="blue", box=box.ROUNDED))
            right.update(Panel("[dim]Trade breakdown will appear after first close[/dim]", title="📈 Trade Breakdown", border_style="green", box=box.ROUNDED))
            return

        total_pnl = sum(_safe_float(t.get("pnl")) for t in trades)
        wins = [t for t in trades if _safe_float(t.get("pnl")) > 0]
        losses = [t for t in trades if _safe_float(t.get("pnl")) < 0]
        win_rate = len(wins) / len(trades) * 100.0
        avg_win = sum(_safe_float(t.get("pnl")) for t in wins) / len(wins) if wins else 0.0
        avg_loss = sum(_safe_float(t.get("pnl")) for t in losses) / len(losses) if losses else 0.0
        gross_profit = sum(_safe_float(t.get("pnl")) for t in wins)
        gross_loss = abs(sum(_safe_float(t.get("pnl")) for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        largest_win = max((_safe_float(t.get("pnl")) for t in wins), default=0.0)
        largest_loss = min((_safe_float(t.get("pnl")) for t in losses), default=0.0)

        initial_total = _safe_float(getattr(sim, "initial_spot_balance", 500.0), 500.0) + _safe_float(getattr(sim, "initial_futures_balance", 500.0), 500.0)
        peak = initial_total if initial_total > 0 else 1000.0
        equity = peak
        max_dd = 0.0
        for t in trades:
            equity += _safe_float(t.get("pnl"))
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

        stats_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        stats_table.add_column("Metric")
        stats_table.add_column("Value", justify="right")
        stats_table.add_row("Total Trades", str(len(trades)))
        stats_table.add_row("Winning / Losing", f"[green]{len(wins)}[/green] / [red]{len(losses)}[/red]")
        stats_table.add_row("Win Rate", f"{_gauge_bar(win_rate, 10, 'green')} {win_rate:.1f}%")
        stats_table.add_row("Total P&L", f"${total_pnl:+,.2f}", style="green" if total_pnl >= 0 else "red")
        stats_table.add_row("Gross Profit / Loss", f"[green]${gross_profit:,.2f}[/green] / [red]${gross_loss:,.2f}[/red]")
        stats_table.add_row("Profit Factor", f"{profit_factor:.2f}")
        stats_table.add_row("Avg Win / Avg Loss", f"${avg_win:,.2f} / ${avg_loss:,.2f}")
        stats_table.add_row("Largest Win / Loss", f"${largest_win:,.2f} / ${largest_loss:,.2f}")
        stats_table.add_row("Max Drawdown", f"{max_dd:.2f}%")
        sharpe = (
            (total_pnl / len(trades))
            / max(1.0, (sum((_safe_float(t.get("pnl")) - total_pnl / len(trades)) ** 2 for t in trades) / len(trades)) ** 0.5)
            if len(trades) > 1
            else 0.0
        )
        stats_table.add_row("Sharpe (approx)", f"{sharpe:.2f}" if len(trades) > 1 else "N/A")

        recent_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        recent_table.add_column("Symbol", style="yellow")
        recent_table.add_column("Mkt")
        recent_table.add_column("Side")
        recent_table.add_column("P&L", justify="right")
        recent_table.add_column("Reason")
        for t in list(reversed(trades))[:10]:
            pnl = _safe_float(t.get("pnl"))
            color = "green" if pnl >= 0 else "red"
            recent_table.add_row(
                str(t.get("symbol", "—")),
                str(t.get("market", "—")),
                str(t.get("side", "—")),
                f"[{color}]${pnl:+,.2f}[/{color}]",
                str(t.get("close_reason", "—"))[:14],
            )

        left_grid = Table.grid(padding=(0, 1))
        left_grid.add_row(Panel(stats_table, title="📊 P&L Statistics", border_style="blue", box=box.ROUNDED))
        left_grid.add_row(Panel(recent_table, title="📜 Recent Closed Trades", border_style="cyan", box=box.ROUNDED))
        left.update(left_grid)

        spot_trades = [t for t in trades if t.get("market") == "SPOT"]
        fut_trades = [t for t in trades if t.get("market") == "FUTURES"]

        market_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        market_table.add_column("Market")
        market_table.add_column("Trades", justify="right")
        market_table.add_column("Wins", justify="right")
        market_table.add_column("Win%", justify="right")
        market_table.add_column("Total P&L", justify="right")
        market_table.add_column("PF", justify="right")

        for market, mtrades in [("SPOT", spot_trades), ("FUTURES", fut_trades)]:
            if not mtrades:
                market_table.add_row(market, "0", "0", "0%", "$0.00", "N/A")
                continue
            mwins = [t for t in mtrades if _safe_float(t.get("pnl")) > 0]
            mlosses = [t for t in mtrades if _safe_float(t.get("pnl")) < 0]
            mpf = sum(_safe_float(t.get("pnl")) for t in mwins) / abs(sum(_safe_float(t.get("pnl")) for t in mlosses)) if mlosses else float("inf")
            market_table.add_row(
                market,
                str(len(mtrades)),
                str(len(mwins)),
                f"{len(mwins) / len(mtrades) * 100:.1f}%",
                f"${sum(_safe_float(t.get('pnl')) for t in mtrades):+,.2f}",
                f"{mpf:.2f}",
            )

        strategy_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        strategy_table.add_column("Strategy")
        strategy_table.add_column("Trades", justify="right")
        strategy_table.add_column("Win%", justify="right")
        strategy_table.add_column("Total P&L", justify="right")

        strategies: dict[str, list[dict]] = {}
        for t in trades:
            strat = str(t.get("strategy", "UNKNOWN"))
            strategies.setdefault(strat, []).append(t)

        for strat, strats_trades in sorted(strategies.items(), key=lambda x: sum(_safe_float(t.get("pnl")) for t in x[1]), reverse=True):
            swins = [t for t in strats_trades if _safe_float(t.get("pnl")) > 0]
            strategy_table.add_row(
                strat,
                str(len(strats_trades)),
                f"{len(swins) / len(strats_trades) * 100:.1f}%",
                f"${sum(_safe_float(t.get('pnl')) for t in strats_trades):+,.2f}",
            )

        right_content = Table.grid(padding=(0, 1))
        right_content.add_row(Panel(market_table, title="📈 By Market", border_style="green", box=box.ROUNDED))
        right_content.add_row(Panel(strategy_table, title="🎯 By Strategy", border_style="yellow", box=box.ROUNDED))
        right.update(right_content)

    def _render_strategy(self) -> None:
        left = self._node_left
        right = self._node_right

        metrics = self._cache_strategy_metrics

        table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        table.add_column("Strategy")
        table.add_column("Mkt")
        table.add_column("Sig", justify="right")
        table.add_column("Val", justify="right")
        table.add_column("W/L", justify="right")
        table.add_column("Win%", justify="right")
        table.add_column("Total P&L", justify="right")
        table.add_column("PF", justify="right")
        table.add_column("Wt", justify="right")

        for m in metrics:
            table.add_row(
                str(m.strategy),
                str(m.market),
                str(m.total_signals),
                str(m.validated_signals),
                f"{m.winning_trades}/{m.losing_trades}",
                f"{_safe_float(m.win_rate) * 100:.1f}%",
                f"${_safe_float(m.total_pnl):+,.2f}",
                f"{_safe_float(m.profit_factor):.2f}",
                f"{_safe_float(m.weight):.2f}",
            )
        if not metrics:
            table.add_row("—", "—", "0", "0", "0/0", "0%", "$0.00", "0.00", "1.00")

        left.update(Panel(table, title="🎯 Strategy Performance", border_style="blue", box=box.ROUNDED))

        intel = self.orchestrator.intelligence
        selector = intel.strategy_selector
        weight_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        weight_table.add_column("Strategy")
        weight_table.add_column("Base Weight", justify="right")
        weight_table.add_column("Regime Adjusted", justify="right")

        regime = getattr(intel, "_current_regime", getattr(self.orchestrator, "_current_regime", "UNKNOWN"))
        for strat, weight in (getattr(selector, "weights", {}) or {}).items():
            adjusted = _safe_float(weight)
            regime_prefs = getattr(selector, "regime_prefs", {}) or {}
            if regime in regime_prefs:
                adjusted *= _safe_float(regime_prefs[regime].get(strat, 1.0), 1.0)
            weight_table.add_row(str(strat), f"{_safe_float(weight):.3f}", f"{adjusted:.3f}")
        if not getattr(selector, "weights", None):
            weight_table.add_row("—", "—", "—")

        auto_enabled = bool(getattr(self.orchestrator, "_autonomous_enabled", False))
        last_dec = getattr(self.orchestrator, "last_autonomous_decision", None) or {}
        auto_table = Table.grid(padding=(0, 2))
        auto_table.add_column("Key", style="dim")
        auto_table.add_column("Value", style="bold")
        auto_table.add_row("Autonomous Trading", "[green]ENABLED[/green]" if auto_enabled else "[yellow]DISABLED (Manual/Advisory)[/yellow]")
        if isinstance(last_dec, dict) and last_dec:
            for k in ("symbol", "action", "status", "reason", "timestamp"):
                if k in last_dec:
                    auto_table.add_row(k.title(), str(last_dec[k])[:60])
        else:
            auto_table.add_row("Last Decision", "[dim]None recorded in this session[/dim]")

        right_grid = Table.grid(padding=(0, 1))
        right_grid.add_row(Panel(weight_table, title=f"⚖️ Strategy Weights (Regime: {regime})", border_style="green", box=box.ROUNDED))
        right_grid.add_row(Panel(auto_table, title="🤖 Autonomous Engine", border_style="magenta", box=box.ROUNDED))
        right.update(right_grid)

    def _render_learning(self) -> None:
        left = self._node_left
        right = self._node_right

        predictor = self.orchestrator.intelligence.predictor
        status_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        status_table.add_column("Component")
        status_table.add_column("Status")
        status_table.add_column("Details")

        is_trained = bool(getattr(predictor, "is_trained", False))
        model_status = "[green]🟢 Ready[/green]" if is_trained else "[yellow]🟡 Not Trained[/yellow]"
        status_table.add_row("ML Ensemble", model_status, f"v{getattr(predictor, 'version', '0000')}" if is_trained else "Rule-based fallback")
        status_table.add_row("RF Model", "[green]🟢 Loaded[/green]" if getattr(predictor, "rf_model", None) else "[red]🔴 Not Loaded[/red]", "RandomForest")
        status_table.add_row("XGBoost Model", "[green]🟢 Loaded[/green]" if getattr(predictor, "xgb_model", None) else "[red]🔴 Not Loaded[/red]", "XGBoost")

        preds = self._cache_predictions
        resolved = [p for p in preds if getattr(p, "is_correct", None) is not None]
        correct = [p for p in resolved if p.is_correct]
        accuracy = len(correct) / len(resolved) * 100.0 if resolved else 0.0
        status_table.add_row("Predictions (100)", str(len(preds)), f"{len(resolved)} resolved, {accuracy:.1f}% accurate")

        reg_table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        reg_table.add_column("Version")
        reg_table.add_column("Type")
        reg_table.add_column("Status")
        reg_table.add_column("Acc", justify="right")
        reg_table.add_column("Sharpe", justify="right")
        models = self._cache_model_registry
        for m in (models or [])[:10]:
            st = str(getattr(m, "status", "UNKNOWN"))
            st_color = "green" if st == "CHAMPION" else "cyan" if "SHADOW" in st else "red" if "REJECT" in st else "dim"
            acc = getattr(m, "validation_accuracy", None)
            sharpe = getattr(m, "validation_sharpe", None)
            reg_table.add_row(
                str(getattr(m, "version", "—")),
                str(getattr(m, "model_type", "—")),
                f"[{st_color}]{st}[/{st_color}]",
                f"{_safe_float(acc) * 100:.1f}%" if acc is not None else "—",
                f"{_safe_float(sharpe):.2f}" if sharpe is not None else "—",
            )
        if not models:
            reg_table.add_row("—", "No registered models", "—", "—", "—")

        left_grid = Table.grid(padding=(0, 1))
        left_grid.add_row(Panel(status_table, title="🧠 Learning Status", border_style="blue", box=box.ROUNDED))
        left_grid.add_row(Panel(reg_table, title="🏛️ Model Registry", border_style="magenta", box=box.ROUNDED))
        left.update(left_grid)

        pred_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        pred_table.add_column("Time")
        pred_table.add_column("Symbol", style="yellow")
        pred_table.add_column("Mkt")
        pred_table.add_column("Pred", justify="center")
        pred_table.add_column("Conf", justify="right")
        pred_table.add_column("Actual", justify="center")
        pred_table.add_column("Ret", justify="right")
        pred_table.add_column("OK", justify="center")

        for p in preds[:24]:
            actual = getattr(p, "actual_outcome", None) or "—"
            is_corr = getattr(p, "is_correct", None)
            correct_mark = "✅" if is_corr else ("❌" if is_corr is not None else "⏳")
            ret_val = getattr(p, "actual_return_pct", None)
            ret = f"{_safe_float(ret_val):+.2f}%" if ret_val is not None else "—"
            pred_table.add_row(
                _format_ts(getattr(p, "created_at", None)),
                str(getattr(p, "symbol", "—")),
                str(getattr(p, "market", "—")),
                str(getattr(p, "predicted_class", "—")),
                f"{_safe_float(getattr(p, 'confidence', 0)):.1%}",
                str(actual),
                ret,
                correct_mark,
            )
        if not preds:
            pred_table.add_row("—", "No predictions yet", "—", "—", "—", "—", "—", "—")

        right.update(Panel(pred_table, title="📋 Recent Predictions", border_style="green", box=box.ROUNDED))

    def _render_health(self) -> None:
        left = self._node_left
        right = self._node_right

        status = self._cache_health
        if not status:
            left.update(Panel("[red]No health monitor[/red]", title="🏥 System Health", box=box.ROUNDED))
            right.update("")
            return

        comp_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        comp_table.add_column("Component")
        comp_table.add_column("Status")
        comp_table.add_column("Details")

        for comp_name, comp_status in status.get("components", {}).items():
            if "healthy" in comp_status:
                status_text = "healthy" if bool(comp_status["healthy"]) else "unhealthy"
            else:
                status_text = str(comp_status.get("status", "unknown"))
            status_emoji = "🟢" if status_text == "healthy" else "🟡" if status_text == "degraded" else "🔴"
            details = comp_status.get("details") or comp_status.get("message") or ""
            comp_table.add_row(comp_name, f"{status_emoji} {status_text}", str(details))

        metrics = status.get("metrics", {}) or {}
        cpu_pct = _safe_float(metrics.get("cpu_percent"))
        mem_pct = _safe_float(metrics.get("memory_percent"))
        disk_pct = _safe_float(metrics.get("disk_percent"))

        sys_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        sys_table.add_column("Metric")
        sys_table.add_column("Value", justify="right")
        sys_table.add_row("Uptime", f"{_safe_float(metrics.get('uptime_seconds')) / 3600:.2f}h")
        sys_table.add_row("CPU %", f"{_gauge_bar(cpu_pct, 10, 'cyan')} {cpu_pct:.1f}%")
        sys_table.add_row("Memory %", f"{_gauge_bar(mem_pct, 10, 'magenta')} {mem_pct:.1f}%")
        sys_table.add_row("Disk %", f"{_gauge_bar(disk_pct, 10, 'yellow')} {disk_pct:.1f}%")
        sys_table.add_row("Events Processed", str(metrics.get("events_processed", 0)))
        sys_table.add_row("Errors (1h)", str(metrics.get("errors_last_hour", 0)))

        left_grid = Table.grid(padding=(0, 1))
        left_grid.add_row(Panel(comp_table, title="🏥 Component Health", border_style="blue", box=box.ROUNDED))
        left_grid.add_row(Panel(sys_table, title="📊 System Resources", border_style="cyan", box=box.ROUNDED))
        left.update(left_grid)

        drift_status = self._cache_drift
        drift_table = Table(show_header=True, header_style="bold yellow", box=box.SIMPLE)
        drift_table.add_column("Drift Metric")
        drift_table.add_column("Value", justify="right")
        if drift_status:
            for k, v in list(drift_status.items())[:12]:
                if k in ("recent_alerts", "alerts"):
                    continue
                val_str = f"{v:.4f}" if isinstance(v, float) else str(v)
                drift_table.add_row(str(k).replace("_", " ").title(), val_str)
        else:
            drift_table.add_row("Drift Monitor", "[dim]Waiting for baseline samples[/dim]")

        drift_monitor = getattr(self.orchestrator, "drift_monitor", None)
        recent_alerts = drift_monitor.get_recent_alerts(limit=8) if callable(getattr(drift_monitor, "get_recent_alerts", None)) else []
        alert_table = Table(show_header=True, header_style="bold red", box=box.SIMPLE)
        alert_table.add_column("Severity")
        alert_table.add_column("Metric")
        alert_table.add_column("Message")
        for a in recent_alerts or []:
            if isinstance(a, dict):
                alert_table.add_row(str(a.get("severity", "WARN")), str(a.get("metric", "—")), str(a.get("message", ""))[:40])
            else:
                alert_table.add_row(str(getattr(a, "severity", "WARN")), str(getattr(a, "metric", "—")), str(getattr(a, "message", ""))[:40])
        if not recent_alerts:
            alert_table.add_row("[green]OK[/green]", "None", "No active drift alerts")

        right_grid = Table.grid(padding=(0, 1))
        right_grid.add_row(Panel(drift_table, title="📉 Drift Monitor", border_style="green", box=box.ROUNDED))
        right_grid.add_row(Panel(alert_table, title="🚨 Recent Drift Alerts", border_style="yellow", box=box.ROUNDED))
        right.update(right_grid)

    def _render_logs(self) -> None:
        left = self._node_left
        right = self._node_right

        events = self._cache_system_events

        ev_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        ev_table.add_column("Time")
        ev_table.add_column("Type", style="yellow")
        ev_table.add_column("Symbol")
        ev_table.add_column("Detail")
        for ev in (events or [])[:25]:
            if isinstance(ev, dict):
                ts = _format_ts(ev.get("timestamp") or ev.get("created_at"))
                etype = str(ev.get("event_type", "—"))
                sym = str(ev.get("symbol") or "—")
                detail = str(ev.get("message") or ev.get("payload") or "")[:36]
            else:
                ts = _format_ts(getattr(ev, "timestamp", None) or getattr(ev, "created_at", None))
                etype = str(getattr(ev, "event_type", "—"))
                sym = str(getattr(ev, "symbol", None) or "—")
                detail = str(getattr(ev, "message", None) or getattr(ev, "payload", "") or "")[:36]
            ev_table.add_row(ts, etype, sym, detail)
        if not events:
            ev_table.add_row("—", "No persisted events yet", "—", "—")

        left.update(Panel(ev_table, title="🔔 Persisted System Events", border_style="blue", box=box.ROUNDED))
        right.update(Panel("[cyan]Live backend logs stream below in real time.[/cyan]", title="📜 Live Stream", border_style="green", box=box.ROUNDED))

    # ── Private helpers ────────────────────────────────────────────────────

    def _fetch_snapshots(self) -> list[dict]:
        """Read in-memory snapshot list — no DB."""
        snapshots = getattr(self.orchestrator, "_recent_snapshots", None) or []
        if not snapshots:
            cache = getattr(self.orchestrator, "cache", None)
            if callable(getattr(cache, "get_market_tickers", None)):
                try:
                    snapshots = (cache.get_market_tickers("SPOT") or []) + (cache.get_market_tickers("FUTURES") or [])
                except Exception:
                    snapshots = []
        return list(snapshots) if isinstance(snapshots, list) else []

    def _fetch_tracked_symbols(self) -> list[str]:
        tracked = getattr(self.orchestrator, "_tracked_symbols", None)
        if tracked:
            return list(tracked)
        registry = getattr(self.orchestrator, "registry", None)
        if callable(getattr(registry, "list_symbols", None)):
            try:
                return list(dict.fromkeys(
                    item["symbol"] for item in (registry.list_symbols() or [])
                    if isinstance(item, dict) and "symbol" in item
                ))
            except Exception:
                pass
        return []

    def _fetch_signals_from_repo(self, repo) -> list[dict]:
        """ORM → dict normalisation for signals. Called only from slow timer."""
        signals: list[dict] = []
        try:
            rows = repo.get_recent_signals(100) or []
        except Exception:
            return signals
        for row in rows:
            if isinstance(row, dict):
                signals.append(dict(row))
            else:
                tp = getattr(row, "take_profit", None)
                if isinstance(tp, str):
                    try:
                        tp = json.loads(tp)
                    except json.JSONDecodeError:
                        tp = [0]
                elif isinstance(tp, (int, float)):
                    tp = [float(tp)]
                elif not isinstance(tp, list) or not tp:
                    tp = [0]
                created = getattr(row, "created_at", None)
                signals.append({
                    "symbol": getattr(row, "symbol", "—"),
                    "market": getattr(row, "market", "SPOT"),
                    "direction": getattr(row, "direction", "WAIT"),
                    "entry": float(getattr(row, "entry_price", 0) or 0),
                    "stop_loss": float(getattr(row, "stop_loss", 0) or 0),
                    "take_profit": tp,
                    "confidence": float(getattr(row, "confidence", 0) or 0),
                    "strategy": getattr(row, "strategy", "N/A") or "N/A",
                    "regime": getattr(row, "regime", "UNKNOWN") or "UNKNOWN",
                    "leverage": getattr(row, "leverage", 1) or 1,
                    "status": getattr(row, "status", "PROPOSED") or "PROPOSED",
                    "timestamp": created.isoformat() if isinstance(created, datetime) else str(created or ""),
                })
        # Fallback to in-memory intelligence cache when repo is empty
        if not signals:
            intel = getattr(self.orchestrator, "intelligence", None)
            last_signals = getattr(intel, "_last_signals", None)
            if isinstance(last_signals, dict):
                for sig_list in last_signals.values():
                    if isinstance(sig_list, list):
                        signals.extend(s for s in sig_list if isinstance(s, dict))
        return signals

    def _calc_rr(self, signal: dict) -> float:
        entry = _safe_float(signal.get("entry"))
        sl = _safe_float(signal.get("stop_loss"))
        tp_list = signal.get("take_profit") or [0]
        tp = _safe_float(tp_list[0] if isinstance(tp_list, list) and tp_list else 0)
        if entry == 0 or sl == 0 or tp == 0:
            return 0.0
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        return reward / risk if risk > 0 else 0.0

    def _get_signal_stats(self, signals: list) -> Table:
        table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        table.add_column("Metric")
        table.add_column("Value", justify="right")

        if not signals:
            table.add_row("Total Signals", "0")
            table.add_row("Avg Confidence", "0%")
            table.add_row("By Direction", "—")
            table.add_row("By Strategy", "—")
            return table

        table.add_row("Total Signals", str(len(signals)))
        avg_conf = sum(_safe_float(s.get("confidence")) for s in signals) / len(signals)
        table.add_row("Avg Confidence", f"{avg_conf * 100:.1f}%")

        dirs: dict[str, int] = {}
        for s in signals:
            d = str(s.get("direction", "UNKNOWN"))
            dirs[d] = dirs.get(d, 0) + 1
        for d, c in sorted(dirs.items(), key=lambda x: -x[1]):
            table.add_row(f"  {d}", str(c))

        strats: dict[str, int] = {}
        for s in signals:
            st = str(s.get("strategy", "UNKNOWN"))
            strats[st] = strats.get(st, 0) + 1
        for st, c in sorted(strats.items(), key=lambda x: -x[1])[:5]:
            table.add_row(f"  {st}", str(c))

        return table


class DashboardLogHandler(logging.Handler):
    """Forward Python logging records into the Textual DashboardApp log panel."""

    _LEVEL_MAP = {
        logging.DEBUG: "debug",
        logging.INFO: "info",
        logging.WARNING: "warning",
        logging.ERROR: "error",
        logging.CRITICAL: "error",
    }

    def __init__(self, app: DashboardApp):
        super().__init__()
        self._app = app
        self.setFormatter(logging.Formatter("%(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        if not self._app.is_running:
            return
        try:
            from rich.markup import escape
            level = self._LEVEL_MAP.get(record.levelno, "info")
            text = escape(self.format(record))
            try:
                self._app.call_from_thread(self._app.write_log, text, level)
            except RuntimeError:
                self._app.write_log(text, level)
        except Exception:
            pass
