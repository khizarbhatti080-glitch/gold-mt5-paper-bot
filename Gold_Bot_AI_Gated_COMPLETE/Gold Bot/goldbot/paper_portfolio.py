from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import Side, Signal


@dataclass
class PaperPosition:
    symbol: str
    side: str
    entry_time: str
    entry: float
    stop: float
    target: float | None
    risk_cash: float
    reason: str


class PortfolioPaperLedger:
    """Restart-safe virtual portfolio. It never calls the MT5 order API."""

    TRADE_FIELDS = (
        "symbol", "side", "entry_time", "exit_time", "entry", "exit", "stop",
        "target", "risk_cash", "pnl", "r_multiple", "exit_reason", "entry_reason",
    )

    def __init__(self, state_path: str, trades_path: str, initial_balance: float = 10_000.0):
        self.state_path = Path(state_path)
        self.trades_path = Path(trades_path)
        self.initial_balance = float(initial_balance)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.trades_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _fresh(self) -> dict:
        return {
            "version": "0.8.0", "created_at": datetime.now(timezone.utc).isoformat(),
            "initial_balance": self.initial_balance, "balance": self.initial_balance,
            "peak_balance": self.initial_balance, "max_drawdown_pct": 0.0,
            "open_positions": {}, "last_processed": {}, "daily": {},
            "pending_orders": {},
            "closed_trades": 0, "wins": 0, "losses": 0,
            "gross_profit": 0.0, "gross_loss": 0.0,
        }

    def _load(self) -> dict:
        if not self.state_path.exists():
            return self._fresh()
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        if data.get("version") != "0.8.0":
            raise ValueError(f"unsupported paper state version in {self.state_path}")
        data.setdefault("pending_orders", {})
        return data

    def save(self) -> None:
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.state, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.state_path)

    @staticmethod
    def _fill(price: float, side: Side, spread: float, slippage: float, entering: bool) -> float:
        adverse = spread / 2.0 + slippage
        return price + adverse if (side == Side.BUY) == entering else price - adverse

    def initialize_symbol(self, symbol: str, bar_time: datetime) -> None:
        """Begin forward observation without manufacturing a historical trade."""
        if symbol not in self.state["last_processed"]:
            self.state["last_processed"][symbol] = bar_time.isoformat()
            self.save()

    def process_bar(self, symbol: str, bar: dict, signal: Signal, *, risk_pct: float,
                    spread_price: float, slippage_price: float,
                    commission_per_trade: float, max_trades_per_day: int,
                    daily_loss_limit_pct: float, daily_profit_target_pct: float,
                    entry_allowed: bool = True, entry_block_reason: str = "",
                    require_ai_approval: bool = False, ai_approved: bool = False) -> list[dict]:
        stamp = bar["time"].isoformat()
        previous = self.state["last_processed"].get(symbol)
        if previous and stamp <= previous:
            return []
        events = []
        day_key = f"{symbol}:{bar['time'].date().isoformat()}"
        daily = self.state["daily"].setdefault(
            day_key, {"start_balance": self.state["balance"], "entries": 0,
                      "consecutive_losses": 0})
        position_data = self.state["open_positions"].get(symbol)

        # A signal based on this closed candle can first fill on a later candle.
        pending = self.state["pending_orders"].get(symbol)
        if pending and stamp > pending["created_at"]:
            pending["bars_waited"] += 1
            pending_side = Side(pending["side"])
            invalidated = (bar["close"] <= pending["stop"] if pending_side == Side.BUY
                           else bar["close"] >= pending["stop"])
            target_first = (pending["target"] is not None and
                            (bar["high"] >= pending["target"] if pending_side == Side.BUY
                             else bar["low"] <= pending["target"]))
            if (not entry_allowed or (require_ai_approval and not pending.get("ai_approved", False))
                    or pending["bars_waited"] > 4 or invalidated or target_first):
                events.append({"event": "VIRTUAL_PENDING_CANCELLED", "symbol": symbol,
                               "reason": (entry_block_reason if not entry_allowed else
                                          "ai_approval_missing" if require_ai_approval and not pending.get("ai_approved", False) else
                                          "four_bars_expired" if pending["bars_waited"] > 4 else
                                          "stop_invalidated" if invalidated else "target_reached_first")})
                del self.state["pending_orders"][symbol]
                pending = None

        if position_data:
            position = PaperPosition(**position_data)
            side = Side(position.side)
            stop_hit = bar["low"] <= position.stop if side == Side.BUY else bar["high"] >= position.stop
            target_hit = position.target is not None and (
                bar["high"] >= position.target if side == Side.BUY else bar["low"] <= position.target)
            opposite = signal.side not in (Side.HOLD, side)
            raw_exit = None
            reason = None
            if stop_hit:
                raw_exit, reason = position.stop, "stop_loss"
            elif target_hit:
                raw_exit, reason = position.target, "take_profit"
            elif opposite:
                raw_exit, reason = signal.entry or bar["open"], "opposite_signal"
            if raw_exit is not None:
                exit_price = self._fill(float(raw_exit), side, spread_price, slippage_price, False)
                unit_risk = abs(position.entry - position.stop)
                move = exit_price - position.entry if side == Side.BUY else position.entry - exit_price
                r_multiple = move / unit_risk if unit_risk else 0.0
                pnl = position.risk_cash * r_multiple - commission_per_trade
                self.state["balance"] += pnl
                self.state["closed_trades"] += 1
                if pnl > 0:
                    self.state["wins"] += 1
                    self.state["gross_profit"] += pnl
                    daily["consecutive_losses"] = 0
                elif pnl < 0:
                    self.state["losses"] += 1
                    self.state["gross_loss"] += abs(pnl)
                    daily["consecutive_losses"] = daily.get("consecutive_losses", 0) + 1
                self.state["peak_balance"] = max(self.state["peak_balance"], self.state["balance"])
                peak = self.state["peak_balance"]
                drawdown = 100 * (peak - self.state["balance"]) / peak if peak else 0.0
                self.state["max_drawdown_pct"] = max(self.state["max_drawdown_pct"], drawdown)
                trade = {
                    "symbol": symbol, "side": side.value, "entry_time": position.entry_time,
                    "exit_time": stamp, "entry": position.entry, "exit": exit_price,
                    "stop": position.stop, "target": position.target,
                    "risk_cash": position.risk_cash, "pnl": pnl,
                    "r_multiple": r_multiple, "exit_reason": reason,
                    "entry_reason": position.reason,
                }
                self._append_trade(trade)
                del self.state["open_positions"][symbol]
                events.append({"event": "VIRTUAL_EXIT", **trade})

        daily_return = 100 * (self.state["balance"] - daily["start_balance"]) / daily["start_balance"]
        locked = (daily["entries"] >= max_trades_per_day
                  or daily.get("consecutive_losses", 0) >= 2
                  or daily_return <= -daily_loss_limit_pct
                  or daily_return >= daily_profit_target_pct)
        if signal.side != Side.HOLD and (not entry_allowed or (require_ai_approval and not ai_approved)):
            events.append({"event": "VIRTUAL_ENTRY_REJECTED", "symbol": symbol,
                           "reason": (entry_block_reason or "news_gate_blocked") if not entry_allowed else "ai_not_approved"})
        if (symbol not in self.state["open_positions"] and not locked
                and entry_allowed and pending):
            pending_side = Side(pending["side"])
            raw_entry = pending["entry"]
            reached = bar["low"] <= raw_entry <= bar["high"]
            if reached:
                entry = self._fill(raw_entry, pending_side, spread_price, slippage_price, True)
                stop = pending["stop"]
                if (stop < entry if pending_side == Side.BUY else stop > entry):
                    position = PaperPosition(symbol, pending_side.value, stamp, entry, stop,
                                             pending["target"], self.state["balance"] * risk_pct / 100.0,
                                             pending["reason"])
                    self.state["open_positions"][symbol] = asdict(position)
                    daily["entries"] += 1
                    events.append({"event": "VIRTUAL_ENTRY", **asdict(position)})
                del self.state["pending_orders"][symbol]
        if (symbol not in self.state["open_positions"] and symbol not in self.state["pending_orders"]
                and not locked and entry_allowed and (not require_ai_approval or ai_approved)
                and signal.side != Side.HOLD):
            if signal.entry is not None and signal.stop_loss is not None:
                valid_stop = (signal.stop_loss < signal.entry if signal.side == Side.BUY
                              else signal.stop_loss > signal.entry)
                if valid_stop:
                    self.state["pending_orders"][symbol] = {
                        "side": signal.side.value, "entry": signal.entry, "stop": signal.stop_loss,
                        "target": signal.take_profit, "reason": signal.reason,
                        "created_at": stamp, "bars_waited": 0,
                        "ai_approved": bool(ai_approved) if require_ai_approval else False,
                    }
                    events.append({"event": "VIRTUAL_PENDING", "symbol": symbol,
                                   "entry": signal.entry, "created_at": stamp})

        self.state["last_processed"][symbol] = stamp
        self.save()
        return events

    def _append_trade(self, trade: dict) -> None:
        new_file = not self.trades_path.exists()
        with self.trades_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.TRADE_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow({key: trade.get(key) for key in self.TRADE_FIELDS})

    def summary(self) -> dict:
        total = int(self.state["closed_trades"])
        gross_loss = float(self.state["gross_loss"])
        profit_factor = (float(self.state["gross_profit"]) / gross_loss if gross_loss
                         else ("inf" if self.state["gross_profit"] else 0.0))
        return {
            "version": self.state["version"], "initial_balance": round(self.state["initial_balance"], 2),
            "balance": round(self.state["balance"], 2),
            "net_profit": round(self.state["balance"] - self.state["initial_balance"], 2),
            "return_pct": round(100 * (self.state["balance"] / self.state["initial_balance"] - 1), 4),
            "closed_trades": total, "wins": self.state["wins"], "losses": self.state["losses"],
            "win_rate_pct": round(100 * self.state["wins"] / total, 2) if total else 0.0,
            "profit_factor": round(profit_factor, 4) if isinstance(profit_factor, float) else profit_factor,
            "max_drawdown_pct": round(self.state["max_drawdown_pct"], 4),
            "open_positions": self.state["open_positions"],
            "pending_orders": self.state["pending_orders"],
            "state_file": str(self.state_path), "trades_file": str(self.trades_path),
        }
