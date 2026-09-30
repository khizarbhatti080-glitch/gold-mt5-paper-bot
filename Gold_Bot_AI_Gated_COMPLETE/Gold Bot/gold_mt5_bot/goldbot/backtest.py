from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime
from math import sqrt

from .models import Side


def load_bars(path: str) -> list[dict]:
    bars = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            bars.append({
                "time": datetime.fromisoformat(row["time"].replace("Z", "+00:00")),
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "spread": float(row.get("spread", 0) or 0),
            })
    return bars


@dataclass
class Trade:
    side: str
    entry_time: str
    exit_time: str
    entry: float
    exit: float
    stop: float
    pnl: float
    r_multiple: float
    exit_reason: str


def _fill(price: float, side: Side, spread: float, slippage: float, entering: bool) -> float:
    adverse = spread / 2.0 + slippage
    return price + adverse if (side == Side.BUY) == entering else price - adverse


def run_backtest(strategy, bars: list[dict], *, initial_balance: float = 10_000.0,
                 risk_pct: float = 0.5, spread_price: float = 0.0,
                 slippage_price: float = 0.0, commission_per_trade: float = 0.0,
                 point_size: float = 0.01, max_trades_per_day: int = 3,
                 daily_loss_limit_pct: float = 1.5,
                 daily_profit_target_pct: float = 2.0) -> dict:
    if hasattr(strategy, "reset"):
        strategy.reset()
    balance, peak, max_drawdown = initial_balance, initial_balance, 0.0
    position = None
    trades: list[Trade] = []
    daily = {}

    def close(side, entry_time, entry, stop, risk_cash, exit_price, when, reason):
        nonlocal balance, peak, max_drawdown
        unit_risk = abs(entry - stop)
        move = exit_price - entry if side == Side.BUY else entry - exit_price
        r = move / unit_risk if unit_risk else 0.0
        pnl = risk_cash * r - commission_per_trade
        balance += pnl
        peak = max(peak, balance)
        max_drawdown = max(max_drawdown, (peak - balance) / peak * 100 if peak else 0.0)
        trades.append(Trade(side.value, entry_time.isoformat(), when.isoformat(), entry,
                            exit_price, stop, pnl, r, reason))

    for i, bar in enumerate(bars):
        day = bar["time"].date()
        if day not in daily:
            daily[day] = {"start_balance": balance, "trades": 0}
        daily_pnl_pct = 100.0 * (balance - daily[day]["start_balance"]) / daily[day]["start_balance"]
        daily_locked = (daily[day]["trades"] >= max_trades_per_day
                        or daily_pnl_pct <= -daily_loss_limit_pct
                        or daily_pnl_pct >= daily_profit_target_pct)
        signal = strategy.on_bar(bar, bars[:i])
        spread_points = bar.get("spread", 0.0)
        spread = spread_points * point_size if spread_points else spread_price
        if position:
            side, entry_time, entry, stop, target, risk_cash = position
            stop_hit = bar["low"] <= stop if side == Side.BUY else bar["high"] >= stop
            target_hit = target is not None and (
                bar["high"] >= target if side == Side.BUY else bar["low"] <= target)
            if stop_hit:
                raw_exit, reason = stop, "stop_loss"
            elif target_hit:
                raw_exit, reason = target, "take_profit"
            elif signal.side not in (Side.HOLD, side):
                raw_exit, reason = signal.entry or bar["open"], "opposite_signal"
            else:
                raw_exit = None
            if raw_exit is not None:
                close(side, entry_time, entry, stop, risk_cash,
                      _fill(raw_exit, side, spread, slippage_price, False),
                      bar["time"], reason)
                position = None
                daily_pnl_pct = 100.0 * (
                    balance - daily[day]["start_balance"]) / daily[day]["start_balance"]
                daily_locked = (daily[day]["trades"] >= max_trades_per_day
                                or daily_pnl_pct <= -daily_loss_limit_pct
                                or daily_pnl_pct >= daily_profit_target_pct)

        if (position is None and not daily_locked and signal.side != Side.HOLD
                and signal.entry is not None and signal.stop_loss is not None):
            raw_entry = signal.entry
            reached = bar["high"] >= raw_entry if signal.side == Side.BUY else bar["low"] <= raw_entry
            valid_stop = signal.stop_loss < raw_entry if signal.side == Side.BUY else signal.stop_loss > raw_entry
            if reached and valid_stop:
                entry = _fill(raw_entry, signal.side, spread, slippage_price, True)
                position = (signal.side, bar["time"], entry, signal.stop_loss,
                            signal.take_profit, balance * risk_pct / 100.0)
                daily[day]["trades"] += 1

    if position and bars:
        side, entry_time, entry, stop, target, risk_cash = position
        spread_points = bars[-1].get("spread", 0.0)
        spread = spread_points * point_size if spread_points else spread_price
        close(side, entry_time, entry, stop, risk_cash,
              _fill(bars[-1]["close"], side, spread, slippage_price, False),
              bars[-1]["time"], "end_of_data")

    pnls = [t.pnl for t in trades]
    wins, losses = [p for p in pnls if p > 0], [p for p in pnls if p < 0]
    returns = [p / initial_balance for p in pnls]
    mean = sum(returns) / len(returns) if returns else 0.0
    variance = sum((x - mean) ** 2 for x in returns) / (len(returns) - 1) if len(returns) > 1 else 0.0
    profit_factor = sum(wins) / abs(sum(losses)) if losses else (float("inf") if wins else 0.0)
    return {
        "strategy": strategy.name, "strategy_version": strategy.version,
        "bars": len(bars), "trades": len(trades),
        "initial_balance": round(initial_balance, 2), "ending_balance": round(balance, 2),
        "net_profit": round(balance - initial_balance, 2),
        "return_pct": round((balance / initial_balance - 1) * 100, 4) if initial_balance else 0.0,
        "win_rate_pct": round(100 * len(wins) / len(trades), 2) if trades else 0.0,
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else "inf",
        "max_drawdown_pct": round(max_drawdown, 4),
        "average_r": round(sum(t.r_multiple for t in trades) / len(trades), 4) if trades else 0.0,
        "sharpe_per_trade": round(mean / sqrt(variance), 4) if variance > 0 else 0.0,
        "assumptions": {"risk_pct": risk_pct, "spread_price_fallback": spread_price,
                        "csv_spread_unit": "points", "point_size": point_size,
                        "max_trades_per_day": max_trades_per_day,
                        "daily_loss_limit_pct": daily_loss_limit_pct,
                        "daily_profit_target_pct": daily_profit_target_pct,
                        "slippage_price": slippage_price, "commission_per_trade": commission_per_trade,
                        "same_bar_priority": "stop_before_target"},
        "trades_detail": [asdict(t) for t in trades],
    }


