"""Shared utilities: data fetch, indicators, email sending."""
from __future__ import annotations
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf


# ─── Watchlist ──────────────────────────────────────────────────────────────
def load_watchlist(path: str = "watchlist.txt") -> list[str]:
    tickers = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            tickers.append(line.upper())
    return tickers


# ─── Indicators ─────────────────────────────────────────────────────────────
def rsi(closes: pd.Series, period: int = 14) -> float:
    """Wilder's RSI."""
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    out = 100 - (100 / (1 + rs))
    return float(out.iloc[-1])


def ema(closes: pd.Series, span: int) -> float:
    return float(closes.ewm(span=span, adjust=False).mean().iloc[-1])


def sma(closes: pd.Series, window: int) -> float:
    return float(closes.tail(window).mean())


# ─── Ticker data ────────────────────────────────────────────────────────────
def fetch_ticker(ticker: str) -> dict | None:
    """Fetch full snapshot for one ticker. Returns None if data unavailable."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="6mo", interval="1d", auto_adjust=False)
        if hist.empty or len(hist) < 50:
            return None

        closes = hist["Close"]
        highs = hist["High"]
        lows = hist["Low"]
        current_price = float(closes.iloc[-1])

        # Support: lowest low in last 60 trading days
        support_major = float(lows.tail(60).min())
        resistance_major = float(highs.tail(60).max())

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
            "rsi": rsi(closes),
            "ema_20": ema(closes, 20),
            "ema_50": ema(closes, 50),
            "support_major": support_major,
            "resistance_major": resistance_major,
            "distance_to_support_pct": (current_price - support_major) / support_major * 100,
            "range_pct": (resistance_major - support_major) / support_major * 100,
            "next_earnings_days": next_earnings_days,
            "ema_uptrend": ema(closes, 20) > ema(closes, 50),
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
    return now_sgt.strftime("%a, %b %-d") if os.name != "nt" else now_sgt.strftime("%a, %b %#d")


def today_sgt_long() -> str:
    now_sgt = datetime.now(timezone(timedelta(hours=8)))
    return now_sgt.strftime("%A, %B %-d, %Y") if os.name != "nt" else now_sgt.strftime("%A, %B %#d, %Y")
