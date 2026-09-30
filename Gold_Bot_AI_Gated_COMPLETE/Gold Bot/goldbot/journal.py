from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


FIELDS = (
    "timestamp_utc", "timestamp_broker", "mode", "symbol", "strategy_name",
    "strategy_version", "action", "decision", "reject_reason_code",
    "entry_price", "stop_loss", "take_profit", "lots", "risk_amount",
    "risk_pct", "rules_fired", "spread_at_decision", "equity_before",
    "fill_price", "slippage", "commission", "swap", "exit_price",
    "exit_reason", "pnl", "r_multiple", "mfe", "mae", "duration",
    "daily_target_hit", "locks_active",
)


class TradeJournal:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init_db(self) -> None:
        columns = ", ".join(f"{field} TEXT" for field in FIELDS)
        with self._connect() as conn:
            conn.execute(f"CREATE TABLE IF NOT EXISTS trade_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, {columns})")
            conn.execute("CREATE TABLE IF NOT EXISTS system_events (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp_utc TEXT NOT NULL, event TEXT NOT NULL, payload_json TEXT NOT NULL)")

    def record_decision(self, record: dict) -> int:
        body = dict(record)
        body.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
        values = [self._encode(body.get(field)) for field in FIELDS]
        placeholders = ",".join("?" for _ in FIELDS)
        with self._connect() as conn:
            cursor = conn.execute(f"INSERT INTO trade_journal ({','.join(FIELDS)}) VALUES ({placeholders})", values)
            return int(cursor.lastrowid)

    def event(self, name: str, payload: dict) -> int:
        with self._connect() as conn:
            cursor = conn.execute("INSERT INTO system_events (timestamp_utc,event,payload_json) VALUES (?,?,?)",
                                  (datetime.now(timezone.utc).isoformat(), name,
                                   json.dumps(payload, default=str, sort_keys=True)))
            return int(cursor.lastrowid)

    @staticmethod
    def _encode(value):
        if isinstance(value, (dict, list, tuple, set)):
            return json.dumps(value, default=str, sort_keys=True)
        if value is None:
            return None
        return str(value)
