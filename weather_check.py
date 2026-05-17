"""Weekly Weather Check — visual market regime read for a swing trader.
 
Designed for a 1-2 week swing trader. Two signals that really matter:
  TREND  — is the market up? (controls whether dip-buys have tailwind)
  FEAR   — is VIX panicking? (controls whether limit orders fill cleanly)
 
Rates and sector leadership are de-emphasized — they matter more for long-term
investors than 1-2 week swing trades. Shown as a small "for the curious" note.
"""
from __future__ import annotations
import sys
import yfinance as yf
 
from lib import send_email, today_sgt_long, today_sgt_str
 
 
# ─── Data fetch ─────────────────────────────────────────────────────────────
def closes_of(ticker: str, period: str = "1y") -> list[float] | None:
    try:
        h = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
        if h.empty:
            return None
        return h["Close"].tolist()
    except Exception as e:
        print(f"[warn] {ticker}: {e}")
        return None
 
 
def sma(closes: list[float], window: int) -> float:
    return sum(closes[-window:]) / window
 
 
def pct_change_n(closes: list[float], n: int) -> float | None:
    if len(closes) < n + 1:
        return None
    return (closes[-1] - closes[-n - 1]) / closes[-n - 1] * 100
 
 
# ─── Signal logic ───────────────────────────────────────────────────────────
def trend_signal(spy: list[float]) -> tuple[str, dict]:
    """Returns ('green'|'amber'|'red', detail dict)."""
    price = spy[-1]
    sma50 = sma(spy, 50)
    sma200 = sma(spy, 200)
    above_50 = price > sma50
    above_200 = price > sma200
    golden = sma50 > sma200
 
    if above_50 and above_200 and golden:
        light = "green"
        label = "UP"
        why = f"SPY ${price:.2f} above both moving averages · Golden cross active"
    elif not above_50 and not above_200 and not golden:
        light = "red"
        label = "DOWN"
        why = f"SPY ${price:.2f} below both moving averages · Death cross active"
    else:
        light = "amber"
        label = "MIXED"
        why = f"SPY ${price:.2f} · above 50D: {above_50} · above 200D: {above_200} · 50D > 200D: {golden}"
 
    return light, {
        "label": label,
        "why": why,
        "price": price,
        "sma50": sma50,
        "sma200": sma200,
        "above_50": above_50,
        "above_200": above_200,
        "golden": golden,
    }
 
 
def fear_signal(vix: list[float]) -> tuple[str, dict]:
    v = vix[-1]
    avg20 = sma(vix, 20) if len(vix) >= 20 else v
    if v < 15:
        light, label = "green", "CHILL"
    elif v < 22:
        light, label = "green", "NORMAL"
    elif v < 30:
        light, label = "amber", "FEAR"
    else:
        light, label = "red", "PANIC"
    return light, {"value": v, "avg20": avg20, "label": label}
 
 
def overall_verdict(trend: str, fear: str) -> dict:
    """Combine the two signals into one verdict for the week."""
    if trend == "green" and fear == "green":
        return {
            "light": "go",
            "head": "TRADE — DIP-BUY OK",
            "sub": "Trend is up. Fear is normal. Setups should fire and fill cleanly.",
            "actions": [
                "Run the Mon–Fri Setup Scanner emails as usual.",
                "If a name scores 4/5+, take the trade at normal size ($1,000 first entry).",
                "Trust support bounces. Don't bail on the first 1% wiggle.",
                "Still 1 trade per week max — pick the best, skip the rest.",
            ],
        }
    if trend == "red" or fear == "red":
        return {
            "light": "stop",
            "head": "SIT IT OUT",
            "sub": "Conditions hostile — either trend is broken or fear is too high. False signals likely.",
            "actions": [
                "Skip new entries this week. Cash is a position.",
                "If you already hold open positions, tighten — exit on the next strength.",
                "Wait for trend to repair or fear to drop before the next entry.",
            ],
        }
    return {
        "light": "caution",
        "head": "BE CAREFUL",
        "sub": "Mixed signals. Trade smaller and wait for the cleanest setups.",
        "actions": [
            "Only act on 5/5 scanner setups this week — skip 4/5.",
            "Use half size ($500 first entry instead of $1,000).",
            "Tighter exits: take 2% instead of 2.5–3% target.",
            "Re-check the trend daily; don't fight a falling tape.",
        ],
    }
 
 
