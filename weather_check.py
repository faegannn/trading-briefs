"""Weekly Weather Check — market regime read."""
from __future__ import annotations
import sys
import yfinance as yf

from lib import send_email, today_sgt_long, today_sgt_str


SECTOR_ETFS = {
    "XLK": "Tech",
    "XLY": "Cons Disc",
    "XLC": "Comm",
    "XLF": "Financials",
    "XLI": "Industrials",
    "XLE": "Energy",
    "XLB": "Materials",
    "XLV": "Healthcare",
    "XLP": "Cons Staples",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
}


def get_close_history(ticker: str, period: str = "1y") -> list[float] | None:
    try:
        h = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
        if h.empty:
            return None
        return h["Close"].tolist()
    except Exception as e:
        print(f"[warn] {ticker}: {e}")
        return None


def pct_change_30d(closes: list[float]) -> float | None:
    if len(closes) < 22:
        return None
    return (closes[-1] - closes[-22]) / closes[-22] * 100


def sma(closes: list[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def vix_zone(vix: float) -> str:
    if vix < 15:
        return "complacency"
    if vix < 22:
        return "normal"
    if vix < 30:
        return "fear"
    return "panic"


def regime_label(spy_above_50: bool, spy_above_200: bool, golden: bool, vix: float, top_sectors: list[str]) -> str:
    cyclicals = {"XLK", "XLY", "XLC"}
    defensives = {"XLP", "XLU", "XLV"}
    cyc_in_top = sum(1 for s in top_sectors if s in cyclicals)
    def_in_top = sum(1 for s in top_sectors if s in defensives)

    if spy_above_50 and spy_above_200 and golden and vix < 18 and cyc_in_top >= 2:
        return "STRONG BULL"
    if spy_above_50 and spy_above_200 and vix < 22 and cyc_in_top >= 1:
        return "MODERATE BULL"
    if not spy_above_200 and vix > 25:
        return "BEAR"
    if not spy_above_50 and spy_above_200:
        return "CORRECTION"
    if spy_above_50 and not spy_above_200:
        return "RECOVERY"
    return "CHOP"


def verdict(regime: str) -> str:
    return {
        "STRONG BULL": "BUY DIPS",
        "MODERATE BULL": "BUY DIPS",
        "RECOVERY": "BUY DIPS",
        "CHOP": "CASH IS A POSITION",
        "CORRECTION": "SELL RIPS",
        "BEAR": "CASH IS A POSITION",
    }.get(regime, "CASH IS A POSITION")


def render_email(data: dict) -> str:
    long_date = today_sgt_long()
    regime = data["regime"]
    v = data["verdict"]

    spy_line = (
        f"SPY ${data['spy_price']:.2f} · 50D ${data['spy_50']:.2f} · 200D ${data['spy_200']:.2f}"
        f" · {'Golden cross (50D > 200D)' if data['golden_cross'] else 'Death cross (50D < 200D)'}"
        f" · {'Above' if data['spy_above_50'] else 'Below'} 50D, {'above' if data['spy_above_200'] else 'below'} 200D"
    )
    vix_line = f"VIX {data['vix']:.1f} (20D avg {data['vix_20avg']:.1f}) — {data['vix_zone']} zone"
    rates_line = (
        f"10Y at {data['ten_y']:.2f}% · 30-day change {data['ten_y_30d_change']:+.2f}pp"
        f" · XLU 30D: {data['xlu_30d']:+.1f}% · XLRE 30D: {data['xlre_30d']:+.1f}%"
    )
    top_str = " · ".join(f"{s} {p:+.1f}%" for s, p in data["top3"])
    bot_str = " · ".join(f"{s} {p:+.1f}%" for s, p in data["bottom3"])

    return f"""<div style="font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;max-width:760px;margin:0 auto;color:#1a1a1a;line-height:1.5">
  <h1 style="margin:0 0 4px;font-size:22px">🌤️ Weekly Regime Read — {long_date}</h1>
  <p style="color:#666;margin:0 0 20px;font-size:13px">Which side of the tape this week · auto-generated 8am ET Sunday</p>

  <div style="background:#f5f7fa;padding:16px 20px;border-left:4px solid #4a90e2;margin-bottom:20px;border-radius:6px">
    <div style="font-size:13px;color:#666;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Regime</div>
    <div style="font-size:24px;font-weight:bold;margin-bottom:8px">{regime}</div>
    <div style="font-size:16px;font-weight:600;color:#2c5282">{v}</div>
  </div>

  <h2 style="font-size:15px;margin:24px 0 6px;border-bottom:1px solid #ddd;padding-bottom:4px">1. TREND <span style="font-weight:normal;color:#666;font-size:12px">— the master signal</span></h2>
  <p style="margin:0">{spy_line}</p>

  <h2 style="font-size:15px;margin:20px 0 6px;border-bottom:1px solid #ddd;padding-bottom:4px">2. VOLATILITY</h2>
  <p style="margin:0">{vix_line}</p>

  <h2 style="font-size:15px;margin:20px 0 6px;border-bottom:1px solid #ddd;padding-bottom:4px">3. RATES</h2>
  <p style="margin:0">{rates_line}</p>

  <h2 style="font-size:15px;margin:20px 0 6px;border-bottom:1px solid #ddd;padding-bottom:4px">4. LEADERSHIP</h2>
  <p style="margin:0"><strong>Top 3:</strong> {top_str}<br><strong>Bottom 3:</strong> {bot_str}</p>

  <hr style="margin:28px 0;border:none;border-top:1px solid #ddd">
  <p style="font-size:11px;color:#888">Data: Yahoo Finance (yfinance) via GitHub Actions. Not financial advice.</p>
</div>"""


def main() -> int:
    # SPY
    spy = get_close_history("SPY", "1y")
    if spy is None or len(spy) < 200:
        print("[error] SPY history unavailable")
        return 1
    spy_price = spy[-1]
    spy_50 = sma(spy, 50)
    spy_200 = sma(spy, 200)
    golden = spy_50 > spy_200
    above_50 = spy_price > spy_50
    above_200 = spy_price > spy_200

    # VIX
    vix_hist = get_close_history("^VIX", "3mo")
    vix = vix_hist[-1] if vix_hist else float("nan")
    vix_20avg = sum(vix_hist[-20:]) / 20 if vix_hist and len(vix_hist) >= 20 else float("nan")

    # 10Y (^TNX is quoted as yield × 10)
    tnx = get_close_history("^TNX", "3mo")
    ten_y = (tnx[-1] / 10) if tnx else float("nan")
    ten_y_30d_change = ((tnx[-1] - tnx[-22]) / 10) if tnx and len(tnx) >= 22 else float("nan")

    # Sector ETFs
    perf = {}
    for sym in SECTOR_ETFS:
        h = get_close_history(sym, "3mo")
        p = pct_change_30d(h) if h else None
        if p is not None:
            perf[sym] = p
    sorted_perf = sorted(perf.items(), key=lambda kv: kv[1], reverse=True)
    top3 = sorted_perf[:3]
    bottom3 = sorted_perf[-3:][::-1]

    xlu_30 = perf.get("XLU", 0.0)
    xlre_30 = perf.get("XLRE", 0.0)

    regime = regime_label(above_50, above_200, golden, vix, [s for s, _ in top3])
    v = verdict(regime)

    data = {
        "regime": regime,
        "verdict": v,
        "spy_price": spy_price,
        "spy_50": spy_50,
        "spy_200": spy_200,
        "golden_cross": golden,
        "spy_above_50": above_50,
        "spy_above_200": above_200,
        "vix": vix,
        "vix_20avg": vix_20avg,
        "vix_zone": vix_zone(vix),
        "ten_y": ten_y,
        "ten_y_30d_change": ten_y_30d_change,
        "xlu_30d": xlu_30,
        "xlre_30d": xlre_30,
        "top3": top3,
        "bottom3": bottom3,
    }

    html = render_email(data)
    subject = f"[AUTO] 🌤️ Weekly Regime Read — {today_sgt_str()}"
    send_email(subject, html)
    print(f"[ok] regime={regime} verdict={v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
