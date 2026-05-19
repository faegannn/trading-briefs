"""Daily Setup Scanner — scores each watchlist ticker on the 5-point checklist."""
from __future__ import annotations
import sys
from lib import load_watchlist, fetch_ticker, send_email, today_sgt_str, today_sgt_long


# ─── 5-point checklist scoring ──────────────────────────────────────────────
def score(data: dict) -> tuple[int, list[tuple[str, bool]]]:
    checks = [
        ("RSI < 40", data["rsi"] < 40),
        ("Within 2.5% of support", abs(data["distance_to_support_pct"]) <= 2.5),
        ("EMA 20 > EMA 50 (uptrend)", data["ema_uptrend"]),
        ("Range ≥ 2.5%", data["range_pct"] >= 2.5),
        (
            "No earnings within 14 days",
            data["next_earnings_days"] is None or data["next_earnings_days"] > 14,
        ),
    ]
    s = sum(1 for _, ok in checks if ok)
    return s, checks


def pick_eligible(scored: list[dict]) -> list[dict]:
    """All 4/5+ tickers sorted best→worst. First entry is the auto-pick."""
    eligible = [r for r in scored if r["score"] >= 4]
    eligible.sort(
        key=lambda r: (
            -r["score"],
            abs(r["data"]["distance_to_support_pct"]),
            r["data"]["rsi"],
            -r["data"]["range_pct"],
        )
    )
    return eligible


