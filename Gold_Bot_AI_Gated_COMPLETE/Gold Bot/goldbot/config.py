from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade_pct: float
    daily_profit_target_pct: float
    daily_loss_limit_pct: float
    max_trades_per_day: int
    max_open_positions: int
    max_spread_points: float
    min_stop_points: float
    max_stop_points: float
    max_lot: float
    consecutive_loss_limit: int
    emergency_drawdown_pct: float
    max_total_lots: float


def load_config(path: str) -> dict:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if cfg["mode"] not in {"backtest", "paper", "live"}:
        raise ValueError("mode must be backtest, paper, or live")
    risk = cfg["risk"]
    for key in ("risk_per_trade_pct", "daily_profit_target_pct", "daily_loss_limit_pct"):
        if float(risk[key]) <= 0:
            raise ValueError(f"{key} must be positive")
    if cfg["mode"] == "live" and not cfg.get("enable_order_submission", False):
        raise ValueError("live mode requires the separate order-submission lock")
    if cfg["mode"] == "live" and cfg.get("live_confirmation") != "I UNDERSTAND LIVE TRADING RISK":
        raise ValueError("live mode requires the exact live_confirmation phrase")
    return cfg


def risk_config(cfg: dict) -> RiskConfig:
    return RiskConfig(**cfg["risk"])
