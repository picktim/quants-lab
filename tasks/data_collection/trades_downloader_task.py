import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict

import pandas as pd

from core.data_sources import CLOBDataSource
from core.services.timescale_client import TimescaleClient
from core.task_base import BaseTask

logging.basicConfig(level=logging.INFO)


class TradesDownloaderTask(BaseTask):
    def __init__(self, name: str, frequency: timedelta, config: Dict[str, Any]):
        super().__init__(name, frequency, config)
        self.connector_name = config['connector_name']
        self.days_data_retention = config.get("days_data_retention", 7)
        self.start_time = time.time() - self.days_data_retention * 24 * 60 * 60
        self.quote_asset = config.get('quote_asset', "USDT")
        self.min_notional_size = Decimal(str(config.get('min_notional_size', 10.0)))
        self.clob = CLOBDataSource()

    async def execute(self):
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f UTC')
        logging.info(f"{now} - Starting trades downloader for {self.connector_name} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        end_time = datetime.now(timezone.utc)
        start_time = pd.Timestamp(self.start_time, unit="s").tz_localize(timezone.utc)
        logging.info(f"{now} - Start date: {start_time}, End date: {end_time}")
        logging.info(f"{now} - Quote asset: {self.quote_asset}, Min notional size: {self.min_notional_size}")

        timescale_client = TimescaleClient(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", 5432),
            user=os.getenv("POSTGRES_USER", "admin"),
            password=os.getenv("POSTGRES_PASSWORD", "admin"),
            database=os.getenv("POSTGRES_DB", "timescaledb")
        )
        await timescale_client.connect()

        trading_rules = await self.clob.get_trading_rules(self.connector_name)
        trading_pairs = trading_rules.filter_by_quote_asset(self.quote_asset) \
            .filter_by_min_notional_size(self.min_notional_size) \
            .get_all_trading_pairs()
        for i, trading_pair in enumerate(trading_pairs):
            logging.info(f"{now} - Fetching trades for {trading_pair} [{i} from {len(trading_pairs)}]")
            try:
                table_name = timescale_client.get_trades_table_name(self.connector_name, trading_pair)
                last_trade_id = await timescale_client.get_last_trade_id(connector_name=self.connector_name,
                                                                         trading_pair=trading_pair,
                                                                         table_name=table_name)
                trades = await self.clob.get_trades(
                    self.connector_name,
                    trading_pair,
                    int(start_time.timestamp()),
                    int(end_time.timestamp()),
                    last_trade_id
                )

                if trades.empty:
                    logging.info(f"{now} - No new trades for {trading_pair}")
                    continue

                trades["connector_name"] = self.connector_name
                trades["trading_pair"] = trading_pair

                trades_data = trades[
                    ["id", "connector_name", "trading_pair", "timestamp", "price", "volume",
                     "sell_taker"]].values.tolist()

                await timescale_client.append_trades(table_name=table_name,
                                                     trades=trades_data)
                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                cutoff_timestamp = (today_start - timedelta(days=self.days_data_retention)).timestamp()
                await timescale_client.delete_trades(connector_name=self.connector_name, trading_pair=trading_pair,
                                                     timestamp=cutoff_timestamp)
                await timescale_client.compute_resampled_ohlc(connector_name=self.connector_name,
                                                              trading_pair=trading_pair, interval="1s")
                logging.info(f"{now} - Inserted {len(trades_data)} trades for {trading_pair}")

            except Exception as e:
                logging.exception(f"{now} - An error occurred during the data load for trading pair {trading_pair}:\n {e}")
                continue

        await timescale_client.close()


if __name__ == "__main__":
    config = {
        'connector_name': 'binance_perpetual',
        'quote_asset': 'USDT',
        'min_notional_size': 10.0,
        'db_host': 'localhost',
        'db_port': 5432,
        'db_name': 'timescaledb'
    }

    task = TradesDownloaderTask("Trades Downloader", timedelta(hours=1), config)
    asyncio.run(task.execute())
