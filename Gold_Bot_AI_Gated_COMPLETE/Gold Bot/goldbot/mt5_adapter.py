from datetime import datetime, timezone
import csv

from .models import AccountSnapshot, Side, SymbolSpec


class MT5Adapter:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.mt5 = None

    def connect(self) -> None:
        import MetaTrader5 as mt5
        terminal_path = self.cfg.get("mt5_terminal_path")
        connected = mt5.initialize(path=terminal_path) if terminal_path else mt5.initialize()
        if not connected:
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        self.mt5 = mt5
        if not mt5.symbol_select(self.cfg["symbol"], True):
            raise RuntimeError(f"Cannot select symbol {self.cfg['symbol']}")

    def select_symbol(self, symbol: str) -> None:
        if not self.mt5.symbol_select(symbol, True):
            raise RuntimeError(f"Cannot select symbol {symbol}")

    def close(self) -> None:
        if self.mt5:
            self.mt5.shutdown()

    def snapshot(self) -> AccountSnapshot:
        account = self.mt5.account_info()
        tick = self.mt5.symbol_info_tick(self.cfg["symbol"])
        info = self.mt5.symbol_info(self.cfg["symbol"])
        positions = self.mt5.positions_get(symbol=self.cfg["symbol"]) or ()
        spread = (tick.ask - tick.bid) / info.point
        return AccountSnapshot(account.equity, account.balance, len(positions), spread)

    def healthy(self) -> bool:
        return bool(self.mt5 and self.mt5.terminal_info() and self.mt5.account_info())

    def symbol_spec(self) -> SymbolSpec:
        info = self.mt5.symbol_info(self.cfg["symbol"])
        return SymbolSpec(
            tick_size=float(info.trade_tick_size), tick_value=float(info.trade_tick_value),
            volume_min=float(info.volume_min), volume_max=float(info.volume_max),
            volume_step=float(info.volume_step), stops_level_points=float(info.trade_stops_level),
            point=float(info.point),
        )

    def find_symbols(self, query: str) -> list[dict]:
        """Return broker symbols containing query (for suffix/prefix discovery)."""
        needle = query.upper().strip()
        matches = []
        for info in self.mt5.symbols_get() or ():
            name = str(info.name)
            description = str(getattr(info, "description", ""))
            if needle in name.upper() or needle in description.upper():
                matches.append({
                    "name": name,
                    "description": description,
                    "visible": bool(getattr(info, "visible", False)),
                    "point": float(getattr(info, "point", 0.0)),
                })
        return matches

    def export_bars(self, timeframe: str, count: int, output_path: str,
                    symbol: str | None = None) -> int:
        mapping = {
            "M1": self.mt5.TIMEFRAME_M1, "M5": self.mt5.TIMEFRAME_M5,
            "M15": self.mt5.TIMEFRAME_M15, "M30": self.mt5.TIMEFRAME_M30,
            "H1": self.mt5.TIMEFRAME_H1, "H4": self.mt5.TIMEFRAME_H4,
        }
        if timeframe not in mapping:
            raise ValueError(f"unsupported timeframe: {timeframe}")
        selected = symbol or self.cfg["symbol"]
        self.select_symbol(selected)
        rates = self.mt5.copy_rates_from_pos(selected, mapping[timeframe], 0, count)
        if rates is None or len(rates) < 2:
            raise RuntimeError(f"MT5 returned insufficient history: {self.mt5.last_error()}")
        from pathlib import Path
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(("time", "open", "high", "low", "close", "tick_volume", "spread"))
            for row in rates:
                stamp = datetime.fromtimestamp(int(row["time"]), tz=timezone.utc).isoformat()
                writer.writerow((stamp, row["open"], row["high"], row["low"], row["close"],
                                 row["tick_volume"], row["spread"]))
        return len(rates)

    def recent_bars(self, timeframe: str, count: int = 500,
                    symbol: str | None = None) -> list[dict]:
        mapping = {
            "M1": self.mt5.TIMEFRAME_M1, "M5": self.mt5.TIMEFRAME_M5,
            "M15": self.mt5.TIMEFRAME_M15, "M30": self.mt5.TIMEFRAME_M30,
            "H1": self.mt5.TIMEFRAME_H1, "H4": self.mt5.TIMEFRAME_H4,
        }
        if timeframe not in mapping:
            raise ValueError(f"unsupported timeframe: {timeframe}")
        selected = symbol or self.cfg["symbol"]
        self.select_symbol(selected)
        rates = self.mt5.copy_rates_from_pos(selected, mapping[timeframe], 0, count)
        if rates is None or len(rates) < 3:
            raise RuntimeError(f"MT5 returned insufficient recent bars: {self.mt5.last_error()}")
        return [{
            "time": datetime.fromtimestamp(int(row["time"]), tz=timezone.utc),
            "open": float(row["open"]), "high": float(row["high"]),
            "low": float(row["low"]), "close": float(row["close"]),
            "spread": float(row["spread"]),
        } for row in rates]

    def submit(self, signal: "Signal", lot: float):
        if not self.cfg.get("enable_order_submission", False):
            return {"submitted": False, "reason": "order submission disabled"}
        if self.cfg["mode"] not in {"paper", "live"}:
            raise RuntimeError("orders are prohibited in backtest mode")
        if signal.stop_loss is None or signal.stop_loss <= 0:
            raise RuntimeError("execution rejected: stop-loss is required")
        tick = self.mt5.symbol_info_tick(self.cfg["symbol"])
        order_type = self.mt5.ORDER_TYPE_BUY if signal.side == Side.BUY else self.mt5.ORDER_TYPE_SELL
        price = tick.ask if signal.side == Side.BUY else tick.bid
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL, "symbol": self.cfg["symbol"],
            "volume": lot, "type": order_type, "price": price,
            "sl": signal.stop_loss, "tp": signal.take_profit,
            "deviation": self.cfg["execution"]["deviation_points"],
            "magic": self.cfg["magic_number"], "comment": self.cfg["execution"]["comment"],
            "type_time": self.mt5.ORDER_TIME_GTC, "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        return self.mt5.order_send(request)
