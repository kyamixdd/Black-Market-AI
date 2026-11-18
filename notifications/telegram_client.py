"""Telegram notification client with duplicate prevention and all notification types."""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


class TelegramClient:
    """Telegram notification client with deduplication and rich formatting."""

    def __init__(self, token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.token = token
        self.chat_id = chat_id
        self._bot = None  # type: ignore[assignment]
        self._enabled = bool(token and chat_id)
        # Deduplication: track recent message hashes with timestamps
        self._sent_hashes: dict[str, float] = {}
        self._dedup_ttl_seconds = 300  # 5 minutes

    async def _ensure_bot(self) -> bool:
        if self._bot is None and self._enabled:
            try:
                from telegram import Bot
                self._bot = Bot(token=self.token)
                # Test connection
                await self._bot.get_me()
                logger.info("Telegram bot connected successfully")
            except Exception as exc:
                # Keep the client enabled so transient network/API failures can retry
                # on the next notification instead of permanently disabling Telegram.
                logger.error("Failed to initialize Telegram bot: %s", exc)
                self._bot = None
                return False
        return self._enabled and self._bot is not None

    def _make_hash(self, text: str) -> str:
        """Create a hash for deduplication."""
        return hashlib.md5(text.encode()).hexdigest()[:16]

    def _is_duplicate(self, text: str) -> bool:
        """Check if message was sent recently."""
        h = self._make_hash(text)
        now = time.time()
        if h in self._sent_hashes:
            if now - self._sent_hashes[h] < self._dedup_ttl_seconds:
                return True
        return False

    def _remember_sent(self, text: str) -> None:
        """Remember a message only after Telegram confirms it was sent."""
        now = time.time()
        self._sent_hashes[self._make_hash(text)] = now
        self._sent_hashes = {
            key: sent_at
            for key, sent_at in self._sent_hashes.items()
            if now - sent_at < self._dedup_ttl_seconds
        }

    async def send_message(self, text: str, parse_mode: str = "HTML", force: bool = False) -> bool:
        """Send a message with deduplication."""
        if not self._enabled:
            logger.debug("Telegram not configured, skipping message")
            return False

        if not force and self._is_duplicate(text):
            logger.debug("Duplicate message suppressed")
            return False

        if not await self._ensure_bot():
            return False

        try:
            await self._bot.send_message(chat_id=self.chat_id, text=text, parse_mode=parse_mode)
            self._remember_sent(text)
            return True
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return False

    async def test_connection(self) -> bool:
        """Verify bot credentials and Telegram API connectivity without sending a message."""
        if not self._enabled:
            return False
        if not await self._ensure_bot():
            return False
        try:
            await self._bot.get_me()
            return True
        except Exception as exc:
            logger.error("Telegram connection test failed: %s", exc)
            self._bot = None
            return False

    # ===== Notification Methods =====

    async def send_strong_setup(self, signal: dict) -> bool:
        """Send strong setup alert."""
        direction_emoji = "🟢" if signal["direction"] in ("LONG", "BUY") else "🔴"
        regime = signal.get("regime", "UNKNOWN")
        confidence = int(signal.get("confidence", 0) * 100)

        tp_list = signal.get("take_profit", [])
        tp1 = tp_list[0] if tp_list else signal.get("entry", 0) * 1.02
        tp2 = tp_list[1] if len(tp_list) > 1 else tp1 * 1.02

        msg = (
            f"<b>🚀 BLACKMARKET AI — STRONG SETUP</b>\n\n"
            f"#{signal['symbol']} | {signal['market']}\n"
            f"{direction_emoji} <b>{signal['direction']}</b> | Regime: {regime}\n\n"
            f"📍 <b>Entry Zone</b>: ${signal['entry']:,.4f}\n"
            f"🛑 <b>Stop Loss</b>: ${signal['stop_loss']:,.4f}\n"
            f"🎯 <b>Target 1</b>: ${tp1:,.4f}\n"
            f"🎯 <b>Target 2</b>: ${tp2:,.4f}\n\n"
            f"📊 <b>Confidence</b>: {confidence}%\n"
            f"🧠 <b>Strategy</b>: {signal.get('strategy', 'UNKNOWN')}\n"
            f"⏱ <b>Timeframe</b>: {signal.get('timeframe', 'MULTI')}\n\n"
            f"⚡ <b>Mode</b>: PAPER ONLY\n"
            f"⚠️ Not financial advice."
        )
        return await self.send_message(msg)

    async def send_signal_update(self, signal: dict, update_type: str) -> bool:
        """Send signal status update (validated, rejected, expired)."""
        emoji_map = {
            "validated": "✅",
            "rejected": "❌",
            "expired": "⏰",
            "executed": "📝",
        }
        emoji = emoji_map.get(update_type, "📢")

        msg = (
            f"{emoji} <b>Signal {update_type.upper()}</b>\n\n"
            f"#{signal['symbol']} | {signal['market']}\n"
            f"{signal['direction']} @ ${signal['entry']:,.4f}\n"
            f"Strategy: {signal.get('strategy', 'UNKNOWN')}\n"
            f"Reason: {signal.get('reject_reason', 'N/A')}"
        )
        return await self.send_message(msg)

    async def send_position_opened(self, position: dict) -> bool:
        """Send position opened notification."""
        side_emoji = "🟢" if position["side"] in ("LONG", "BUY") else "🔴"
        lev = f" ({position.get('leverage', 1.0)}x)" if position.get("market") == "FUTURES" else ""

        msg = (
            f"{side_emoji} <b>POSITION OPENED</b>\n\n"
            f"#{position['symbol']} | {position['market']}{lev}\n"
            f"<b>{position['side']}</b>\n\n"
            f"📍 Entry: ${position['entry_price']:,.4f}\n"
            f"📦 Amount: {position['amount']:.6f}\n"
            f"🛑 Stop Loss: ${position.get('stop_loss', 0):,.4f}\n"
            f"🎯 Take Profit: ${position.get('take_profit', 0):,.4f}\n\n"
            f"💰 Fee: ${position.get('fees_paid', 0):.4f}\n"
            f"🆔 {position['position_id']}"
        )
        return await self.send_message(msg)

    async def send_position_closed(self, trade: dict) -> bool:
        """Send position closed notification with P&L."""
        pnl = trade.get("pnl", 0)
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        pnl_pct = trade.get("pnl_pct", 0)

        msg = (
            f"{pnl_emoji} <b>POSITION CLOSED</b>\n\n"
            f"#{trade['symbol']} | {trade['market']}\n"
            f"<b>{trade['side']}</b> | {trade.get('close_reason', 'UNKNOWN')}\n\n"
            f"📍 Entry: ${trade['entry_price']:,.4f}\n"
            f"📤 Exit: ${trade['exit_price']:,.4f}\n"
            f"📦 Amount: {trade['amount']:.6f}\n\n"
            f"{pnl_emoji} <b>P&L</b>: ${pnl:+.2f} ({pnl_pct:+.2f}%)\n"
            f"💰 Fee: ${trade.get('fee', 0):.4f}\n"
            f"⏱ Held: {self._format_duration(trade.get('opened_at'), trade.get('closed_at'))}\n"
            f"🆔 {trade.get('position_id', trade.get('signal_id', 'N/A'))}"
        )
        return await self.send_message(msg)

    async def send_daily_risk_warning(self, daily_pnl: float, balance: float, threshold_pct: float = 2.0) -> bool:
        """Send daily loss warning."""
        pnl_pct = (daily_pnl / balance) * 100 if balance > 0 else 0
        emoji = "🟡" if pnl_pct > -threshold_pct * 0.5 else "🔴"

        msg = (
            f"{emoji} <b>DAILY RISK WARNING</b>\n\n"
            f"Daily P&L: ${daily_pnl:+.2f} ({pnl_pct:+.2f}%)\n"
            f"Limit: -{threshold_pct}% (${-balance * threshold_pct / 100:.2f})\n"
            f"Total Balance: ${balance:.2f}\n\n"
            f"{'⚠️ Approaching limit' if pnl_pct > -threshold_pct * 0.5 else '🚨 Limit exceeded — new positions blocked'}"
        )
        return await self.send_message(msg)

    async def send_learning_report(self, report: dict) -> bool:
        """Send learning cycle report."""
        status = report.get("status", "unknown")
        emoji = "✅" if status == "trained" else "⏭️" if status == "model_current" else "⚠️"

        msg = (
            f"{emoji} <b>LEARNING REPORT</b>\n\n"
            f"Status: {status}\n"
            f"Samples: {report.get('samples', 0)}\n"
            f"RF F1: {report.get('validation', {}).get('rf', {}).get('aggregated', {}).get('mean_f1', 0):.3f}\n"
            f"XGB F1: {report.get('validation', {}).get('xgb', {}).get('aggregated', {}).get('mean_f1', 0):.3f}\n"
            f"Promoted: {'Yes' if report.get('promoted') else 'No'}\n"
            f"Outcomes labeled: {report.get('outcomes_labeled', 0)}"
        )
        return await self.send_message(msg)

    async def send_system_error(self, error: str, source: str = "SYSTEM") -> bool:
        """Send system error notification."""
        msg = (
            f"🔴 <b>SYSTEM ERROR</b>\n\n"
            f"Source: {source}\n"
            f"Error: <code>{error[:500]}</code>\n"
            f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        return await self.send_message(msg, force=True)  # Force send errors

    async def send_connection_status(self, component: str, status: str, details: str = "") -> bool:
        """Send connection status change."""
        emoji = "🟢" if status == "connected" else "🔴" if status == "disconnected" else "🟡"

        msg = (
            f"{emoji} <b>CONNECTION STATUS</b>\n\n"
            f"Component: {component}\n"
            f"Status: {status.upper()}\n"
            f"{details}"
        )
        return await self.send_message(msg)

    async def send_early_warning(self, message: str, symbol: str = "", market: str = "") -> bool:
        """Send early warning notification."""
        msg = (
            f"🟡 <b>EARLY WARNING</b>\n\n"
            f"{message}\n"
            f"{f'#{symbol} | {market}' if symbol else ''}\n"
            f"Time: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
        )
        return await self.send_message(msg)

    async def send_daily_summary(self, stats: dict) -> bool:
        """Send daily summary report."""
        spot_bal = stats.get("spot_balance", 0)
        fut_bal = stats.get("futures_balance", 0)
        total = spot_bal + fut_bal
        realized = stats.get("realized_pnl", 0)
        unrealized = stats.get("unrealized_pnl", 0)
        win_rate = stats.get("win_rate", 0)
        profit_factor = stats.get("profit_factor", 0)
        max_dd = stats.get("max_drawdown", 0)
        trades = stats.get("trades_today", 0)

        pnl_emoji = "🟢" if realized >= 0 else "🔴"

        msg = (
            f"📊 <b>DAILY SUMMARY</b> — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n"
            f"💰 <b>Balances</b>\n"
            f"  Spot: ${spot_bal:.2f}\n"
            f"  Futures: ${fut_bal:.2f}\n"
            f"  <b>Total: ${total:.2f}</b>\n\n"
            f"{pnl_emoji} <b>P&L</b>\n"
            f"  Realized: ${realized:+.2f}\n"
            f"  Unrealized: ${unrealized:+.2f}\n"
            f"  <b>Net: ${realized + unrealized:+.2f}</b>\n\n"
            f"📈 <b>Performance</b>\n"
            f"  Trades: {trades}\n"
            f"  Win Rate: {win_rate:.1f}%\n"
            f"  Profit Factor: {profit_factor:.2f}\n"
            f"  Max DD: {max_dd:.2f}%\n\n"
            f"⚡ Mode: PAPER ONLY"
        )
        return await self.send_message(msg)

    @staticmethod
    def _format_duration(opened, closed) -> str:
        """Format duration between two timestamps."""
        if not opened or not closed:
            return "N/A"
        if isinstance(opened, str):
            opened = datetime.fromisoformat(opened.replace("Z", "+00:00"))
        if isinstance(closed, str):
            closed = datetime.fromisoformat(closed.replace("Z", "+00:00"))
        delta = closed - opened
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{delta.total_seconds() / 60:.0f}m"
        elif hours < 24:
            return f"{hours:.1f}h"
        else:
            return f"{hours / 24:.1f}d"