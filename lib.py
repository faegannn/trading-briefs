"""Shared utilities — algorithms match the trading dashboard exactly."""
from __future__ import annotations
import os
import smtplib
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
    """Wilder RSI — exact port of dashboard calcRSI()."""
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
    """EMA initialized with SMA of first `period` values — matches dashboard."""
    if len(arr) < period:
        return None
    k = 2 / (period + 1)
    e = sum(arr[:period]) / period
    for i in range(period, len(arr)):
        e = arr[i] * k + e * (1 - k)
    return e
 
 
def find_sr(highs: list[float], lows: list[float], price: float, win: int = 2) -> dict:
    """Find support/resistance — exact port of dashboard findSR().
 
    Returns dict with 'sup' (supports below price) and 'res' (resistance above),
    each a list of {p, type, cnt, touches, strength, strengthScore},
    top 3 closest to price, with strength based on number of touches.
    """
    levs = []
    n = len(highs)
    for i in range(win, n - win):
        window_h = highs[i - win : i + win + 1]
        window_l = lows[i - win : i + win + 1]
        if highs[i] == max(window_h):
            levs.append({"p": highs[i], "type": "r"})
        if lows[i] == min(window_l):
            levs.append({"p": lows[i], "type": "s"})
 
    # Cluster nearby levels (within 1.2% of each other)
    levs.sort(key=lambda x: x["p"])
    cl: list[dict] = []
    for lv in levs:
        existing = next((c for c in cl if abs(c["p"] - lv["p"]) / lv["p"] < 0.012), None)
        if existing:
            existing["cnt"] += 1
            existing["p"] = (existing["p"] + lv["p"]) / 2
        else:
            cl.append({**lv, "cnt": 1})
 
    # Count actual touches (candles within 0.8% of level)
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
 
    supports = sorted(
        [x for x in cl if x["type"] == "s" and x["p"] < price],
        key=lambda x: -x["p"],
    )[:3]
    resistances = sorted(
        [x for x in cl if x["type"] == "r" and x["p"] > price],
        key=lambda x: x["p"],
    )[:3]
    return {"sup": supports, "res": resistances}
 
 
def nearest_support(sr: dict) -> dict | None:
    """Most relevant support: highest-strength among the top 3 below price.
    If multiple share the highest strength, pick the closest to current price.
    """
    if not sr["sup"]:
        return None
    best = max(sr["sup"], key=lambda s: (s["strengthScore"], s["p"]))
    return best
 
 
def nearest_resistance(sr: dict) -> dict | None:
    if not sr["res"]:
        return None
    best = max(sr["res"], key=lambda r: (r["strengthScore"], -r["p"]))
    return best
 
 
# ─── Ticker data ────────────────────────────────────────────────────────────
def fetch_ticker(ticker: str) -> dict | None:
    """Fetch full snapshot for one ticker using dashboard-matching algorithms."""
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
 
        # Use ~100 trading days (matches dashboard's Alpaca limit=100)
        recent = min(100, len(closes))
        sr = find_sr(highs[-recent:], lows[-recent:], current_price)
        sup = nearest_support(sr)
        res = nearest_resistance(sr)
        support_major = sup["p"] if sup else min(lows[-60:])
        resistance_major = res["p"] if res else max(highs[-60:])
        support_strength = sup["strength"] if sup else "weak"
        resistance_strength = res["strength"] if res else "weak"
 
        # Next earnings
        next_earnings_days: int | None = None
        try:
            cal = t.calendar
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if isinstance(ed, list) and ed:
                    earn = ed[0]
                    if hasattr(earn, "date"):
                        earn = earn.date()
                    next_earnings_days = (earn - datetime.now(timezone.utc).date()).days
            elif hasattr(cal, "iloc") and "Earnings Date" in cal.index:
                ed = cal.loc["Earnings Date"]
                if hasattr(ed, "iloc"):
                    ed = ed.iloc[0]
                if hasattr(ed, "date"):
                    ed = ed.date()
                next_earnings_days = (ed - datetime.now(timezone.utc).date()).days
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
 
 
# ─── Email send (Gmail SMTP) ────────────────────────────────────────────────
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
    """e.g. 'Mon, May 18'."""
    now_sgt = datetime.now(timezone(timedelta(hours=8)))
    return now_sgt.strftime("%a, %b %d").replace(" 0", " ")
 
 
def today_sgt_long() -> str:
    now_sgt = datetime.now(timezone(timedelta(hours=8)))
    return now_sgt.strftime("%A, %B %d, %Y").replace(" 0", " ")
 