# ─── HTML rendering ─────────────────────────────────────────────────────────
def render_email(trend_light, trend, fear_light, fear, verdict, rates_ctx) -> str:
    long_date = today_sgt_long()
 
    # Verdict block styling
    if verdict["light"] == "go":
        v_bg = "background:linear-gradient(135deg,#ecfdf5,#d1fae5);border:2px solid #10b981"
        v_dot = "🟢"
        v_lbl_color = "#047857"
        v_head_color = "#064e3b"
        v_sub_color = "#065f46"
    elif verdict["light"] == "stop":
        v_bg = "background:linear-gradient(135deg,#fef2f2,#fee2e2);border:2px solid #ef4444"
        v_dot = "🔴"
        v_lbl_color = "#991b1b"
        v_head_color = "#7f1d1d"
        v_sub_color = "#991b1b"
    else:
        v_bg = "background:linear-gradient(135deg,#fffbeb,#fef3c7);border:2px solid #f59e0b"
        v_dot = "🟡"
        v_lbl_color = "#92400e"
        v_head_color = "#78350f"
        v_sub_color = "#92400e"
 
    # Trend bar (SPY position vs MAs)
    # Normalize positions onto a 0-100% scale
    p = trend["price"]
    s50 = trend["sma50"]
    s200 = trend["sma200"]
    span_lo = min(p, s50, s200) * 0.985
    span_hi = max(p, s50, s200) * 1.015
    span = span_hi - span_lo or 1
 
    def pos(v):
        return (v - span_lo) / span * 100
 
    trend_dot_color = {"green": "#10b981", "amber": "#f59e0b", "red": "#ef4444"}[trend_light]
    bar_fill = (
        "linear-gradient(to right,#fee2e2 0%,#fef3c7 50%,#d1fae5 100%)"
        if trend_light != "red"
        else "linear-gradient(to right,#fee2e2 0%,#fee2e2 100%)"
    )
 
    # VIX zone bar
    fear_dot_color = {"green": "#10b981", "amber": "#f59e0b", "red": "#ef4444"}[fear_light]
    vix_pos = min(max((fear["value"] - 10) / 30 * 100, 0), 100)  # scale 10-40 to 0-100%
 
    actions_html = "\n".join(f'<li style="margin:3px 0">{a}</li>' for a in verdict["actions"])
 
    return f"""<div style="font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;max-width:680px;margin:0 auto;color:#1a1a1a;line-height:1.5;padding:20px">
 
  <h1 style="margin:0 0 4px;font-size:22px">🌤️ Weather Check — {long_date}</h1>
  <p style="color:#666;margin:0 0 20px;font-size:13px">Should you trade this week, or sit it out?</p>
 
  <!-- ────────── VERDICT ────────── -->
  <div style="{v_bg};padding:24px 20px;border-radius:10px;text-align:center;margin-bottom:24px">
    <div style="font-size:36px">{v_dot}</div>
    <div style="color:{v_lbl_color};font-size:11px;text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-top:4px">This week's call</div>
    <div style="color:{v_head_color};font-size:28px;font-weight:800;margin:6px 0">{verdict['head']}</div>
    <div style="color:{v_sub_color};font-size:14px">{verdict['sub']}</div>
  </div>
 
  <!-- ────────── TREND CARD ────────── -->
  <div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin-bottom:14px">
    <div style="font-size:13px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;margin-bottom:8px">📈 Is the market going up? — TREND</div>
    <div style="font-size:20px;font-weight:700;margin-bottom:4px"><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{trend_dot_color};vertical-align:middle;margin-right:6px"></span>{trend['label']}</div>
    <div style="font-size:13px;color:#374151">{trend['why']}</div>
 
    <!-- visual position bar -->
    <div style="position:relative;height:14px;background:#f3f4f6;border-radius:7px;margin:14px 0 4px;overflow:hidden">
      <div style="height:100%;border-radius:7px;background:{bar_fill}"></div>
    </div>
    <div style="position:relative;height:32px;margin-bottom:6px">
      <div style="position:absolute;top:-10px;left:{pos(s200):.1f}%;width:2px;height:14px;background:repeating-linear-gradient(to bottom,#9ca3af 0 3px,transparent 3px 6px)"></div>
      <div style="position:absolute;top:4px;left:{pos(s200):.1f}%;font-size:10px;color:#6b7280;transform:translateX(-50%);white-space:nowrap">200D ${s200:.0f}</div>
      <div style="position:absolute;top:-10px;left:{pos(s50):.1f}%;width:2px;height:14px;background:#9ca3af"></div>
      <div style="position:absolute;top:18px;left:{pos(s50):.1f}%;font-size:10px;color:#6b7280;transform:translateX(-50%);white-space:nowrap">50D ${s50:.0f}</div>
      <div style="position:absolute;top:-12px;left:{pos(p):.1f}%;width:3px;height:18px;background:#1f2937"></div>
      <div style="position:absolute;top:10px;left:{pos(p):.1f}%;font-size:10px;color:#1f2937;font-weight:700;transform:translateX(-50%);white-space:nowrap">SPY ${p:.0f}</div>
    </div>
 
    <div style="background:#f9fafb;border-left:3px solid #6b7280;padding:8px 10px;margin-top:10px;border-radius:4px;font-size:12px;color:#374151">
      <strong>For your swing trades:</strong> {_trend_takeaway(trend_light)}
    </div>
  </div>
 
  <!-- ────────── FEAR CARD ────────── -->
  <div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin-bottom:14px">
    <div style="font-size:13px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;margin-bottom:8px">😱 How scared is the market? — FEAR</div>
    <div style="font-size:20px;font-weight:700;margin-bottom:4px"><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{fear_dot_color};vertical-align:middle;margin-right:6px"></span>VIX {fear['value']:.1f} — {fear['label']}</div>
    <div style="font-size:13px;color:#374151">20-day average: {fear['avg20']:.1f}</div>
 
    <!-- VIX zone bar -->
    <div style="position:relative;margin-top:14px">
      <div style="display:flex;height:14px;border-radius:7px;overflow:hidden">
        <span style="flex:5;background:#dbeafe"></span>
        <span style="flex:7;background:#d1fae5"></span>
        <span style="flex:8;background:#fef3c7"></span>
        <span style="flex:10;background:#fee2e2"></span>
      </div>
      <div style="position:absolute;top:-4px;left:calc({vix_pos:.1f}% - 7px);width:0;height:0;border-left:7px solid transparent;border-right:7px solid transparent;border-top:8px solid #1f2937"></div>
      <div style="display:flex;justify-content:space-between;font-size:10px;color:#9ca3af;font-family:'SF Mono',Menlo,monospace;margin-top:6px">
        <span>10</span><span>15 chill</span><span>22 normal</span><span>30 fear</span><span>40+ panic</span>
      </div>
    </div>
 
    <div style="background:#f9fafb;border-left:3px solid #6b7280;padding:8px 10px;margin-top:14px;border-radius:4px;font-size:12px;color:#374151">
      <strong>For your swing trades:</strong> {_fear_takeaway(fear_light)}
    </div>
  </div>
 
  <!-- ────────── ACTIONS ────────── -->
  <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:14px 16px;margin-top:8px">
    <div style="font-size:13px;color:#1e40af;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;margin-bottom:8px">🎯 Your action this week</div>
    <ul style="margin:4px 0 0 18px;padding:0;font-size:13px;color:#1e3a8a">
      {actions_html}
    </ul>
  </div>
 
  <!-- ────────── FOOTER ────────── -->
  <hr style="margin:24px 0 12px;border:none;border-top:1px solid #ddd">
  <p style="font-size:11px;color:#888">
    Data: Yahoo Finance via GitHub Actions. Not financial advice.
  </p>
  <p style="font-size:11px;color:#6b7280;margin-top:6px">
    <strong>For the curious:</strong> {rates_ctx}
  </p>
</div>"""
 
 
def _trend_takeaway(light: str) -> str:
    return {
        "green": "The tide is rising. Dip-buys at support tend to bounce, not break. Your 5-point checklist signals are trustworthy this week.",
        "amber": "Mixed picture. Some setups will work, others will fail. Be picky — only the cleanest 5/5 scanner picks deserve a position.",
        "red": "Tide is going out. Even good-looking setups break support. Don't try to catch falling knives — cash is a real position this week.",
    }[light]
 
 
