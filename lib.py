"""Shared utilities — algorithms match the trading dashboard exactly."""
from __future__ import annotations
import json
import os
import smtplib
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yfinance as yf


# ─── Watchlist ──────────────────────────────────────────────────────────────
def load_watchlist(path: str = "watchlist.txt") -> list[str]:
    tickers = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            tickers.append(line.upper())
    return tickers


# ─── Indicators — ported from dashboard JavaScript ──────────────────────────
def calc_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gA = lA = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gA += d
        else:
            lA -= d
    gA /= period
    lA /= period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        gA = (gA * (period - 1) + (d if d > 0 else 0)) / period
        lA = (lA * (period - 1) + (-d if d < 0 else 0)) / period
    if lA == 0:
        return 100.0
    return 100 - (100 / (1 + gA / lA))


def ema_last(arr: list[float], period: int) -> float | None:
    if len(arr) < period:
        return None
    k = 2 / (period + 1)
    e = sum(arr[:period]) / period
    for i in range(period, len(arr)):
        e = arr[i] * k + e * (1 - k)
    return e


def find_sr(highs: list[float], lows: list[float], price: float, win: int = 2) -> dict:
    levs = []
    n = len(highs)
    for i in range(win, n - win):
        window_h = highs[i - win : i + win + 1]
        window_l = lows[i - win : i + win + 1]
        if highs[i] == max(window_h):
            levs.append({"p": highs[i], "type": "r"})
        if lows[i] == min(window_l):
            levs.append({"p": lows[i], "type": "s"})

    levs.sort(key=lambda x: x["p"])
    cl: list[dict] = []
    for lv in levs:
        existing = next((c for c in cl if abs(c["p"] - lv["p"]) / lv["p"] < 0.012), None)
        if existing:
            existing["cnt"] += 1
            existing["p"] = (existing["p"] + lv["p"]) / 2
        else:
            cl.append({**lv, "cnt": 1})

    for lv in cl:
        touches = 0
        for i in range(n):
            near_low = abs(lows[i] - lv["p"]) / lv["p"] < 0.008
            near_high = abs(highs[i] - lv["p"]) / lv["p"] < 0.008
            if near_low or near_high:
                touches += 1
        lv["touches"] = touches
        lv["strength"] = "strong" if touches >= 3 else ("moderate" if touches == 2 else "weak")
        lv["strengthScore"] = 3 if touches >= 3 else (2 if touches == 2 else 1)

    supports = sorted([x for x in cl if x["type"] == "s" and x["p"] < price], key=lambda x: -x["p"])[:3]
    resistances = sorted([x for x in cl if x["type"] == "r" and x["p"] > price], key=lambda x: x["p"])[:3]
    return {"sup": supports, "res": resistances}


def nearest_support(sr: dict) -> dict | None:
    if not sr["sup"]:
        return None
    return max(sr["sup"], key=lambda s: (s["strengthScore"], s["p"]))


def nearest_resistance(sr: dict) -> dict | None:
    if not sr["res"]:
        return None
    return max(sr["res"], key=lambda r: (r["strengthScore"], -r["p"]))


# ─── Ticker data ────────────────────────────────────────────────────────────
def fetch_ticker(ticker: str) -> dict | None:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="6mo", interval="1d", auto_adjust=False)
        if hist.empty or len(hist) < 50:
            return None

        closes = hist["Close"].tolist()
        highs = hist["High"].tolist()
        lows = hist["Low"].tolist()
        current_price = float(closes[-1])

        rsi = calc_rsi(closes, 14)
        ema_20 = ema_last(closes, 20)
        ema_50 = ema_last(closes, 50)

        recent = min(100, len(closes))
        sr = find_sr(highs[-recent:], lows[-recent:], current_price)
        sup = nearest_support(sr)
        res = nearest_resistance(sr)
        support_major = sup["p"] if sup else min(lows[-60:])
        resistance_major = res["p"] if res else max(highs[-60:])
        support_strength = sup["strength"] if sup else "weak"
        resistance_strength = res["strength"] if res else "weak"

        # Earnings — UPCOMING only.
        next_earnings_days: int | None = None
        today = datetime.now(timezone.utc).date()
        try:
            cal = t.calendar
            candidates: list = []
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if isinstance(ed, list):
                    candidates = list(ed)
                elif ed is not None:
                    candidates = [ed]
            elif hasattr(cal, "loc") and hasattr(cal, "index") and "Earnings Date" in cal.index:
                ed = cal.loc["Earnings Date"]
                if hasattr(ed, "tolist"):
                    try:
                        candidates = list(ed.tolist())
                    except Exception:
                        candidates = [ed]
                else:
                    candidates = [ed]
            upcoming: list = []
            for d in candidates:
                try:
                    if hasattr(d, "date"):
                        d = d.date()
                    if d >= today:
                        upcoming.append(d)
                except Exception:
                    continue
            upcoming.sort()
            if upcoming:
                next_earnings_days = (upcoming[0] - today).days
        except Exception:
            pass

        if next_earnings_days is None:
            try:
                info = t.info or {}
                ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
                if ts:
                    ed = datetime.fromtimestamp(ts, tz=timezone.utc).date()
                    if ed >= today:
                        next_earnings_days = (ed - today).days
            except Exception:
                pass

        return {
            "ticker": ticker,
            "current_price": current_price,
            "rsi": rsi,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "support_major": support_major,
            "resistance_major": resistance_major,
            "support_strength": support_strength,
            "resistance_strength": resistance_strength,
            "distance_to_support_pct": (current_price - support_major) / support_major * 100,
            "range_pct": (resistance_major - support_major) / support_major * 100,
            "next_earnings_days": next_earnings_days,
            "ema_uptrend": (ema_20 is not None and ema_50 is not None and ema_20 > ema_50),
        }
    except Exception as e:
        print(f"[warn] {ticker}: {e}")
        return None


