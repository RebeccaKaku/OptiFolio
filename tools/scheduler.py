"""Scheduler for background tasks such as data ingestion and portfolio snapshots."""

import asyncio
import datetime
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.services.market_data_service import MarketDataIngestionService
from src.api.enhanced_api_service import get_enhanced_api_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scheduler")

async def record_portfolio_snapshot():
    """Record a snapshot of the current portfolio state."""
    logger.info("Recording portfolio snapshot...")
    try:
        api = get_enhanced_api_service()
        # Portfolio snapshot logic
        result = api.get_portfolio_snapshot()
        if result["success"]:
            logger.info("Portfolio snapshot recorded successfully")
        else:
            logger.error(f"Failed to record snapshot: {result.get('error')}")
    except Exception as e:
        logger.error(f"Error recording portfolio snapshot: {e}")

async def run_ingestion():
    """Run ingestion for a set of predefined assets."""
    logger.info("Starting scheduled ingestion...")
    service = MarketDataIngestionService()

    # Example assets to ingest
    assets = [
        ("AAPL", "yahoo"),
        ("sh000001", "yahoo"),
        ("510300", "akshare"),
    ]

    end_date = datetime.datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    for symbol, provider in assets:
        logger.info(f"Ingesting {symbol} from {provider}...")
        try:
            await service.ingest_asset(symbol, start_date, end_date, provider)
            logger.info(f"Successfully ingested {symbol}")
        except Exception as e:
            logger.error(f"Failed to ingest {symbol}: {e}")

async def main_loop():
    """Main scheduler loop."""
    logger.info("Starting OptiFolio Scheduler...")

    while True:
        now = datetime.datetime.now()

        # Run ingestion once a day at 01:00
        if now.hour == 1 and now.minute == 0:
            await run_ingestion()
            # Wait a minute to avoid re-triggering
            await asyncio.sleep(60)

        # Record snapshot every hour
        if now.minute == 0:
            await record_portfolio_snapshot()
            # Wait a minute to avoid re-triggering
            await asyncio.sleep(60)

        await asyncio.sleep(30)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
