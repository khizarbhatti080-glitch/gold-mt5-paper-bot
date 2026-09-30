from dataclasses import asdict, dataclass
from datetime import date
import json
import math
from pathlib import Path

from .config import RiskConfig
from .models import AccountSnapshot, DataQuality, Mode, RejectReason, RiskCheckResult, SymbolSpec, TradeProposal


@dataclass
class DailyState:
    date: str
    start_equity: float
    equity_peak: float
    trades: int = 0
    consecutive_losses: int = 0
    locked: bool = False
    lock_reason: str = ""
    target_would_have_hit: bool = False


class RiskManager:
    def __init__(self, cfg: RiskConfig, state_path: str):
        self.cfg = cfg
        self.path = Path(state_path)

    def load_or_start(self, equity: float, today: date | None = None) -> DailyState:
        key = (today or date.today()).isoformat()
        if self.path.exists():
            state = DailyState(**json.loads(self.path.read_text(encoding="utf-8")))
            if state.date == key:
                state.equity_peak = max(state.equity_peak, equity)
                self.save(state)
                return state
        state = DailyState(date=key, start_equity=equity, equity_peak=equity)
        self.save(state)
        return state

    def save(self, state: DailyState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
        temp.replace(self.path)

    @staticmethod
    def size_multiplier(drawdown_pct: float = 0.0, volatility_ratio: float = 1.0,
                        consecutive_losses: int = 0) -> float:
        multiplier = 1.0
        if drawdown_pct > 0:
            multiplier *= max(0.25, 1.0 - drawdown_pct / 10.0)
        if volatility_ratio > 1.0:
            multiplier *= max(0.5, 1.0 / volatility_ratio)
        if consecutive_losses > 0:
            multiplier *= max(0.25, 1.0 - 0.2 * consecutive_losses)
        return min(1.0, max(0.0, multiplier))

    def position_size(self, equity: float, entry: float, stop_loss: float,
                      spec: SymbolSpec, multiplier: float = 1.0) -> tuple[float, float]:
        if stop_loss is None or stop_loss <= 0:
            raise ValueError("stop-loss is required")
        if entry <= 0 or spec.tick_size <= 0 or spec.tick_value <= 0 or spec.volume_step <= 0:
            raise ValueError("invalid price or broker symbol specification")
        stop_distance = abs(entry - stop_loss)
        stop_points = stop_distance / spec.point
        if not self.cfg.min_stop_points <= stop_points <= self.cfg.max_stop_points:
            raise ValueError("stop distance outside configured bounds")
        if stop_points < spec.stops_level_points:
            raise ValueError("stop distance is below broker stops level")
        risk_amount = equity * self.cfg.risk_per_trade_pct / 100.0
        risk_amount *= min(1.0, max(0.0, multiplier))
        loss_per_lot = (stop_distance / spec.tick_size) * spec.tick_value
        raw_lots = risk_amount / loss_per_lot
        lots = math.floor((raw_lots + 1e-12) / spec.volume_step) * spec.volume_step
        cap = min(spec.volume_max, self.cfg.max_lot, self.cfg.max_total_lots)
        lots = min(lots, cap)
        if lots + 1e-12 < spec.volume_min:
            raise ValueError("calculated lot is below broker minimum")
        return round(lots, 8), risk_amount

    def evaluate(self, *, state: DailyState, account: AccountSnapshot,
                 proposal: TradeProposal, spec: SymbolSpec, mode: Mode,
                 kill_switch_engaged: bool, connection_healthy: bool,
                 data_quality: DataQuality, market_open: bool,
                 in_session: bool, news_blocked: bool = False,
                 current_total_lots: float = 0.0) -> RiskCheckResult:
        checks: list[str] = []

        def reject(code: RejectReason, message: str) -> RiskCheckResult:
            return RiskCheckResult(False, code, message, checks_passed=tuple(checks))

        if kill_switch_engaged:
            return reject(RejectReason.KILL_SWITCH, "kill switch engaged")
        checks.append("kill_switch")
        if not connection_healthy:
            return reject(RejectReason.CONNECTION_UNHEALTHY, "MT5 connection unhealthy")
        checks.append("connection")
        if data_quality != DataQuality.OK:
            return reject(RejectReason.DATA_QUALITY, "market data quality degraded")
        checks.append("data_quality")
        if not market_open:
            return reject(RejectReason.MARKET_CLOSED, "symbol is not tradable")
        checks.append("market_open")

        state.equity_peak = max(state.equity_peak, account.equity)
        pnl_pct = 100.0 * (account.equity - state.start_equity) / state.start_equity
        drawdown_pct = 100.0 * (state.equity_peak - account.equity) / state.equity_peak
        if state.locked:
            return reject(RejectReason.DAILY_LOSS, state.lock_reason or "daily lock active")
        if pnl_pct <= -self.cfg.daily_loss_limit_pct:
            return self._lock(state, RejectReason.DAILY_LOSS, f"daily loss limit reached ({pnl_pct:.2f}%)", checks)
        checks.append("daily_loss")
        if pnl_pct >= self.cfg.daily_profit_target_pct:
            state.target_would_have_hit = True
            self.save(state)
            if mode == Mode.LIVE:
                return self._lock(state, RejectReason.DAILY_PROFIT, f"daily profit target reached ({pnl_pct:.2f}%)", checks)
        checks.append("daily_profit")
        if drawdown_pct >= self.cfg.emergency_drawdown_pct:
            return self._lock(state, RejectReason.EMERGENCY_DRAWDOWN, f"emergency drawdown reached ({drawdown_pct:.2f}%)", checks)
        checks.append("drawdown")
        if state.consecutive_losses >= self.cfg.consecutive_loss_limit:
            return self._lock(state, RejectReason.CONSECUTIVE_LOSSES, "consecutive-loss limit reached", checks)
        checks.append("loss_streak")

        signal = proposal.signal
        if signal.stop_loss is None or signal.stop_loss <= 0:
            return reject(RejectReason.MISSING_STOP, "trade has no valid stop-loss")
        checks.append("stop_present")
        if account.spread_points > self.cfg.max_spread_points:
            return reject(RejectReason.SPREAD, "spread exceeds configured maximum")
        checks.append("spread")
        if not in_session or news_blocked:
            return reject(RejectReason.OUT_OF_SESSION, "outside permitted session or news blackout active")
        checks.append("session")
        if proposal.duplicate:
            return reject(RejectReason.DUPLICATE_ENTRY, "duplicate or overlapping entry")
        checks.append("duplicate")
        if state.trades >= self.cfg.max_trades_per_day:
            return self._lock(state, RejectReason.MAX_TRADES, "maximum daily trades reached", checks)
        checks.append("trade_count")
        if account.open_positions >= self.cfg.max_open_positions:
            return reject(RejectReason.MAX_POSITIONS, "maximum open positions reached")
        checks.append("open_positions")

        multiplier = self.size_multiplier(drawdown_pct, 1.0, state.consecutive_losses)
        try:
            lots, risk_amount = self.position_size(account.equity, signal.entry or 0.0,
                                                   signal.stop_loss, spec, multiplier)
        except ValueError as exc:
            reason = RejectReason.BELOW_MIN_LOT if "minimum" in str(exc) else RejectReason.INVALID_STOP
            return reject(reason, str(exc))
        if current_total_lots + lots > self.cfg.max_total_lots + 1e-12:
            return reject(RejectReason.EXPOSURE, "total exposure cap exceeded")
        checks.extend(("position_size", "exposure"))
        self.save(state)
        return RiskCheckResult(True, RejectReason.APPROVED, "all risk checks passed",
                               lots, risk_amount, tuple(checks))

    def _lock(self, state: DailyState, code: RejectReason, message: str,
              checks: list[str]) -> RiskCheckResult:
        state.locked = True
        state.lock_reason = message
        self.save(state)
        return RiskCheckResult(False, code, message, checks_passed=tuple(checks))

    def record_closed_trade(self, state: DailyState, pnl: float) -> None:
        state.trades += 1
        state.consecutive_losses = state.consecutive_losses + 1 if pnl < 0 else 0
        self.save(state)
