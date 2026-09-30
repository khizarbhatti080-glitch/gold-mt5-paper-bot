import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from .backtest import load_bars, run_walk_forward
from .config import load_config
from .mt5_adapter import MT5Adapter
from .kill_switch import KillSwitch
from .journal import TradeJournal
from .models import Side
from .strategy import build_strategy


def main() -> None:
    parser = argparse.ArgumentParser(description="Gold MT5 bot")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "run", "kill", "resume"):
        p = sub.add_parser(command)
        p.add_argument("--config", required=True)
    export = sub.add_parser("export-history")
    export.add_argument("--config", required=True)
    export.add_argument("--timeframe", choices=("M1", "M5", "M15", "M30", "H1", "H4"), required=True)
    export.add_argument("--bars", type=int, default=50000)
    export.add_argument("--output", required=True)
    symbols = sub.add_parser("find-symbol")
    symbols.add_argument("--config", required=True)
    symbols.add_argument("--query", required=True)
    portfolio_export = sub.add_parser("portfolio-export")
    portfolio_export.add_argument("--config", required=True)
    portfolio_export.add_argument("--bars", type=int, default=50000)
    portfolio_export.add_argument("--output-dir", default="data/portfolio")
    portfolio_backtest = sub.add_parser("portfolio-backtest")
    portfolio_backtest.add_argument("--config", required=True)
    portfolio_backtest.add_argument("--data-dir", default="data/portfolio")
    portfolio_backtest.add_argument("--output", default="portfolio_backtest.json")
    portfolio_observe = sub.add_parser("portfolio-observe")
    portfolio_observe.add_argument("--config", required=True)
    portfolio_observe.add_argument("--once", action="store_true")
    observe = sub.add_parser("observe")
    observe.add_argument("--config", required=True)
    observe.add_argument("--strategy", choices=("london_fvg_trend_v04",), required=True)
    observe.add_argument("--once", action="store_true")
    backtest = sub.add_parser("backtest")
    backtest.add_argument("--config", required=True)
    backtest.add_argument("--csv", required=True)
    backtest.add_argument("--strategy", choices=("candle_break_reversal", "london_fvg_inversion",
                                                  "london_fvg_trend_v04"),
                          required=True)
    backtest.add_argument("--split", type=float, default=0.70)
    args = parser.parse_args()
    cfg = load_config(args.config)
    if args.command == "portfolio-backtest":
        results = {}
        data_dir = Path(args.data_dir)
        for item in cfg.get("instruments", []):
            symbol = item["symbol"]
            csv_path = data_dir / f"{symbol.lower()}_{cfg['timeframe'].lower()}.csv"
            if not csv_path.exists():
                results[symbol] = {"error": f"missing history: {csv_path}"}
                continue
            bt = cfg.get("backtest", {})
            results[symbol] = run_walk_forward(
                lambda: build_strategy(cfg.get("strategy", "london_fvg_trend_v04")),
                load_bars(str(csv_path)), split_ratio=float(cfg.get("split_ratio", 0.70)),
                gates=cfg.get("validation_gates", {}),
                initial_balance=float(bt.get("initial_balance", 10000)),
                risk_pct=float(cfg["risk"]["risk_per_trade_pct"]),
                spread_price=float(item.get("spread_price_fallback", 0)),
                slippage_price=float(item.get("slippage_price", 0)),
                commission_per_trade=float(item.get("commission_per_trade", 0)),
                point_size=float(item.get("point_size", 0.01)),
                max_trades_per_day=int(cfg["risk"]["max_trades_per_day"]),
                daily_loss_limit_pct=float(cfg["risk"]["daily_loss_limit_pct"]),
                daily_profit_target_pct=float(cfg["risk"]["daily_profit_target_pct"]))
        approved = [name for name, value in results.items()
                    if isinstance(value, dict) and value.get("demo_eligible")]
        payload = {"strategy": cfg.get("strategy"), "results": results,
                   "approved_symbols": approved,
                   "portfolio_demo_eligible": bool(results) and len(approved) == len(results)}
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return
    if args.command in {"kill", "resume"}:
        switch = KillSwitch(cfg["paths"]["kill_switch"])
        state = switch.engage("manual CLI emergency stop") if args.command == "kill" else switch.resume("manual CLI resume")
        print(json.dumps(state.__dict__, indent=2))
        return
    if args.command == "backtest":
        bt = cfg.get("backtest", {})
        result = run_walk_forward(lambda: build_strategy(args.strategy), load_bars(args.csv),
                                  split_ratio=args.split, gates=cfg.get("validation_gates", {}),
                                  initial_balance=float(bt.get("initial_balance", 10000)),
                                  risk_pct=float(cfg["risk"]["risk_per_trade_pct"]),
                                  spread_price=float(bt.get("spread_price_fallback", 0)),
                                  slippage_price=float(bt.get("slippage_price", 0)),
                                  commission_per_trade=float(bt.get("commission_per_trade", 0)),
                                  point_size=float(bt.get("point_size", 0.01)),
                                  max_trades_per_day=int(cfg["risk"]["max_trades_per_day"]),
                                  daily_loss_limit_pct=float(cfg["risk"]["daily_loss_limit_pct"]),
                                  daily_profit_target_pct=float(cfg["risk"]["daily_profit_target_pct"]))
        print(json.dumps(result, indent=2))
        return
    broker = MT5Adapter(cfg)
    broker.connect()
    try:
        if args.command == "export-history":
            count = broker.export_bars(args.timeframe, args.bars, args.output)
            print(json.dumps({"exported_bars": count, "output": args.output}, indent=2))
            return
        if args.command == "find-symbol":
            print(json.dumps({"query": args.query, "matches": broker.find_symbols(args.query)}, indent=2))
            return
        if args.command == "portfolio-export":
            exported = {}
            out = Path(args.output_dir)
            for item in cfg.get("instruments", []):
                symbol = item["symbol"]
                path = out / f"{symbol.lower()}_{cfg['timeframe'].lower()}.csv"
                try:
                    exported[symbol] = {
                        "bars": broker.export_bars(cfg["timeframe"], args.bars, str(path), symbol),
                        "output": str(path),
                    }
                except Exception as exc:
                    exported[symbol] = {"error": str(exc)}
            print(json.dumps(exported, indent=2))
            return
        if args.command == "portfolio-observe":
            if cfg["mode"] != "paper" or cfg.get("enable_order_submission", False):
                raise SystemExit("Portfolio observation requires mode: paper and enable_order_submission: false.")
            states = {item["symbol"]: {"strategy": build_strategy(cfg.get("strategy", "london_fvg_trend_v04")),
                                               "last": None}
                      for item in cfg.get("instruments", []) if item.get("enabled", True)}
            while True:
                for symbol, state in states.items():
                    try:
                        bars = broker.recent_bars(cfg["timeframe"], 500, symbol)[:-1]
                        if bars[-1]["time"] == state["last"]:
                            continue
                        strategy = build_strategy(cfg.get("strategy", "london_fvg_trend_v04"))
                        latest = None
                        for index, bar in enumerate(bars):
                            signal = strategy.on_bar(bar, bars[:index])
                            if signal.side != Side.HOLD:
                                latest = signal
                        state["last"] = bars[-1]["time"]
                        current = latest if latest and latest.timestamp == state["last"] else None
                        signal_payload = asdict(current) if current else None
                        if signal_payload:
                            signal_payload["side"] = signal_payload["side"].value
                            signal_payload["timestamp"] = signal_payload["timestamp"].isoformat()
                        print(json.dumps({"mode": "portfolio-paper-signal-only", "symbol": symbol,
                                          "closed_bar_time": state["last"].isoformat(),
                                          "signal": signal_payload, "order_submission": False}))
                    except Exception as exc:
                        print(json.dumps({"symbol": symbol, "error": str(exc)}))
                if args.once:
                    return
                time.sleep(max(2, int(cfg.get("poll_seconds", 2))))
        if args.command == "observe":
            if cfg["mode"] != "paper":
                raise SystemExit("Observation requires mode: paper in config.yaml.")
            if cfg.get("enable_order_submission", False):
                raise SystemExit("Signal-only observation requires enable_order_submission: false.")
            journal = TradeJournal(cfg["paths"]["journal"])
            last_closed_time = None
            while True:
                bars = broker.recent_bars(cfg["timeframe"], 500)
                closed = bars[:-1]
                if closed[-1]["time"] != last_closed_time:
                    strategy = build_strategy(args.strategy)
                    latest = None
                    for index, bar in enumerate(closed):
                        signal = strategy.on_bar(bar, closed[:index])
                        if signal.side != Side.HOLD:
                            latest = signal
                    last_closed_time = closed[-1]["time"]
                    payload = {
                        "mode": "paper-signal-only", "symbol": cfg["symbol"],
                        "closed_bar_time": last_closed_time.isoformat(),
                        "signal": asdict(latest) if latest and latest.timestamp == last_closed_time else None,
                        "order_submission": False,
                    }
                    if payload["signal"]:
                        payload["signal"]["side"] = payload["signal"]["side"].value
                        payload["signal"]["timestamp"] = payload["signal"]["timestamp"].isoformat()
                    print(json.dumps(payload, indent=2))
                    journal.record_decision({
                        "mode": "paper", "symbol": cfg["symbol"],
                        "action": payload["signal"]["side"] if payload["signal"] else "HOLD",
                        "decision": "OBSERVED", "reject_reason_code": "ORDER_SUBMISSION_DISABLED",
                        "strategy_name": args.strategy, "strategy_version": "0.4.0-experimental",
                        "rules_fired": payload["signal"]["reason"] if payload["signal"] else "no_signal",
                    })
                if args.once:
                    return
                time.sleep(max(2, int(cfg.get("poll_seconds", 2))))
        print(broker.snapshot())
        print({"healthy": broker.healthy(), "symbol_spec": broker.symbol_spec()})
        if args.command == "run":
            raise SystemExit("Runner locked: backtest gates and demo approval are not yet satisfied.")
    finally:
        broker.close()


if __name__ == "__main__":
    main()
