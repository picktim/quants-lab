from decimal import Decimal

from optuna import trial

from controllers.directional_trading.xtreet_bb import XtreetBBControllerConfig
from core.backtesting.optimizer import BacktestingConfig, BaseStrategyConfigGenerator
from hummingbot.strategy_v2.executors.position_executor.data_types import TrailingStop


class XtreetConfigGenerator(BaseStrategyConfigGenerator):
    trading_pair = None

    async def generate_config(self, trial: trial) -> BacktestingConfig:
        connector_name = "binance_perpetual"
        trading_pair = self.trading_pair
        interval = trial.suggest_categorical("interval", ["1m"])
        # Generate specific Xtreet metrics
        bb_length = trial.suggest_int("bb_length", 20, 200, step=20)
        bb_std = trial.suggest_float("bb_std", 0.5, 3.0, step=0.5)

        # Metrics management
        dca_spread_1 = trial.suggest_float("last_spread", 0.1, 0.75)
        dca_amount_1 = trial.suggest_float("last_amount", 1.0, 2.0)

        # Triple barrier metrics
        stop_loss = trial.suggest_float("stop_loss", 0.01, 0.75)

        trailing_stop_activation = trial.suggest_float("trailing_stop_activation", 0.1, 0.5)
        trailing_stop_delta = trial.suggest_float("trailing_stop_delta", 0.1, 0.5)
        trailing_stop = TrailingStop(
            activation_price=Decimal(trailing_stop_activation),
            trailing_delta=Decimal(trailing_stop_delta)
        )
        # Id Generation
        controller_id = f"xtreet_bb_{connector_name}_{interval}_{trading_pair}_" \
                        f"bb{bb_length}_{bb_std}_sl{round(100 * stop_loss, 1)}_" \
                        f"ts{round(100 * trailing_stop_activation, 1)}-" \
                        f"{round(100 * trailing_stop_delta, 1)}" \

        config = XtreetBBControllerConfig(
            id=controller_id,
            total_amount_quote=Decimal("1000"),
            connector_name=connector_name,
            trading_pair=trading_pair,
            candles_trading_pair=trading_pair,
            interval=interval,
            bb_length=bb_length,
            bb_std=bb_std,
            bb_long_threshold=0.0,
            bb_short_threshold=1.0,
            dca_spreads=[Decimal("-0.00000001"), dca_spread_1],
            dca_amounts_pct=[Decimal("1"), dca_amount_1],
            stop_loss=Decimal(stop_loss),
            trailing_stop=trailing_stop,
            dynamic_order_spread=True,
            dynamic_target=True,
            min_stop_loss=Decimal("0.01"),
            max_stop_loss=Decimal("0.1"),
            min_trailing_stop=Decimal("0.005"),
            max_trailing_stop=Decimal("0.03"),
            min_distance_between_orders=Decimal("0.01"),
            time_limit=60 * 60 * 24,
            max_executors_per_side=1,
            cooldown_time=60 * 5
        )
        return BacktestingConfig(config=config, start=self.start, end=self.end)