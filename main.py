#!/usr/bin/env python3
"""BlackMarket AI - Local autonomous market research and simulation platform.

Paper trading only. No real money execution. No API keys required.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

# Load environment first
from dotenv import load_dotenv

load_dotenv()

from config import DATABASE_URL, LOG_LEVEL
from core.config_validator import validate_config_or_exit
from core.orchestrator import Orchestrator
from database.connection import Database


def _configure_logging(tui: bool) -> None:
    """Configure root logging for headless or interactive TUI mode."""
    Path("logs").mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.FileHandler(Path("logs") / "blackmarket.log", encoding="utf-8"),
    ]
    if not tui:
        handlers.insert(0, logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )


logger = logging.getLogger(__name__)


async def main(tui: bool = False) -> int:
    _configure_logging(tui)

    # Validate configuration at startup
    validate_config_or_exit()

    logger.info("=" * 60)
    logger.info("BLACKMARKET AI v1.0 - Local Paper Trading Research System")
    logger.info("=" * 60)

    # Initialize database
    db = Database(DATABASE_URL)
    db.init_db()

    # Create and initialize orchestrator
    orch = Orchestrator(db)
    await orch.initialize()
    event_task = asyncio.create_task(orch.event_bus.run(), name="blackmarket-event-bus")

    # Handle shutdown signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(orch.handle_signal(s, None)))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler for SIGTERM
            pass

    orch_task: asyncio.Task | None = None
    log_handler: logging.Handler | None = None
    try:
        if tui:
            from terminal.dashboard import DashboardApp, DashboardLogHandler

            app = DashboardApp(orchestrator=orch)
            log_handler = DashboardLogHandler(app)
            log_handler.setLevel(getattr(logging, LOG_LEVEL))
            logging.getLogger().addHandler(log_handler)
            orch_task = asyncio.create_task(orch.run(), name="blackmarket-orchestrator")
            await app.run_async()
        else:
            await orch.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        if log_handler is not None:
            logging.getLogger().removeHandler(log_handler)
        await orch.stop()
        if orch_task and not orch_task.done():
            orch_task.cancel()
            await asyncio.gather(orch_task, return_exceptions=True)
        if not event_task.done():
            event_task.cancel()
            await asyncio.gather(event_task, return_exceptions=True)
        db.close()
        logger.info("BlackMarket AI stopped")

    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BlackMarket AI - Local Paper Trading Research System")
    parser.add_argument(
        "--tui",
        "--terminal",
        action="store_true",
        dest="tui",
        help="Launch the interactive real-time terminal dashboard alongside the engine",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main(tui=args.tui)))