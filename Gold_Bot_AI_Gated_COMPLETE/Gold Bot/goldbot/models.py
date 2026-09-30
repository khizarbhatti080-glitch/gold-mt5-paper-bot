from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Mode(str, Enum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class DataQuality(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"


class RejectReason(str, Enum):
    APPROVED = "APPROVED"
    KILL_SWITCH = "KILL_SWITCH"
    CONNECTION_UNHEALTHY = "CONNECTION_UNHEALTHY"
    DATA_QUALITY = "DATA_QUALITY"
    MARKET_CLOSED = "MARKET_CLOSED"
    DAILY_LOSS = "DAILY_LOSS"
    DAILY_PROFIT = "DAILY_PROFIT"
    EMERGENCY_DRAWDOWN = "EMERGENCY_DRAWDOWN"
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"
    MISSING_STOP = "MISSING_STOP"
    INVALID_STOP = "INVALID_STOP"
    SPREAD = "SPREAD"
    OUT_OF_SESSION = "OUT_OF_SESSION"
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY"
    MAX_TRADES = "MAX_TRADES"
    MAX_POSITIONS = "MAX_POSITIONS"
    BELOW_MIN_LOT = "BELOW_MIN_LOT"
    EXPOSURE = "EXPOSURE"


@dataclass(frozen=True)
class Signal:
    side: Side
    timestamp: datetime
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = ""


@dataclass(frozen=True)
class AccountSnapshot:
    equity: float
    balance: float
    open_positions: int
    spread_points: float


@dataclass(frozen=True)
class SymbolSpec:
    tick_size: float
    tick_value: float
    volume_min: float
    volume_max: float
    volume_step: float
    stops_level_points: float = 0.0
    point: float = 0.01


@dataclass(frozen=True)
class TradeProposal:
    signal: Signal
    symbol: str
    strategy_name: str
    strategy_version: str
    rules_fired: str = ""
    duplicate: bool = False


@dataclass(frozen=True)
class RiskCheckResult:
    approved: bool
    reason: RejectReason
    message: str
    lots: float = 0.0
    risk_amount: float = 0.0
    checks_passed: tuple[str, ...] = field(default_factory=tuple)