def _fear_takeaway(light: str) -> str:
    return {
        "green": "Low VIX means small overnight gaps. Limit orders fill where you put them; stops don't get blown out by overnight moves.",
        "amber": "Elevated VIX means wider intraday swings and bigger gaps. Be wary of limit orders filling too cheap (means stock is gapping down through your level).",
        "red": "Panic VIX means giant gaps and false breakdowns. Limit orders fill into freefalls. Skip new entries entirely this week.",
    }[light]
 
 
def _rates_context(ten_y: float, ten_y_30d_chg: float, top_sectors: list[tuple[str, float]]) -> str:
    """One-line footnote — Rates and Leadership for the curious."""
    direction = "rising" if ten_y_30d_chg > 0.2 else ("falling" if ten_y_30d_chg < -0.2 else "steady")
    top_str = ", ".join(f"{s} {p:+.1f}%" for s, p in top_sectors)
    return (
        f"10-year Treasury yield at {ten_y:.2f}% ({direction}, {ten_y_30d_chg:+.2f}pp over 30 days). "
        f"Sector leaders: {top_str}. These matter more for long-term investors than 1–2 week swing trades."
    )
 
 
# ─── Main ───────────────────────────────────────────────────────────────────
SECTOR_ETFS = ["XLK", "XLY", "XLC", "XLF", "XLI", "XLE", "XLB", "XLV", "XLP", "XLU", "XLRE"]
 
 
def main() -> int:
    spy = closes_of("SPY", "1y")
    if spy is None or len(spy) < 200:
        print("[error] SPY data unavailable")
        return 1
    vix = closes_of("^VIX", "3mo")
    if vix is None or len(vix) < 20:
        print("[error] VIX data unavailable")
        return 1
 
    trend_light, trend = trend_signal(spy)
    fear_light, fear = fear_signal(vix)
    verdict = overall_verdict(trend_light, fear_light)
 
    # Context: rates + leadership (small footer line only)
    tnx = closes_of("^TNX", "3mo")
    ten_y = (tnx[-1] / 10) if tnx else 0.0
    ten_y_30d_chg = ((tnx[-1] - tnx[-22]) / 10) if tnx and len(tnx) >= 22 else 0.0
 
    sector_perf: dict[str, float] = {}
    for sym in SECTOR_ETFS:
        c = closes_of(sym, "3mo")
        if c and len(c) >= 22:
            sector_perf[sym] = (c[-1] - c[-22]) / c[-22] * 100
    top3 = sorted(sector_perf.items(), key=lambda kv: kv[1], reverse=True)[:3]
    rates_ctx = _rates_context(ten_y, ten_y_30d_chg, top3)
 
    html = render_email(trend_light, trend, fear_light, fear, verdict, rates_ctx)
    subject = f"[AUTO] 🌤️ Weather Check — {today_sgt_str()}"
    send_email(subject, html)
    print(f"[ok] verdict: {verdict['head']}")
    return 0
 
 
if __name__ == "__main__":
    sys.exit(main())
