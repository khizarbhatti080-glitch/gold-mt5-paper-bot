from __future__ import annotations
import argparse, time
from datetime import datetime, timezone
from goldbot.config import load_config, risk_config
from goldbot.models import DataQuality, Mode, Side, Signal, TradeProposal
from goldbot.mt5_adapter import MT5Adapter
from goldbot.risk import RiskManager
from goldbot.strategy import CandleBreakReversalStrategy

def in_session(cfg, now):
    sh, sm = map(int, cfg["session"]["start"].split(":"))
    eh, em = map(int, cfg["session"]["end"].split(":"))
    m = now.hour*60 + now.minute
    return sh*60+sm <= m < eh*60+em

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--demo-submit", action="store_true")
    a=p.parse_args()
    cfg=load_config(a.config)
    cfg=dict(cfg); cfg["enable_order_submission"]=bool(a.demo_submit)
    ad=MT5Adapter(cfg); ad.connect(); mt5=ad.mt5
    acct=mt5.account_info()
    demo=getattr(mt5,"ACCOUNT_TRADE_MODE_DEMO",0)
    if a.demo_submit and acct.trade_mode != demo:
        raise RuntimeError("BLOCKED: this runner submits orders only on an MT5 DEMO account")
    if a.demo_submit and not mt5.terminal_info().trade_allowed:
        raise RuntimeError("Enable Algo Trading in MT5 first")
    strat=CandleBreakReversalStrategy()
    rm=RiskManager(risk_config(cfg), cfg["paths"]["daily_state"])
    state=rm.load_or_start(float(acct.equity))
    symbol, tf, magic=cfg["symbol"],cfg["timeframe"],int(cfg["magic_number"])
    poll=float(cfg.get("poll_seconds",2)); last_key=None; seen_closed=set()
    print(f"GOLD MT5 DEMO RUNNER | {symbol} {tf} | account={acct.login}")
    print("DEMO ORDERS:", "ENABLED" if a.demo_submit else "MONITOR ONLY", "| Ctrl+C stops safely")
    try:
      while True:
        try:
          bars=ad.recent_bars(tf,4); prev,cur=bars[-2],bars[-1]
          tick=mt5.symbol_info_tick(symbol)
          now=datetime.now(timezone.utc)
          side=Side.HOLD; stop=None; reason="waiting"
          if prev["close"] < prev["open"] and tick.bid < prev["low"]:
              side=Side.SELL; stop=float(prev["high"]); reason="red_candle_break_low"
          elif prev["close"] > prev["open"] and tick.ask > prev["high"]:
              side=Side.BUY; stop=float(prev["low"]); reason="green_candle_break_high"
          positions=tuple(p for p in (mt5.positions_get(symbol=symbol) or ())
                          if int(getattr(p,"magic",0))==magic)
          if side==Side.HOLD:
              print(f"WAIT | {now:%H:%M:%S} | bid={tick.bid:.2f} ask={tick.ask:.2f} | positions={len(positions)}")
              time.sleep(poll); continue
          key=(cur["time"],side.value,prev["time"])
          if key==last_key: time.sleep(poll); continue

          # Close opposite bot position first (reversal rule).
          opposite=mt5.POSITION_TYPE_BUY if side==Side.SELL else mt5.POSITION_TYPE_SELL
          if a.demo_submit:
            for pos in [x for x in positions if int(x.type)==opposite]:
              typ=mt5.ORDER_TYPE_SELL if int(pos.type)==mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
              price=tick.bid if typ==mt5.ORDER_TYPE_SELL else tick.ask
              req={"action":mt5.TRADE_ACTION_DEAL,"symbol":symbol,"position":int(pos.ticket),
                   "volume":float(pos.volume),"type":typ,"price":float(price),
                   "deviation":int(cfg["execution"]["deviation_points"]),"magic":magic,
                   "comment":cfg["execution"]["comment"]+"-reverse",
                   "type_time":mt5.ORDER_TIME_GTC,"type_filling":mt5.ORDER_FILLING_IOC}
              print("REVERSE CLOSE |",mt5.order_send(req))
            time.sleep(.5)
          positions=tuple(p for p in (mt5.positions_get(symbol=symbol) or ())
                          if int(getattr(p,"magic",0))==magic)
          same=mt5.POSITION_TYPE_BUY if side==Side.BUY else mt5.POSITION_TYPE_SELL
          duplicate=any(int(x.type)==same for x in positions)
          entry=float(tick.ask if side==Side.BUY else tick.bid)
          sig=Signal(side,now,entry,stop,None,reason)
          prop=TradeProposal(sig,symbol,strat.name,strat.version,reason,duplicate)
          snap=ad.snapshot(); state=rm.load_or_start(snap.equity); spec=ad.symbol_spec()
          check=rm.evaluate(state=state,account=snap,proposal=prop,spec=spec,mode=Mode.PAPER,
              kill_switch_engaged=False,connection_healthy=ad.healthy(),
              data_quality=DataQuality.OK,market_open=True,in_session=in_session(cfg,now),
              current_total_lots=sum(float(x.volume) for x in positions))
          print(f"SIGNAL | {side.value} | entry={entry:.2f} SL={stop:.2f} | {check.reason.value} | {check.message}")
          last_key=key
          if check.approved:
            if a.demo_submit:
              result=ad.submit(sig,check.lots)
              print(f"DEMO ORDER | lots={check.lots} | result={result}")
            else: print(f"MONITOR | would submit {check.lots} lots")
          time.sleep(poll)
        except KeyboardInterrupt: raise
        except Exception as e:
          print(f"LOOP ERROR | {type(e).__name__}: {e}"); time.sleep(max(2,poll))
    except KeyboardInterrupt:
      print("\nSTOPPED SAFELY")
    finally: ad.close()

if __name__=="__main__": main()
