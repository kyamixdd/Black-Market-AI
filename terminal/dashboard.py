"""Textual-based professional terminal dashboard for BlackMarket AI."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

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
    Log,
    Static,
    TabPane,
    Tabs,
)

logger = logging.getLogger(__name__)


class DashboardApp(App):
    """Professional terminal dashboard with 11 views."""

    CSS = """
    Screen { layout: vertical; background: $surface; }
    Header { dock: top; height: 3; background: $primary; color: $text; }
    Footer { dock: bottom; height: 1; background: $primary; color: $text; }
    Tabs { dock: top; height: 1; background: $boost; }
    TabPane { layout: vertical; }

    /* Main layout */
    #main { layout: horizontal; height: 1fr; }
    #left { width: 55%; layout: vertical; height: 1fr; }
    #right { width: 45%; layout: vertical; height: 1fr; }

    /* Panels */
    .panel { height: 1fr; border: solid $primary; margin: 1; padding: 1; background: $surface; }
    .panel-title { text-style: bold; color: $accent; margin-bottom: 1; }
    .metric-row { layout: horizontal; height: 1; margin: 0 1; }
    .metric-label { width: 40%; color: $text-muted; }
    .metric-value { width: 60%; text-align: right; text-style: bold; }
    .metric-positive { color: $success; }
    .metric-negative { color: $error; }
    .metric-neutral { color: $warning; }

    /* DataTables */
    DataTable { height: 1fr; border: solid $primary; margin: 1; }
    DataTable > .datatable--header { background: $boost; color: $text; text-style: bold; }
    DataTable > .datatable--cursor { background: $accent; color: $text; }

    /* Log panel */
    Log { height: 1fr; border: solid $primary; margin: 1; background: $surface; }

    /* Status indicators */
    .status-ok { color: $success; }
    .status-warn { color: $warning; }
    .status-error { color: $error; }

    /* Scanner status */
    .scanner-active { color: $success; text-style: bold; }
    .scanner-idle { color: $text-muted; }

    /* Model status */
    .model-ready { color: $success; }
    .model-training { color: $warning; }
    .model-not-ready { color: $text-muted; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("r", "refresh", "Refresh"),
        Binding("space", "toggle_pause", "Pause/Resume"),
        Binding("1", "tab_overview", "Overview"),
        Binding("2", "tab_scanner", "Scanner"),
        Binding("3", "tab_spot", "Spot Signals"),
        Binding("4", "tab_futures", "Futures Signals"),
        Binding("5", "tab_positions", "Positions"),
        Binding("6", "tab_balances", "Balances"),
        Binding("7", "tab_pnl", "P&L Stats"),
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

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Tabs(
            TabPane("📊 Overview", id="tab_overview"),
            TabPane("🔍 Scanner", id="tab_scanner"),
            TabPane("📈 Spot Signals", id="tab_spot"),
            TabPane("📉 Futures Signals", id="tab_futures"),
            TabPane("💼 Positions", id="tab_positions"),
            TabPane("💰 Balances", id="tab_balances"),
            TabPane("📊 P&L Stats", id="tab_pnl"),
            TabPane("🎯 Strategy", id="tab_strategy"),
            TabPane("🧠 Learning", id="tab_learning"),
            TabPane("🏥 Health", id="tab_health"),
            TabPane("📜 Logs", id="tab_logs"),
            id="main_tabs"
        )
        with Container(id="main"):
            with Vertical(id="left"):
                yield Static("", id="left_content")
            with Vertical(id="right"):
                yield Static("", id="right_content")
                yield Log(id="log_panel", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_timer = self.set_interval(2.0, self.refresh_ui)
        self._populate_tabs()
        self.log_panel = self.query_one("#log_panel", Log)
        self.log("🚀 BlackMarket AI Dashboard started")
        self.log(f"📡 Connected to orchestrator: {self.orchestrator is not None}")

    def on_unmount(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()

    def _populate_tabs(self) -> None:
        """Initialize tab content placeholders."""
        tabs = self.query_one("#main_tabs", Tabs)
        # Content will be dynamically updated in refresh_ui based on active tab

    def log(self, message: str, level: str = "info") -> None:
        """Add a log entry with timestamp."""
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        colors = {"info": "cyan", "warning": "yellow", "error": "red", "success": "green", "debug": "dim"}
        color = colors.get(level, "white")
        self.log_panel.write_line(f"[{color}]{timestamp}[/{color}] {message}")

    async def action_quit(self) -> None:
        self.log("🛑 Shutting down dashboard...")
        if self.orchestrator:
            await self.orchestrator.stop()
        await self.quit()

    async def action_refresh(self) -> None:
        self.refresh_ui()
        self.log("🔄 Manual refresh triggered")

    async def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        status = "PAUSED" if self._paused else "RESUMED"
        self.log(f"⏸️ Dashboard {status}")

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
        tabs = self.query_one("#main_tabs", Tabs)
        tabs.active = tab_id
        self.refresh_ui()

    def refresh_ui(self) -> None:
        """Main UI refresh - updates content based on active tab."""
        if self._paused:
            return

        if not self.orchestrator:
            self._show_no_orchestrator()
            return

        try:
            tabs = self.query_one("#main_tabs", Tabs)
            active = tabs.active

            # Route to appropriate render method
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
            self.log(f"❌ Refresh error: {exc}", "error")

    def _show_no_orchestrator(self) -> None:
        left = self.query_one("#left_content", Static)
        right = self.query_one("#right_content", Static)
        left.update(Panel("[red]No orchestrator connected[/red]", title="⚠️ Disconnected"))
        right.update("")

    # ===== Render Methods =====

    def _render_overview(self) -> None:
        """Main dashboard overview."""
        left = self.query_one("#left_content", Static)
        right = self.query_one("#right_content", Static)

        sim = self.orchestrator.simulator
        spot_bal = sim.get_balance("SPOT")
        fut_bal = sim.get_balance("FUTURES")
        total = spot_bal + fut_bal

        # Calculate P&L
        realized = sum(t.get("pnl", 0) for t in sim.closed_trades)
        unrealized = sum(p.get("unrealized_pnl", 0) for p in sim.spot_positions.values())
        unrealized += sum(p.get("unrealized_pnl", 0) for p in sim.futures_positions.values())

        # Win rate
        trades = sim.closed_trades
        wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
        win_rate = (wins / len(trades) * 100) if trades else 0

        # Profit factor
        gross_profit = sum(t["pnl"] for t in trades if t.get("pnl", 0) > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t.get("pnl", 0) < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Max drawdown
        peak = 1000.0
        equity = 1000.0
        max_dd = 0.0
        for t in trades:
            equity += t.get("pnl", 0)
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)

        left_content = Table.grid(padding=(0, 2))
        left_content.add_column("Metric", style="dim")
        left_content.add_column("Value", justify="right", style="bold")
        left_content.add_row("💰 Spot Balance", f"${spot_bal:,.2f}")
        left_content.add_row("💰 Futures Balance", f"${fut_bal:,.2f}")
        left_content.add_row("[bold]💰 Total Balance[/bold]", f"[bold]${total:,.2f}[/bold]")
        left_content.add_row("", "")
        left_content.add_row("🟢 Realized P&L", f"${realized:+,.2f}", style="green" if realized >= 0 else "red")
        left_content.add_row("🔵 Unrealized P&L", f"${unrealized:+,.2f}", style="green" if unrealized >= 0 else "red")
        left_content.add_row("[bold]📊 Net P&L[/bold]", f"[bold]${realized + unrealized:+,.2f}[/bold]")
        left_content.add_row("", "")
        left_content.add_row("📈 Win Rate", f"{win_rate:.1f}%")
        left_content.add_row("📈 Profit Factor", f"{profit_factor:.2f}")
        left_content.add_row("📉 Max Drawdown", f"{max_dd:.2f}%")
        left_content.add_row("", "")
        left_content.add_row("💼 Open Positions", f"{len(sim.spot_positions) + len(sim.futures_positions)}")
        left_content.add_row("📝 Total Trades", f"{len(trades)}")
        left_content.add_row("⏰ Last Update", self._last_update)

        left.update(Panel(left_content, title="📊 Portfolio Overview", border_style="blue"))

        # Right: Strongest setups + scanner status
        intel = self.orchestrator.intelligence
        signals = []
        if hasattr(intel, '_last_signals'):
            for sig_list in intel._last_signals.values():
                for sig in sig_list:
                    if sig.get("confidence", 0) >= 0.65:
                        signals.append(sig)

        signals.sort(key=lambda s: s.get("confidence", 0), reverse=True)
        top_signals = signals[:5]

        right_table = Table(show_header=True, header_style="bold cyan")
        right_table.add_column("Symbol", style="yellow")
        right_table.add_column("Dir", justify="center")
        right_table.add_column("Market", justify="center")
        right_table.add_column("Entry", justify="right")
        right_table.add_column("SL", justify="right")
        right_table.add_column("TP", justify="right")
        right_table.add_column("Conf", justify="right")
        right_table.add_column("Strategy")

        for s in top_signals:
            dir_style = "green" if s["direction"] in ("LONG", "BUY") else "red"
            right_table.add_row(
                s["symbol"],
                f"[{dir_style}]{s['direction']}[/{dir_style}]",
                s["market"],
                f"${s['entry']:,.4f}",
                f"${s.get('stop_loss', 0):,.4f}",
                f"${s.get('take_profit', [0])[0]:,.4f}",
                f"{int(s.get('confidence', 0)*100)}%",
                s.get("strategy", "N/A")[:12]
            )

        if not top_signals:
            right_table.add_row("—", "—", "—", "—", "—", "—", "—", "No strong setups")

        # Scanner status
        scanner_status = "🟢 ACTIVE" if getattr(self.orchestrator, '_scanning', False) else "🟡 IDLE"
        ws_status = "🟢 CONNECTED" if getattr(self.orchestrator, '_ws_connected', False) else "🔴 DISCONNECTED"

        scanner_info = Table.grid(padding=(0, 1))
        scanner_info.add_column("Component")
        scanner_info.add_column("Status")
        scanner_info.add_row("Market Scanner", scanner_status)
        scanner_info.add_row("WebSocket", ws_status)
        scanner_info.add_row("Signals Today", str(len([s for sigs in intel._last_signals.values() for s in sigs])))
        scanner_info.add_row("Symbols Tracked", str(len(getattr(self.orchestrator, '_tracked_symbols', []))))

        right_content = Table.grid(padding=(0, 1))
        right_content.add_row(Panel(right_table, title="🎯 Strongest Setups", border_style="green"))
        right_content.add_row("")
        right_content.add_row(Panel(scanner_info, title="🔍 Scanner Status", border_style="yellow"))

        right.update(Panel(right_content, title="📈 Market Intelligence", border_style="green"))

    def _render_scanner(self) -> None:
        """Market scanner view."""
        left = self.query_one("#left_content", Static)
        right = self.query_one("#right_content", Static)

        # Tier distribution
        tier_counts = {"Tier 1": 0, "Tier 2": 0, "Tier 3": 0, "Tier 4": 0}
        if hasattr(self.orchestrator, '_symbol_tiers'):
            for sym, tier in self.orchestrator._symbol_tiers.items():
                tier_name = f"Tier {tier}"
                if tier_name in tier_counts:
                    tier_counts[tier_name] += 1

        left_table = Table(show_header=True, header_style="bold cyan")
        left_table.add_column("Tier")
        left_table.add_column("Symbols", justify="right")
        left_table.add_column("Description")
        left_table.add_row("Tier 1", str(tier_counts.get("Tier 1", 0)), "High volume, tight spreads")
        left_table.add_row("Tier 2", str(tier_counts.get("Tier 2", 0)), "Good liquidity")
        left_table.add_row("Tier 3", str(tier_counts.get("Tier 3", 0)), "Moderate liquidity")
        left_table.add_row("Tier 4", str(tier_counts.get("Tier 4", 0)), "Lower priority")

        left.update(Panel(left_table, title="📊 Symbol Tiers", border_style="blue"))

        # Recent scans
        right_table = Table(show_header=True, header_style="bold cyan")
        right_table.add_column("Time")
        right_table.add_column("Symbol")
        right_table.add_column("Market")
        right_table.add_column("Price", justify="right")
        right_table.add_column("24h Chg", justify="right")
        right_table.add_column("Volume", justify="right")
        right_table.add_column("Regime")

        # Get recent snapshots from repo
        if hasattr(self.orchestrator, '_recent_snapshots'):
            for snap in self.orchestrator._recent_snapshots[:20]:
                chg_color = "green" if snap.get("price_change_24h", 0) >= 0 else "red"
                right_table.add_row(
                    snap.get("timestamp", "")[:19] if snap.get("timestamp") else "—",
                    snap.get("symbol", "—"),
                    snap.get("market", "—"),
                    f"${snap.get('price', 0):,.4f}",
                    f"[{chg_color}]{snap.get('price_change_24h', 0):+.2f}%[/{chg_color}]",
                    f"${snap.get('volume_24h', 0)/1e6:.1f}M",
                    snap.get("regime", "UNKNOWN")
                )

        right.update(Panel(right_table, title="📡 Recent Market Snapshots", border_style="green"))

    def _render_spot_signals(self) -> None:
        """Spot signals view."""
        left = self.query_one("#left_content", Static)
        right = self.query_one("#right_content", Static)

        intel = self.orchestrator.intelligence
        spot_signals = []
        for sig_list in intel._last_signals.values():
            for s in sig_list:
                if s.get("market") == "SPOT":
                    spot_signals.append(s)

        spot_signals.sort(key=lambda s: s.get("confidence", 0), reverse=True)

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Time")
        table.add_column("Symbol", style="yellow")
        table.add_column("Dir", justify="center")
        table.add_column("Entry", justify="right")
        table.add_column("SL", justify="right")
        table.add_column("TP", justify="right")
        table.add_column("R:R", justify="right")
        table.add_column("Conf", justify="right")
        table.add_column("Strategy")
        table.add_column("Regime")

        for s in spot_signals[:30]:
            dir_style = "green" if s["direction"] in ("LONG", "BUY") else "red"
            rr = self._calc_rr(s)
            table.add_row(
                s.get("timestamp", "")[:19] if s.get("timestamp") else "—",
                s["symbol"],
                f"[{dir_style}]{s['direction']}[/{dir_style}]",
                f"${s['entry']:,.4f}",
                f"${s.get('stop_loss', 0):,.4f}",
                f"${s.get('take_profit', [0])[0]:,.4f}",
                f"{rr:.2f}",
                f"{int(s.get('confidence', 0)*100)}%",
                s.get("strategy", "N/A")[:15],
                s.get("regime", "UNKNOWN")
            )

        if not spot_signals:
            table.add_row("—", "No SPOT signals", "—", "—", "—", "—", "—", "—", "—", "—")

        left.update(Panel(table, title="📈 SPOT Signals", border_style="blue"))

        # Signal stats
        stats = self._get_signal_stats(spot_signals)
        right.update(Panel(stats, title="📊 Signal Statistics", border_style="green"))

    def _render_futures_signals(self) -> None:
        """Futures signals view."""
        left = self.query_one("#left_content", Static)
        right = self.query_one("#right_content", Static)

        intel = self.orchestrator.intelligence
        fut_signals = []
        for sig_list in intel._last_signals.values():
            for s in sig_list:
                if s.get("market") == "FUTURES":
                    fut_signals.append(s)

        fut_signals.sort(key=lambda s: s.get("confidence", 0), reverse=True)

        table = Table(show_header=True, header_style="bold cyan")
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
        table.add_column("Regime")

        for s in fut_signals[:30]:
            dir_style = "green" if s["direction"] in ("LONG", "BUY") else "red"
            rr = self._calc_rr(s)
            table.add_row(
                s.get("timestamp", "")[:19] if s.get("timestamp") else "—",
                s["symbol"],
                f"[{dir_style}]{s['direction']}[/{dir_style}]",
                f"{s.get('leverage', 1)}x",
                f"${s['entry']:,.4f}",
                f"${s.get('stop_loss', 0):,.4f}",
                f"${s.get('take_profit', [0])[0]:,.4f}",
                f"{rr:.2f}",
                f"{int(s.get('confidence', 0)*100)}%",
                s.get("strategy", "N/A")[:15],
                s.get("regime", "UNKNOWN")
            )

        if not fut_signals:
            table.add_row("—", "No FUTURES signals", "—", "—", "—", "—", "—", "—", "—", "—", "—")

        left.update(Panel(table, title="📉 FUTURES Signals", border_style="magenta"))

        stats = self._get_signal_stats(fut_signals)
        right.update(Panel(stats, title="📊 Signal Statistics", border_style="green"))

    def _render_positions(self) -> None:
        """Open positions view."""
        left = self.query_one("#left_content", Static)
        right = self.query_one("#right_content", Static)

        sim = self.orchestrator.simulator

        # Spot positions
        spot_table = Table(show_header=True, header_style="bold cyan")
        spot_table.add_column("Symbol", style="yellow")
        spot_table.add_column("Side", justify="center")
        spot_table.add_column("Entry", justify="right")
        spot_table.add_column("Current", justify="right")
        spot_table.add_column("Amount", justify="right")
        spot_table.add_column("Unrealized", justify="right")
        spot_table.add_column("SL", justify="right")
        spot_table.add_column("TP", justify="right")
        spot_table.add_column("Strategy")

        for p in sim.spot_positions.values():
            pnl = p.get("unrealized_pnl", 0)
            pnl_style = "green" if pnl >= 0 else "red"
            side_style = "green" if p["side"] in ("LONG", "BUY") else "red"
            spot_table.add_row(
                p["symbol"],
                f"[{side_style}]{p['side']}[/{side_style}]",
                f"${p['entry_price']:,.4f}",
                f"${p.get('current_price', p['entry_price']):,.4f}",
                f"{p['amount']:.6f}",
                f"[{pnl_style}]${pnl:+,.2f}[/{pnl_style}]",
                f"${p.get('stop_loss', 0):,.4f}" if p.get('stop_loss') else "—",
                f"${p.get('take_profit', 0):,.4f}" if p.get('take_profit') else "—",
                p.get("strategy", "N/A")[:12]
            )

        if not sim.spot_positions:
            spot_table.add_row("—", "No open SPOT positions", "—", "—", "—", "—", "—", "—", "—")

        # Futures positions
        fut_table = Table(show_header=True, header_style="bold magenta")
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

        for p in sim.futures_positions.values():
            pnl = p.get("unrealized_pnl", 0)
            pnl_style = "green" if pnl >= 0 else "red"
            side_style = "green" if p["side"] in ("LONG", "BUY") else "red"
            lev = p.get("leverage", 1)
            # Calculate liquidation price
            from paper_trading.liquidation_engine import LiquidationEngine
            le = LiquidationEngine()
            liq_price = le.calculate_liquidation_price(p)
            margin_ratio = le.get_margin_ratio(p, p.get("current_price", p["entry_price"]))

            fut_table.add_row(
                p["symbol"],
                f"[{side_style}]{p['side']}[/{side_style}]",
                f"{lev}x",
                f"${p['entry_price']:,.4f}",
                f"${p.get('current_price', p['entry_price']):,.4f}",
                f"{p['amount']:.6f}",
                f"[{pnl_style}]${pnl:+,.2f}[/{pnl_style}]",
                f"${liq_price:,.4f}" if liq_price > 0 else "N/A",
                f"{margin_ratio:.2f}",
                p.get("strategy", "N/A")[:12]
            )

        if not sim.futures_positions:
            fut_table.add_row("—", "No open FUTURES positions", "—", "—", "—", "—", "—", "—", "—", "—")

        left_content = Table.grid(padding=(0, 1))
        left_content.add_row(Panel(spot_table, title="📈 SPOT Positions", border_style="blue"))
        left_content.add_row(Panel(fut_table, title="📉 FUTURES Positions", border_style="magenta"))

        left.update(left_content)

        # Right: Position summary
        total_positions = len(sim.spot_positions) + len(sim.futures_positions)
        total_unrealized = sum(p.get("unrealized_pnl", 0) for p in sim.spot_positions.values())
        total_unrealized += sum(p.get("unrealized_pnl", 0) for p in sim.futures_positions.values())
        total_fees = sum(p.get("fees_paid", 0) for p in sim.spot_positions.values())
        total_fees += sum(p.get("fees_paid", 0) for p in sim.futures_positions.values())

        risk_info = Table.grid(padding=(0, 2))
        risk_info.add_column("Metric")
        risk_info.add_column("Value", justify="right", style="bold")
        risk_info.add_row("Total Open Positions", str(total_positions))
        risk_info.add_row("SPOT Positions", str(len(sim.spot_positions)))
        risk_info.add_row("FUTURES Positions", str(len(sim.futures_positions)))
        risk_info.add_row("", "")
        risk_info.add_row("Total Unrealized P&L", f"${total_unrealized:+,.2f}", style="green" if total_unrealized >= 0 else "red")
        risk_info.add_row("Total Fees Paid", f"${total_fees:,.2f}")
        risk_info.add_row("", "")
        risk_info.add_row("Max SPOT Positions", f"{sim.risk_manager.max_spot_positions}")
        risk_info.add_row("Max FUTURES Positions", f"{sim.risk_manager.max_futures_positions}")
        risk_info.add_row("Daily Loss Limit", f"{sim.risk_manager.max_daily_loss_pct}%")
        risk_info.add_row("Current Daily P&L", f"${sim.get_daily_pnl():+,.2f}")

        right.update(Panel(risk_info, title="⚠️ Position Risk Summary", border_style="yellow"))

    def _render_balances(self) -> None:
        """Account balances view."""
        left = self.query_one("#left_content", Static)
        right = self.query_one("#right_content", Static)

        sim = self.orchestrator.simulator
        spot_bal = sim.get_balance("SPOT")
        fut_bal = sim.get_balance("FUTURES")
        total = spot_bal + fut_bal
        initial_total = 1000.0  # 500 + 500

        # Balance history would come from repo
        balance_table = Table(show_header=True, header_style="bold cyan")
        balance_table.add_column("Account")
        balance_table.add_column("Initial", justify="right")
        balance_table.add_column("Current", justify="right")
        balance_table.add_column("P&L", justify="right")
        balance_table.add_column("Return", justify="right")

        spot_pnl = spot_bal - 500
        fut_pnl = fut_bal - 500
        balance_table.add_row("SPOT", "$500.00", f"${spot_bal:,.2f}", f"${spot_pnl:+,.2f}", f"{(spot_pnl/500*100):+.2f}%")
        balance_table.add_row("FUTURES", "$500.00", f"${fut_bal:,.2f}", f"${fut_pnl:+,.2f}", f"{(fut_pnl/500*100):+.2f}%")
        balance_table.add_row("[bold]TOTAL[/bold]", "[bold]$1,000.00[/bold]", f"[bold]${total:,.2f}[/bold]",
                              f"[bold]${spot_pnl+fut_pnl:+,.2f}[/bold]", f"[bold]{((spot_pnl+fut_pnl)/1000*100):+.2f}%[/bold]")

        left.update(Panel(balance_table, title="💰 Account Balances", border_style="blue"))

        # Margin info for futures
        margin_table = Table(show_header=True, header_style="bold cyan")
        margin_table.add_column("Metric")
        margin_table.add_column("Value", justify="right")
        margin_table.add_row("Futures Balance", f"${fut_bal:,.2f}")
        margin_table.add_row("Used Margin", f"${sum(p.get('amount',0)*p.get('entry_price',0)/p.get('leverage',1) for p in sim.futures_positions.values()):,.2f}")
        margin_table.add_row("Free Margin", f"${fut_bal - sum(p.get('amount',0)*p.get('entry_price',0)/p.get('leverage',1) for p in sim.futures_positions.values()):,.2f}")
        margin_table.add_row("Margin Ratio", f"{(fut_bal / max(1, sum(p.get('amount',0)*p.get('entry_price',0)/p.get('leverage',1) for p in sim.futures_positions.values()))) if sum(p.get('amount',0)*p.get('entry_price',0)/p.get('leverage',1) for p in sim.futures_positions.values()) > 0 else float('inf'):.2f}")
        margin_table.add_row("Max Leverage", f"{sim.risk_manager.max_leverage}x")

        right.update(Panel(margin_table, title="📊 Futures Margin", border_style="green"))

    def _render_pnl_stats(self) -> None:
        """P&L statistics view."""
        left = self.query_one("#left_content", Static)
        right = self.query_one("#right_content", Static)

        sim = self.orchestrator.simulator
        trades = sim.closed_trades

        if not trades:
            left.update(Panel("[dim]No closed trades yet[/dim]", title="📊 P&L Statistics", border_style="blue"))
            right.update("")
            return

        # Overall stats
        total_pnl = sum(t.get("pnl", 0) for t in trades)
        wins = [t for t in trades if t.get("pnl", 0) > 0]
        losses = [t for t in trades if t.get("pnl", 0) < 0]
        win_rate = len(wins) / len(trades) * 100
        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        largest_win = max((t["pnl"] for t in wins), default=0)
        largest_loss = min((t["pnl"] for t in losses), default=0)

        # Max drawdown
        peak = 1000.0
        equity = 1000.0
        max_dd = 0.0
        for t in trades:
            equity += t.get("pnl", 0)
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)

        stats_table = Table(show_header=True, header_style="bold cyan")
        stats_table.add_column("Metric")
        stats_table.add_column("Value", justify="right")

        stats_table.add_row("Total Trades", str(len(trades)))
        stats_table.add_row("Winning Trades", str(len(wins)))
        stats_table.add_row("Losing Trades", str(len(losses)))
        stats_table.add_row("Win Rate", f"{win_rate:.1f}%")
        stats_table.add_row("", "")
        stats_table.add_row("Total P&L", f"${total_pnl:+,.2f}", style="green" if total_pnl >= 0 else "red")
        stats_table.add_row("Gross Profit", f"${gross_profit:,.2f}")
        stats_table.add_row("Gross Loss", f"${gross_loss:,.2f}")
        stats_table.add_row("Profit Factor", f"{profit_factor:.2f}")
        stats_table.add_row("", "")
        stats_table.add_row("Avg Win", f"${avg_win:,.2f}")
        stats_table.add_row("Avg Loss", f"${avg_loss:,.2f}")
        stats_table.add_row("Largest Win", f"${largest_win:,.2f}")
        stats_table.add_row("Largest Loss", f"${largest_loss:,.2f}")
        stats_table.add_row("", "")
        stats_table.add_row("Max Drawdown", f"{max_dd:.2f}%")
        stats_table.add_row("Sharpe (approx)", f"{(total_pnl/len(trades))/(max(1, (sum((t['pnl']-total_pnl/len(trades))**2 for t in trades)/len(trades))**0.5)):.2f}" if len(trades) > 1 else "N/A")

        left.update(Panel(stats_table, title="📊 P&L Statistics", border_style="blue"))

        # By market
        spot_trades = [t for t in trades if t.get("market") == "SPOT"]
        fut_trades = [t for t in trades if t.get("market") == "FUTURES"]

        market_table = Table(show_header=True, header_style="bold cyan")
        market_table.add_column("Market")
        market_table.add_column("Trades", justify="right")
        market_table.add_column("Wins", justify="right")
        market_table.add_column("Win%", justify="right")
        market_table.add_column("Total P&L", justify="right")
        market_table.add_column("Profit Factor", justify="right")

        for market, mtrades in [("SPOT", spot_trades), ("FUTURES", fut_trades)]:
            if not mtrades:
                market_table.add_row(market, "0", "0", "0%", "$0.00", "N/A")
                continue
            mwins = [t for t in mtrades if t.get("pnl", 0) > 0]
            mlosses = [t for t in mtrades if t.get("pnl", 0) < 0]
            mpf = sum(t["pnl"] for t in mwins) / abs(sum(t["pnl"] for t in mlosses)) if mlosses else float('inf')
            market_table.add_row(
                market, str(len(mtrades)), str(len(mwins)),
                f"{len(mwins)/len(mtrades)*100:.1f}%",
                f"${sum(t.get('pnl',0) for t in mtrades):+,.2f}",
                f"{mpf:.2f}"
            )

        # By strategy
        strategy_table = Table(show_header=True, header_style="bold cyan")
        strategy_table.add_column("Strategy")
        strategy_table.add_column("Trades", justify="right")
        strategy_table.add_column("Win%", justify="right")
        strategy_table.add_column("Total P&L", justify="right")

        strategies = {}
        for t in trades:
            strat = t.get("strategy", "UNKNOWN")
            if strat not in strategies:
                strategies[strat] = []
            strategies[strat].append(t)

        for strat, strats_trades in sorted(strategies.items(), key=lambda x: sum(t.get("pnl",0) for t in x[1]), reverse=True):
            swins = [t for t in strats_trades if t.get("pnl", 0) > 0]
            strategy_table.add_row(
                strat, str(len(strats_trades)),
                f"{len(swins)/len(strats_trades)*100:.1f}%",
                f"${sum(t.get('pnl',0) for t in strats_trades):+,.2f}"
            )

        right_content = Table.grid(padding=(0, 1))
        right_content.add_row(Panel(market_table, title="📈 By Market", border_style="green"))
        right_content.add_row(Panel(strategy_table, title="🎯 By Strategy", border_style="yellow"))

        right.update(right_content)

    def _render_strategy(self) -> None:
        """Strategy performance view."""
        left = self.query_one("#left_content", Static)
        right = self.query_one("#right_content", Static)

        # Get strategy metrics from repo
        repo = getattr(self.orchestrator, '_repo', None)
        if repo:
            metrics = repo.get_all_strategy_metrics()
        else:
            metrics = []

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Strategy")
        table.add_column("Market")
        table.add_column("Signals", justify="right")
        table.add_column("Validated", justify="right")
        table.add_column("Wins", justify="right")
        table.add_column("Losses", justify="right")
        table.add_column("Win%", justify="right")
        table.add_column("Total P&L", justify="right")
        table.add_column("Profit Factor", justify="right")
        table.add_column("Weight", justify="right")

        for m in metrics:
            table.add_row(
                m.strategy,
                m.market,
                str(m.total_signals),
                str(m.validated_signals),
                str(m.winning_trades),
                str(m.losing_trades),
                f"{m.win_rate*100:.1f}%",
                f"${m.total_pnl:+,.2f}",
                f"{m.profit_factor:.2f}",
                f"{m.weight:.2f}"
            )

        if not metrics:
            table.add_row("—", "—", "0", "0", "0", "0", "0%", "$0.00", "0.00", "1.00")

        left.update(Panel(table, title="🎯 Strategy Performance", border_style="blue"))

        # Strategy selector weights
        intel = self.orchestrator.intelligence
        selector = intel.strategy_selector

        weight_table = Table(show_header=True, header_style="bold cyan")
        weight_table.add_column("Strategy")
        weight_table.add_column("Base Weight", justify="right")
        weight_table.add_column("Regime Adjusted", justify="right")

        for strat, weight in selector.weights.items():
            # Show for current regime
            regime = "UNKNOWN"
            adjusted = weight
            if hasattr(intel, '_current_regime'):
                regime = intel._current_regime
                if regime in selector.regime_prefs:
                    adjusted *= selector.regime_prefs[regime].get(strat, 1.0)

            weight_table.add_row(strat, f"{weight:.3f}", f"{adjusted:.3f}")

        right.update(Panel(weight_table, title=f"⚖️ Strategy Weights (Regime: {regime})", border_style="green"))

    def _render_learning(self) -> None:
        """Learning status view."""
        left = self.query_one("#left_content", Static)
        right = self.query_one("#right_content", Static)

        predictor = self.orchestrator.intelligence.predictor

        # Model status
        status_table = Table(show_header=True, header_style="bold cyan")
        status_table.add_column("Component")
        status_table.add_column("Status")
        status_table.add_column("Details")

        model_status = "🟢 Ready" if predictor.is_trained else "🟡 Not Trained"
        status_table.add_row("ML Model", model_status, f"v{predictor.version}" if predictor.is_trained else "Using rule-based fallback")
        status_table.add_row("RF Model", "🟢 Loaded" if predictor.rf_model else "🔴 Not Loaded", "—")
        status_table.add_row("XGBoost Model", "🟢 Loaded" if predictor.xgb_model else "🔴 Not Loaded", "—")
        status_table.add_row("River Model", "🟡 Available", "river v0.27.0")

        # Prediction stats from repo
        repo = getattr(self.orchestrator, '_repo', None)
        if repo:
            preds = repo.get_predictions_history(100)
            resolved = [p for p in preds if p.is_correct is not None]
            correct = [p for p in resolved if p.is_correct]
            accuracy = len(correct) / len(resolved) * 100 if resolved else 0
            status_table.add_row("Predictions (100)", str(len(preds)), f"{len(resolved)} resolved, {accuracy:.1f}% accurate")
        else:
            status_table.add_row("Predictions", "N/A", "No repo connection")

        left.update(Panel(status_table, title="🧠 Learning Status", border_style="blue"))

        # Recent predictions
        pred_table = Table(show_header=True, header_style="bold cyan")
        pred_table.add_column("Time")
        pred_table.add_column("Symbol")
        pred_table.add_column("Market")
        pred_table.add_column("Predicted", justify="center")
        pred_table.add_column("Conf", justify="right")
        pred_table.add_column("Actual", justify="center")
        pred_table.add_column("Return", justify="right")
        pred_table.add_column("Correct", justify="center")

        if repo:
            for p in preds[:20]:
                actual = p.actual_outcome or "—"
                correct_mark = "✅" if p.is_correct else ("❌" if p.is_correct is not None else "⏳")
                ret = f"{p.actual_return_pct:+.2f}%" if p.actual_return_pct else "—"
                pred_table.add_row(
                    p.created_at.strftime("%H:%M:%S") if p.created_at else "—",
                    p.symbol,
                    p.market,
                    p.predicted_class,
                    f"{p.confidence:.1%}",
                    actual,
                    ret,
                    correct_mark
                )

        right.update(Panel(pred_table, title="📋 Recent Predictions", border_style="green"))

    def _render_health(self) -> None:
        """System health view."""
        left = self.query_one("#left_content", Static)
        right = self.query_one("#right_content", Static)

        health = self.orchestrator.health_monitor if self.orchestrator else None

        if not health:
            left.update(Panel("[red]No health monitor[/red]", title="🏥 System Health"))
            right.update("")
            return

        status = health.get_status()

        comp_table = Table(show_header=True, header_style="bold cyan")
        comp_table.add_column("Component")
        comp_table.add_column("Status")
        comp_table.add_column("Details")

        for comp_name, comp_status in status.get("components", {}).items():
            status_text = comp_status.get("status", "unknown")
            status_emoji = "🟢" if status_text == "healthy" else "🟡" if status_text == "degraded" else "🔴"
            comp_table.add_row(comp_name, f"{status_emoji} {status_text}", comp_status.get("message", ""))

        left.update(Panel(comp_table, title="🏥 Component Health", border_style="blue"))

        # System metrics
        metrics = status.get("metrics", {})
        sys_table = Table(show_header=True, header_style="bold cyan")
        sys_table.add_column("Metric")
        sys_table.add_column("Value", justify="right")

        sys_table.add_row("Uptime", f"{metrics.get('uptime_seconds', 0)/3600:.1f}h")
        sys_table.add_row("CPU %", f"{metrics.get('cpu_percent', 0):.1f}%")
        sys_table.add_row("Memory %", f"{metrics.get('memory_percent', 0):.1f}%")
        sys_table.add_row("Disk %", f"{metrics.get('disk_percent', 0):.1f}%")
        sys_table.add_row("Events Processed", str(metrics.get('events_processed', 0)))
        sys_table.add_row("Errors (1h)", str(metrics.get('errors_last_hour', 0)))

        right.update(Panel(sys_table, title="📊 System Metrics", border_style="green"))

    def _render_logs(self) -> None:
        """Logs view - already handled by Log panel."""
        left = self.query_one("#left_content", Static)
        right = self.query_one("#right_content", Static)

        left.update(Panel("[dim]Logs displayed in bottom panel[/dim]", title="📜 Event Logs", border_style="blue"))
        right.update("")

    # ===== Helper Methods =====

    def _calc_rr(self, signal: dict) -> float:
        """Calculate risk:reward ratio."""
        entry = signal.get("entry", 0)
        sl = signal.get("stop_loss", 0)
        tp = signal.get("take_profit", [0])[0]
        if entry == 0 or sl == 0 or tp == 0:
            return 0.0
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        return reward / risk if risk > 0 else 0.0

    def _get_signal_stats(self, signals: list) -> Table:
        """Generate signal statistics table."""
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Metric")
        table.add_column("Value", justify="right")

        if not signals:
            table.add_row("Total Signals", "0")
            table.add_row("Avg Confidence", "0%")
            table.add_row("By Direction", "—")
            table.add_row("By Strategy", "—")
            return table

        table.add_row("Total Signals", str(len(signals)))
        avg_conf = sum(s.get("confidence", 0) for s in signals) / len(signals)
        table.add_row("Avg Confidence", f"{avg_conf*100:.1f}%")

        # By direction
        dirs = {}
        for s in signals:
            d = s.get("direction", "UNKNOWN")
            dirs[d] = dirs.get(d, 0) + 1
        for d, c in sorted(dirs.items(), key=lambda x: -x[1]):
            table.add_row(f"  {d}", str(c))

        # By strategy
        strats = {}
        for s in signals:
            st = s.get("strategy", "UNKNOWN")
            strats[st] = strats.get(st, 0) + 1
        for st, c in sorted(strats.items(), key=lambda x: -x[1])[:5]:
            table.add_row(f"  {st}", str(c))

        return table