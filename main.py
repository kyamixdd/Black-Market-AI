#!/usr/bin/env python3
"""BlackMarket AI - Local autonomous market research and simulation platform.

Paper trading only. No real money execution. No API keys required.
"""
from __future__ import annotations

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

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path("logs") / "blackmarket.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


async def main() -> int:
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

    try:
        await orch.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        await orch.stop()
        if not event_task.done():
            event_task.cancel()
            await asyncio.gather(event_task, return_exceptions=True)
        db.close()
        logger.info("BlackMarket AI stopped")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))