# ─── Impact keyword categories ──────────────────────────────────────────────
IMPACT_CATEGORIES = [
    ("🏛️ Fed/Rates", ["fed ", " fed,", "fomc", "powell", "interest rate", "rate cut", "rate hike", "rate decision", "rate-cut", "rate-hike", "dovish", "hawkish", "easing cycle", "tightening", "basis point", "bps cut", "bps hike", "fed chair", "federal reserve"]),
    ("💰 Inflation", ["cpi", "ppi", "inflation", "deflation", "pce ", "core prices", "consumer price", "producer price"]),
    ("💼 Jobs", ["payrolls", "nfp", "jobs report", "unemployment", "labor market", "non-farm", "nonfarm", "hiring slowdown", "jobless"]),
    ("📊 Economy", ["gdp", "recession", "stimulus", "treasury yield", "yield curve", "soft landing", "hard landing", "economic growth"]),
    ("🌍 Geopolitics", [" war ", "war,", "war.", "ukraine", "russia", "israel", "iran", "middle east", "tariff", "sanction", "trade war", "china tension", "taiwan", "north korea"]),
    ("⚠️ Market shock", ["market crash", "selloff", "sell-off", "plunge", "correction", "bear market", "circuit breaker", "rout", "panic selling"]),
    ("🏛️ Government", ["shutdown", "debt ceiling", "election", "trump", "biden", "white house", "treasury secretary"]),
    ("💼 Earnings", ["earnings beat", "earnings miss", "guidance cut", "guidance raise", "missed estimates", "beat estimates", "profit warning"]),
]


def _categorize(text_lower: str) -> str | None:
    for cat, kws in IMPACT_CATEGORIES:
        for kw in kws:
            if kw in text_lower:
                return cat
    return None


# ─── Yahoo Finance news ─────────────────────────────────────────────────────
def fetch_yahoo_news(limit: int = 5, impact_filter: bool = True) -> list[dict]:
    try:
        items = yf.Ticker("SPY").news or []
    except Exception as e:
        print(f"[warn] yahoo news fetch: {e}")
        return []

    normalized: list[dict] = []
    for it in items:
        try:
            if "content" in it and isinstance(it["content"], dict):
                c = it["content"]
                pubdate = c.get("pubDate") or ""
                ts = 0
                if pubdate:
                    try:
                        ts = int(datetime.fromisoformat(pubdate.replace("Z", "+00:00")).timestamp())
                    except Exception:
                        pass
                headline = c.get("title", "")
                summary = c.get("summary", "") or c.get("description", "")
                source = (c.get("provider") or {}).get("displayName") or "Yahoo Finance"
                url = ((c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url") or "")
            else:
                headline = it.get("title", "")
                summary = it.get("summary", "")
                source = it.get("publisher", "Yahoo Finance")
                url = it.get("link", "")
                ts = int(it.get("providerPublishTime", 0) or 0)
            if headline:
                normalized.append({
                    "headline": headline,
                    "summary": summary,
                    "source": source,
                    "url": url,
                    "datetime": ts,
                    "category": None,
                })
        except Exception:
            continue

    normalized.sort(key=lambda x: x["datetime"], reverse=True)

    if not impact_filter:
        return normalized[:limit]

    impact = []
    for n in normalized[:25]:
        text = (n["headline"] + " " + (n.get("summary") or "")).lower()
        cat = _categorize(text)
        if cat:
            n["category"] = cat
            impact.append(n)

    if impact:
        return impact[:limit]

    for n in normalized[:3]:
        n["category"] = "📰 General"
    return normalized[:3]


def watchlist_earnings_this_week(tickers: list[str]) -> list[tuple[str, int]]:
    out = []
    for tk in tickers:
        try:
            cal = yf.Ticker(tk).calendar
            ed = None
            if isinstance(cal, dict):
                lst = cal.get("Earnings Date") or []
                if isinstance(lst, list) and lst:
                    ed = lst[0]
            if ed is not None:
                if hasattr(ed, "date"):
                    ed = ed.date()
                days = (ed - datetime.now(timezone.utc).date()).days
                if 0 <= days <= 7:
                    out.append((tk, days))
        except Exception:
            continue
    out.sort(key=lambda x: x[1])
    return out


# ─── Email send ─────────────────────────────────────────────────────────────
def send_email(subject: str, html_body: str) -> None:
    gmail_user = os.environ["GMAIL_USER"]
    gmail_pass = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
    to_email = os.environ.get("GMAIL_TO", gmail_user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(gmail_user, gmail_pass)
        s.send_message(msg)
    print(f"[ok] sent: {subject}")


# ─── Date helpers ───────────────────────────────────────────────────────────
def today_sgt_str() -> str:
    now_sgt = datetime.now(timezone(timedelta(hours=8)))
    return now_sgt.strftime("%a, %b %d").replace(" 0", " ")


def today_sgt_long() -> str:
    now_sgt = datetime.now(timezone(timedelta(hours=8)))
    return now_sgt.strftime("%A, %B %d, %Y").replace(" 0", " ")