def run_walk_forward(strategy_factory, bars: list[dict], *, split_ratio: float = 0.70,
                     gates: dict | None = None, **kwargs) -> dict:
    if not 0.5 <= split_ratio < 1.0:
        raise ValueError("split_ratio must be at least 0.5 and below 1.0")
    split = int(len(bars) * split_ratio)
    in_sample = run_backtest(strategy_factory(), bars[:split], **kwargs)
    out_of_sample = run_backtest(strategy_factory(), bars[split:], **kwargs)
    rules = gates or {}
    pf = out_of_sample["profit_factor"]
    pf_value = float("inf") if pf == "inf" else float(pf)
    checks = {
        "minimum_out_of_sample_trades": out_of_sample["trades"] >= int(
            rules.get("minimum_out_of_sample_trades", 100)),
        "minimum_profit_factor": pf_value >= float(rules.get("minimum_profit_factor", 1.2)),
        "maximum_drawdown": out_of_sample["max_drawdown_pct"] <= float(rules.get("maximum_drawdown_pct", 10)),
        "positive_out_of_sample": (
            out_of_sample["net_profit"] > 0
            if rules.get("require_positive_out_of_sample", True) else True),
    }
    return {"split_ratio": split_ratio, "split_index": split, "in_sample": in_sample,
            "out_of_sample": out_of_sample, "validation_checks": checks,
            "demo_eligible": all(checks.values())}
