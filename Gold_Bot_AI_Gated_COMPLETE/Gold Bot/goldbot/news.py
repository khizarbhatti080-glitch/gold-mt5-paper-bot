"""Fail-closed USD economic-calendar entry gate for XAUUSD paper observation.

Feed JSON schema: {"generated_at":"2026-09-24T12:00:00Z", "events":
[{"time":"2026-09-24T13:30:00Z", "currency":"USD", "impact":"high", "title":"US CPI"}]}.
Timestamps must include a UTC offset. This is a calendar, not headline sentiment.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


MAJOR = ("cpi", "consumer price index", "nonfarm", "non-farm", "nfp",
         "fomc", "fed rate", "federal funds", "powell", "fed press conference")
FOREX_FACTORY_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def _date(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("calendar timestamps require an explicit UTC offset")
    return result.astimezone(timezone.utc)


def _trading_economics(now: datetime) -> dict:
    """Fetch high-importance US events; TE documents Date as UTC without an offset."""
    key = os.environ.get("TRADING_ECONOMICS_API_KEY", "").strip()
    if not key:
        raise ValueError("TRADING_ECONOMICS_API_KEY is missing")
    start = (now - timedelta(days=1)).date().isoformat()
    end = (now + timedelta(days=2)).date().isoformat()
    url = ("https://api.tradingeconomics.com/calendar/country/united%20states/"
           f"{start}/{end}?c={quote(key, safe='')}&importance=3&f=json")
    req = Request(url, headers={"User-Agent": "GoldBot-Paper-NewsGate/1.0"})
    with urlopen(req, timeout=8) as response:
        if response.status != 200:
            raise ValueError("calendar HTTP status not 200")
        body = response.read(1_000_001)
    if len(body) > 1_000_000:
        raise ValueError("calendar feed too large")
    raw = json.loads(body)
    if not isinstance(raw, list) or not raw:
        raise ValueError("calendar returned no events")
    events = []
    for row in raw:
        if not isinstance(row, dict) or not all(k in row for k in ("Date", "Event", "Importance", "Country")):
            raise ValueError("calendar returned incomplete events")
        if str(row["Country"]).lower() != "united states":
            continue
        date = str(row["Date"])
        stamp = _date(date if date.endswith("Z") or "+" in date[10:] else date + "Z")
        events.append({"time": stamp.isoformat(), "currency": "USD",
                       "impact": "high" if int(row["Importance"]) == 3 else "low",
                       "title": str(row["Event"])})
    if not events:
        raise ValueError("calendar returned no US events")
    return {"generated_at": now.isoformat(), "events": events}


def _forex_factory(now: datetime) -> dict:
    """Use Forex Factory's public weekly JSON export, with offset-aware dates."""
    req = Request(FOREX_FACTORY_URL, headers={"User-Agent": "GoldBot-Paper-NewsGate/1.0"})
    with urlopen(req, timeout=8) as response:
        if response.status != 200:
            raise ValueError("calendar HTTP status not 200")
        body = response.read(1_000_001)
    if len(body) > 1_000_000:
        raise ValueError("calendar feed too large")
    raw = json.loads(body)
    if not isinstance(raw, list) or not raw:
        raise ValueError("weekly calendar missing events")
    events = []
    event_times = []
    for row in raw:
        if not isinstance(row, dict) or not all(k in row for k in ("date", "country", "impact", "title")):
            raise ValueError("weekly calendar contains incomplete event")
        when = _date(row["date"])
        event_times.append(when)
        if str(row["country"]).upper() == "USD":
            events.append({"time": when.isoformat(), "currency": "USD",
                           "impact": str(row["impact"]).lower(), "title": str(row["title"])})
    if not min(event_times) - timedelta(days=1) <= now <= max(event_times) + timedelta(days=1):
        raise ValueError("weekly calendar outside current week")
    if not events:
        raise ValueError("weekly calendar missing USD events")
    return {"generated_at": now.isoformat(), "events": events}


def entry_decision(config: dict, now: datetime) -> tuple[bool, str]:
    """Return (entry_permitted, reason). Exceptions block new entries."""
    if not config.get("enabled", False):
        return False, "news_gate_not_enabled"
    if now.tzinfo is None:
        return False, "news_gate_clock_missing_timezone"
    now = now.astimezone(timezone.utc)
    try:
        source = config["source"]
        if source == "forexfactory":
            feed = _forex_factory(now)
        elif source == "tradingeconomics":
            feed = _trading_economics(now)
        elif source.startswith("https://"):
            req = Request(source, headers={"User-Agent": "GoldBot-Paper-NewsGate/1.0"})
            with urlopen(req, timeout=8) as response:
                if response.status != 200:
                    raise ValueError("calendar HTTP status not 200")
                body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise ValueError("calendar feed too large")
            feed = json.loads(body)
        else:
            feed = json.loads(Path(source).read_text(encoding="utf-8"))
        generated = _date(feed["generated_at"])
        max_age = timedelta(minutes=int(config.get("max_age_minutes", 360)))
        if generated > now + timedelta(minutes=5) or now - generated > max_age:
            return False, "news_calendar_stale"
        events = feed["events"]
        if not isinstance(events, list):
            raise ValueError("events must be a list")
        for event in events:
            if not all(key in event for key in ("time", "currency", "impact", "title")):
                raise ValueError("incomplete calendar event")
            when = _date(event["time"])
            if str(event["currency"]).strip().upper() != "USD":
                continue
            if str(event["impact"]).strip().lower() not in ("high", "3"):
                continue
            title = str(event["title"]).lower()
            minutes = int(config.get("major_buffer_minutes", 60) if any(term in title for term in MAJOR)
                          else config.get("high_buffer_minutes", 30))
            if abs(now - when) <= timedelta(minutes=minutes):
                return False, f"usd_news_blackout:{event['title']}:{when.isoformat()}"
        return True, "usd_calendar_clear"
    except (OSError, ValueError, KeyError, TypeError, TimeoutError, json.JSONDecodeError) as exc:
        return False, f"news_calendar_unavailable:{type(exc).__name__}"