def trade_plan(d: dict) -> dict:
    s = d["support_major"]
    r = d["resistance_major"]
    target = min(r, s * 1.03)
    return {
        "entry_1_price": s,
        "entry_1_alloc": 1000,
        "entry_1_qty": int(1000 // s),
        "entry_2_trigger": s * 0.95,
        "entry_2_alloc": 600,
        "entry_3_trigger": s * 0.90,
        "entry_3_alloc": 400,
        "target_price": target,
        "target_pct": (target - s) / s * 100,
    }


# ─── HTML rendering ─────────────────────────────────────────────────────────
def fmt(v, decimals=2, pct=False, plus=False, na="N/A"):
    if v is None or (isinstance(v, float) and (v != v)):
        return na
    sign = "+" if plus and v > 0 else ""
    s = f"{sign}{v:.{decimals}f}"
    if pct:
        s += "%"
    return s


def cell(ok: bool, text: str) -> str:
    color = "#10b981" if ok else "#ef4444"
    return f'<td style="text-align:right;padding:6px 8px;border:1px solid #ddd;color:{color};font-weight:600">{text}</td>'


def neutral_cell(text: str) -> str:
    return f'<td style="text-align:right;padding:6px 8px;border:1px solid #ddd">{text}</td>'


def render_email(scored: list[dict], eligible: list[dict]) -> str:
    long_date = today_sgt_long()
    winner = eligible[0] if eligible else None

    # Hero
    if winner:
        w = winner
        d = w["data"]
        plan = w["plan"]
        # Multi-candidate sub-note if there are more than one 4/5+ setups
        if len(eligible) > 1:
            others = " · ".join(
                f"<strong>{e['data']['ticker']}</strong> ({e['score']}/5)"
                for e in eligible[1:]
            )
            multi_note = (
                f'<div style="font-size:12px;color:#047857;margin-top:8px;padding-top:8px;border-top:1px solid #a7f3d0">'
                f'<strong>Also eligible this week:</strong> {others}. '
                f'Pick whichever you prefer — same V1 rules apply. Auto-pick is the closest to support.'
                f"</div>"
            )
        else:
            multi_note = ""

        hero = f"""
        <div style="background:linear-gradient(135deg,#ecfdf5 0%,#d1fae5 100%);padding:16px 20px;border-left:4px solid #10b981;margin-bottom:24px;border-radius:6px">
          <div style="font-size:11px;color:#047857;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;font-weight:600">🎯 Auto-pick: tightest setup</div>
          <div style="font-size:22px;font-weight:700;color:#064e3b">{d['ticker']} · {w['score']}/5 ✅</div>
          <div style="font-size:13px;color:#065f46;margin-top:4px">
            At support ${d['support_major']:.2f} ({fmt(d['distance_to_support_pct'], 1, pct=True, plus=True)}) · RSI {d['rsi']:.0f} · range {d['range_pct']:.1f}% · earnings in {'∞' if d['next_earnings_days'] is None else f"{d['next_earnings_days']}d"}
          </div>
          {multi_note}
        </div>
        """
        decision = f"""
        <h2 style="font-size:14px;margin:20px 0 8px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Decision (auto-pick)</h2>
        <p style="font-size:13px;margin:0">
          <strong>{d['ticker']}</strong> is your {w['score']}/5 setup. Limit order: <strong>${plan['entry_1_price']:.2f}</strong>
          ({plan['entry_1_qty']} shares ≈ $1,000). DCA-2 trigger: ${plan['entry_2_trigger']:.2f} (–5%). DCA-3 trigger:
          ${plan['entry_3_trigger']:.2f} (–10%). Target: <strong>${plan['target_price']:.2f}</strong>
          (+{plan['target_pct']:.1f}%). Cancel if not filled by Wednesday.
        </p>
        {('<p style="font-size:12px;color:#6b7280;margin-top:6px">If you choose a different eligible name instead, the same DCA math applies: 50% at support, 30% if it drops 5%, 20% if it drops 10%; target +3% or resistance.</p>') if len(eligible) > 1 else ''}
        """
    else:
        highest = max(scored, key=lambda r: r["score"]) if scored else None
        hi_s = highest["score"] if highest else 0
        hi_t = highest["data"]["ticker"] if highest else "—"
        hero = f"""
        <div style="background:#fef2f2;padding:16px 20px;border-left:4px solid #ef4444;margin-bottom:24px;border-radius:6px">
          <div style="font-size:22px;font-weight:700;color:#991b1b">⏸️ SKIP THIS WEEK</div>
          <div style="font-size:13px;color:#7f1d1d;margin-top:4px">No watchlist ticker scored 4/5+. Highest: {hi_t} at {hi_s}/5. Wait for next week.</div>
        </div>
        """
        decision = ""

    # Ranked table
    scored_sorted = sorted(
        scored,
        key=lambda r: (
            -r["score"],
            abs(r["data"]["distance_to_support_pct"]),
            r["data"]["rsi"],
        ),
    )
    eligible_tickers = {e["data"]["ticker"] for e in eligible}
    rows_html = []
    for rank, r in enumerate(scored_sorted, start=1):
        d = r["data"]
        is_winner = winner is not None and d["ticker"] == winner["data"]["ticker"]
        is_eligible = d["ticker"] in eligible_tickers and not is_winner
        if is_winner:
            bg = "background:#ecfdf5;font-weight:600"
        elif is_eligible:
            bg = "background:#f0fdf4"
        else:
            bg = ""
        score_color = "#10b981" if r["score"] >= 4 else ("#f59e0b" if r["score"] == 3 else "#ef4444")
        score_label = "✅" if r["score"] >= 4 else ("⚠️" if r["score"] == 3 else "❌")
        earn_days = d["next_earnings_days"]
        # Show "—" if unknown OR if the stored value is in the past (defensive).
        if earn_days is None or earn_days < 0:
            earn_str = "—"
            earn_ok = True  # unknown earnings ≠ disqualification
        else:
            earn_str = f"{earn_days}d"
            earn_ok = earn_days > 14
        rows_html.append(f"""
        <tr style="{bg}">
          <td style="text-align:center;padding:6px 8px;border:1px solid #ddd">{rank}</td>
          <td style="padding:6px 8px;border:1px solid #ddd;font-weight:700">{d['ticker']}</td>
          <td style="text-align:center;padding:6px 8px;border:1px solid #ddd;color:{score_color};font-weight:600">{r['score']}/5 {score_label}</td>
          {neutral_cell(f"${d['current_price']:.2f}")}
          {cell(d['rsi'] < 40, f"{d['rsi']:.0f}")}
          {neutral_cell(f"${d['support_major']:.2f}")}
          {cell(abs(d['distance_to_support_pct']) <= 2.5, fmt(d['distance_to_support_pct'], 1, pct=True, plus=True))}
          <td style="text-align:center;padding:6px 8px;border:1px solid #ddd;color:{'#10b981' if d['ema_uptrend'] else '#ef4444'};font-weight:600">{'✓' if d['ema_uptrend'] else '✗'}</td>
          {cell(d['range_pct'] >= 2.5, f"{d['range_pct']:.1f}%")}
          {cell(earn_ok, earn_str)}
        </tr>
        """)
    rows_html_str = "\n".join(rows_html)

    return f"""<div style="font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;max-width:760px;margin:0 auto;color:#1a1a1a;line-height:1.5">

  <h1 style="margin:0 0 4px;font-size:22px">📊 Setup Scanner — {long_date}</h1>
  <p style="color:#666;margin:0 0 20px;font-size:13px">5-point checklist scored for your watchlist · auto-generated 8am ET</p>

  {hero}

  <h2 style="font-size:14px;margin:16px 0 8px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">All {len(scored)} watchlist tickers — ranked</h2>
  <table style="border-collapse:collapse;width:100%;font-size:12px">
    <thead>
      <tr style="background:#f5f5f5">
        <th style="text-align:center;padding:6px 8px;border:1px solid #ddd">Rank</th>
        <th style="text-align:left;padding:6px 8px;border:1px solid #ddd">Ticker</th>
        <th style="text-align:center;padding:6px 8px;border:1px solid #ddd">Score</th>
        <th style="text-align:right;padding:6px 8px;border:1px solid #ddd">Price</th>
        <th style="text-align:right;padding:6px 8px;border:1px solid #ddd">RSI</th>
        <th style="text-align:right;padding:6px 8px;border:1px solid #ddd">Support</th>
        <th style="text-align:right;padding:6px 8px;border:1px solid #ddd">To Support</th>
        <th style="text-align:center;padding:6px 8px;border:1px solid #ddd">EMA 20&gt;50</th>
        <th style="text-align:right;padding:6px 8px;border:1px solid #ddd">Range</th>
        <th style="text-align:right;padding:6px 8px;border:1px solid #ddd">Earnings</th>
      </tr>
    </thead>
    <tbody>
      {rows_html_str}
    </tbody>
  </table>

  {decision}

  <hr style="margin:24px 0 12px;border:none;border-top:1px solid #ddd">
  <div style="font-size:11px;color:#6b7280;line-height:1.7">
    <strong style="color:#374151">Column legend</strong><br>
    <strong>Price</strong> — current market price<br>
    <strong>Support</strong> — major support level (60-day, multi-touch), your entry target<br>
    <strong>To Support</strong> — distance from price to support. +1.4% = trading 1.4% above support (good). Negative = price has dropped below support (broken).<br>
    <strong>Range</strong> — gap from support to resistance. Bigger = more profit potential.<br>
    <strong>Earnings</strong> — days until next upcoming earnings. "—" means no earnings reported within Yahoo's data window.<br>
    <br>
    <strong style="color:#374151">5-point checklist (need 4/5 to trade)</strong><br>
    RSI &lt; 40 · within 2.5% of support · EMA 20 &gt; EMA 50 · range ≥ 2.5% · no earnings in 14 days<br>
    <br>
    Data: Yahoo Finance (yfinance) via GitHub Actions. 1 trade per week max. Not financial advice.
  </div>
</div>"""


# ─── Main ───────────────────────────────────────────────────────────────────
def main() -> int:
    tickers = load_watchlist()
    print(f"[info] watchlist: {tickers}")

    scored = []
    for t in tickers:
        d = fetch_ticker(t)
        if d is None:
            print(f"[warn] no data for {t}")
            continue
        s, checks = score(d)
        scored.append({"data": d, "score": s, "checks": checks})

    if not scored:
        print("[error] no ticker data — aborting send")
        return 1

    eligible = pick_eligible(scored)
    for e in eligible:
        e["plan"] = trade_plan(e["data"])

    html = render_email(scored, eligible)
    subject = f"[AUTO] 📊 Setup Scanner — {today_sgt_str()}"
    send_email(subject, html)
    return 0


if __name__ == "__main__":
    sys.exit(main())
