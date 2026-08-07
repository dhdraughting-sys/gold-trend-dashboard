#!/usr/bin/env python3
"""
gold_trends.py
==============
A trend-following dashboard generator for spot gold (with silver, the US
Dollar Index, and the 10-year Treasury yield as context).

WHAT IT DOES
------------
1. Downloads recent daily price history for gold, silver, the US Dollar
   Index, and the 10-year Treasury yield (free data via Yahoo Finance,
   no API key needed).
2. Computes the indicators trend-followers actually look at: 20/50/200-day
   moving averages, golden/death cross detection, 14-day RSI, rolling
   volatility, and % change over several windows (1D/1W/1M/3M/YTD/1Y).
3. Writes a single self-contained HTML dashboard (gold_dashboard.html)
   with the charts and a plain-English trend read-out, and prints the
   same read-out to your terminal.

USAGE
-----
    pip install yfinance pandas
    python3 gold_trends.py

Then open gold_dashboard.html in any browser. Re-run the script any time
(e.g. once a day, or via cron/Task Scheduler) to refresh it with the
latest prices.

NOTE ON DATA
------------
"Spot" gold/silver (XAUUSD=X / XAGUSD=X) is preferred; if Yahoo doesn't
return it (this happens occasionally), the script automatically falls
back to the corresponding COMEX/COMEX-silver futures contract (GC=F /
SI=F), which track spot prices within a small, well-understood basis.
Whichever series was actually used is labeled in the dashboard so you
always know what you're looking at.

This script needs a normal internet connection to Yahoo Finance. It will
not work in network-locked-down environments (e.g. some CI/sandbox
containers) - run it on your own computer.
"""

import json
import sys
import math
from datetime import datetime, timezone

try:
    import pandas as pd
except ImportError:
    sys.exit("Missing dependency 'pandas'. Install with: pip install pandas yfinance")

try:
    import yfinance as yf
except ImportError:
    sys.exit("Missing dependency 'yfinance'. Install with: pip install yfinance pandas")


# ---------------------------------------------------------------------------
# Config: each asset lists candidate Yahoo Finance tickers in priority order.
# The first ticker that returns usable data wins.
# ---------------------------------------------------------------------------
ASSETS = {
    "gold": {
        "label": "Gold",
        "candidates": [("XAUUSD=X", "Spot Gold (XAU/USD)"), ("GC=F", "COMEX Gold Futures (GC=F)")],
        "unit": "$/oz",
    },
    "silver": {
        "label": "Silver",
        "candidates": [("XAGUSD=X", "Spot Silver (XAG/USD)"), ("SI=F", "COMEX Silver Futures (SI=F)")],
        "unit": "$/oz",
    },
    "usd_index": {
        "label": "US Dollar Index",
        "candidates": [("DX-Y.NYB", "ICE US Dollar Index"), ("DX=F", "US Dollar Index Futures")],
        "unit": "index",
    },
    "yield_10y": {
        "label": "10-Year Treasury Yield",
        "candidates": [("^TNX", "CBOE 10-Year Treasury Yield")],
        "unit": "%",
        "divide_by": 10.0,  # Yahoo quotes ^TNX as yield * 10
    },
}

LOOKBACK_PERIOD = "2y"   # history pulled for MA/RSI calculations
DISPLAY_WINDOW_DAYS = 365  # how much of that history the charts actually show


# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------
def fetch_series(candidates):
    """Try each candidate ticker until one returns non-empty daily data."""
    for ticker, nice_name in candidates:
        try:
            df = yf.download(ticker, period=LOOKBACK_PERIOD, interval="1d",
                              progress=False, auto_adjust=True)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        df = df[["Close"]].rename(columns={"Close": "close"}).dropna()
        if len(df) < 30:
            continue
        return df, ticker, nice_name
    return None, None, None


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------
def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, math.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def pct_change_over(close, trading_days):
    if len(close) <= trading_days:
        return None
    now = close.iloc[-1]
    then = close.iloc[-1 - trading_days]
    if then == 0 or pd.isna(then) or pd.isna(now):
        return None
    return (now / then - 1) * 100


def pct_change_ytd(close):
    this_year = close.index[-1].year
    ytd_slice = close[close.index.year == this_year]
    if ytd_slice.empty:
        return None
    start = ytd_slice.iloc[0]
    now = close.iloc[-1]
    if start == 0 or pd.isna(start):
        return None
    return (now / start - 1) * 100


def detect_recent_cross(ma_fast, ma_slow, lookback=10):
    """Return 'golden', 'death', or None if fast MA crossed slow MA in the
    last `lookback` sessions."""
    diff = (ma_fast - ma_slow).dropna()
    if len(diff) < lookback + 1:
        return None
    recent = diff.iloc[-(lookback + 1):]
    sign = (recent > 0).astype(int)
    changes = sign.diff().dropna()
    if (changes == 1).any():
        return "golden"
    if (changes == -1).any():
        return "death"
    return None


def classify_trend(price, ma50, ma200):
    if any(pd.isna(v) for v in (price, ma50, ma200)):
        return "insufficient-data"
    if price > ma50 > ma200:
        return "strong-uptrend"
    if price > ma50 and ma50 <= ma200:
        return "uptrend-forming"
    if price < ma50 < ma200:
        return "strong-downtrend"
    if price < ma50 and ma50 >= ma200:
        return "downtrend-forming"
    return "sideways"


def classify_rsi(rsi_value):
    if rsi_value is None or pd.isna(rsi_value):
        return "neutral"
    if rsi_value >= 70:
        return "overbought"
    if rsi_value <= 30:
        return "oversold"
    return "neutral"


def analyze_asset(df, key, meta):
    close = df["close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    rsi = compute_rsi(close, 14)

    daily_ret = close.pct_change()
    vol_20d_annualized = daily_ret.rolling(20).std() * math.sqrt(252) * 100  # %

    last_price = close.iloc[-1]
    last_ma20 = ma20.iloc[-1]
    last_ma50 = ma50.iloc[-1]
    last_ma200 = ma200.iloc[-1]
    last_rsi = rsi.iloc[-1]
    last_vol = vol_20d_annualized.iloc[-1]

    trend = classify_trend(last_price, last_ma50, last_ma200)
    cross = detect_recent_cross(ma50, ma200, lookback=10)
    rsi_state = classify_rsi(last_rsi)

    # trailing-1y percentile rank of current volatility (Low/Medium/High)
    vol_hist = vol_20d_annualized.dropna().iloc[-252:]
    vol_percentile = None
    if len(vol_hist) > 20 and not pd.isna(last_vol):
        vol_percentile = float((vol_hist < last_vol).mean() * 100)

    pct_changes = {
        "1D": pct_change_over(close, 1),
        "1W": pct_change_over(close, 5),
        "1M": pct_change_over(close, 21),
        "3M": pct_change_over(close, 63),
        "YTD": pct_change_ytd(close),
        "1Y": pct_change_over(close, 252),
    }

    display = df.iloc[-DISPLAY_WINDOW_DAYS:]
    dates = [d.strftime("%Y-%m-%d") for d in display.index]

    def series_or_none(s):
        s = s.reindex(display.index)
        return [None if pd.isna(v) else round(float(v), 4) for v in s]

    return {
        "key": key,
        "label": meta["label"],
        "unit": meta["unit"],
        "dates": dates,
        "close": series_or_none(close),
        "ma20": series_or_none(ma20),
        "ma50": series_or_none(ma50),
        "ma200": series_or_none(ma200),
        "rsi": series_or_none(rsi),
        "volatility": series_or_none(vol_20d_annualized),
        "last_price": None if pd.isna(last_price) else round(float(last_price), 4),
        "last_ma20": None if pd.isna(last_ma20) else round(float(last_ma20), 4),
        "last_rsi": None if pd.isna(last_rsi) else round(float(last_rsi), 2),
        "last_volatility": None if pd.isna(last_vol) else round(float(last_vol), 2),
        "vol_percentile": None if vol_percentile is None else round(vol_percentile, 1),
        "trend": trend,
        "recent_cross": cross,
        "rsi_state": rsi_state,
        "pct_changes": {k: (None if v is None else round(v, 2)) for k, v in pct_changes.items()},
    }


TREND_COPY = {
    "strong-uptrend": "Strong uptrend - price is above both the 50- and 200-day averages, and the 50-day is above the 200-day.",
    "uptrend-forming": "Uptrend forming - price is above the 50-day average, but the longer 200-day trend hasn't confirmed yet.",
    "strong-downtrend": "Strong downtrend - price is below both the 50- and 200-day averages, and the 50-day is below the 200-day.",
    "downtrend-forming": "Downtrend forming - price is below the 50-day average, but the longer 200-day trend hasn't confirmed yet.",
    "sideways": "Sideways / mixed - no clean alignment between price and the moving averages.",
    "insufficient-data": "Not enough history yet to classify the trend.",
}


# ---------------------------------------------------------------------------
# Build payload + render
# ---------------------------------------------------------------------------
def build_payload():
    assets = {}
    sources = {}
    for key, meta in ASSETS.items():
        df, ticker, nice_name = fetch_series(meta["candidates"])
        if df is None:
            print(f"  [warn] Could not fetch any data for {meta['label']}; skipping.")
            continue
        if meta.get("divide_by"):
            df = df / meta["divide_by"]
        result = analyze_asset(df, key, meta)
        result["source_ticker"] = ticker
        result["source_name"] = nice_name
        assets[key] = result
        sources[key] = nice_name
        print(f"  [ok] {meta['label']}: {nice_name} ({ticker}) - {len(df)} sessions, "
              f"last close {result['last_price']}")

    if "gold" not in assets:
        sys.exit("Could not fetch gold data at all - check your internet connection and try again.")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "assets": assets,
        "trend_copy": TREND_COPY,
        "signal": compute_signal(assets),
    }
    return payload


def render_dashboard(payload, out_path="gold_dashboard.html"):
    data_json = json.dumps(payload)
    html = HTML_TEMPLATE.replace("__GOLD_TRENDS_DATA__", data_json)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def print_summary(payload):
    gold = payload["assets"].get("gold")
    if not gold:
        return
    print("\n" + "=" * 60)
    print(f"GOLD TREND SUMMARY  ({payload['generated_at']})")
    print("=" * 60)
    print(f"Source: {gold['source_name']} ({gold['source_ticker']})")
    print(f"Last price: {gold['last_price']} {gold['unit']}")
    print(f"Trend: {TREND_COPY[gold['trend']]}")
    if gold["recent_cross"]:
        cross_word = "Golden cross (bullish)" if gold["recent_cross"] == "golden" else "Death cross (bearish)"
        print(f"Recent MA50/MA200 cross: {cross_word} in the last 10 sessions")
    print(f"RSI(14): {gold['last_rsi']} -> {gold['rsi_state']}")
    if gold["last_volatility"] is not None:
        pct_txt = f", higher than {gold['vol_percentile']}% of the last year" if gold["vol_percentile"] is not None else ""
        print(f"20D volatility (annualized): {gold['last_volatility']}%{pct_txt}")
    print("Change: " + ", ".join(
        f"{k} {v:+.2f}%" for k, v in gold["pct_changes"].items() if v is not None
    ))
    signal = payload.get("signal")
    if signal:
        print("-" * 60)
        print(f"Technical signal: {signal['label_text']}  (score {signal['score']:+d} of ±{signal['max_score']})")
        for f in signal["factors"]:
            print(f"  {'+' if f['points'] > 0 else ''}{f['points']:>2}  {f['name']}: {f['detail']}")
        for c in signal["cautions"]:
            print(f"  caution: {c}")
        for n in signal["context_notes"]:
            print(f"  context: {n}")
        print("  NOTE: mechanical summary of the indicators above, not financial advice.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Technical signal
# ---------------------------------------------------------------------------
# This is a transparent, rule-based summary of the indicators already on the
# dashboard - NOT investment advice, and not a "buy/short" instruction. It
# mechanically scores trend/momentum factors so you can see, at a glance,
# whether they broadly agree or conflict. Trend-following signals like this
# lag price, can whipsaw in choppy/sideways markets, and say nothing about
# your personal risk tolerance or position sizing. Always treat this as one
# input, not a decision.
SIGNAL_LABELS = {
    "bullish": "Bullish lean",
    "bearish": "Bearish lean",
    "mixed": "Mixed / no clear edge",
}


def compute_signal(assets):
    gold = assets.get("gold")
    if gold is None or gold.get("trend") == "insufficient-data":
        return None

    factors = []

    trend_points = {
        "strong-uptrend": 2, "uptrend-forming": 1, "sideways": 0,
        "downtrend-forming": -1, "strong-downtrend": -2,
    }.get(gold["trend"], 0)
    factors.append({
        "name": "Trend (price vs 50/200-day averages)",
        "detail": SIGNAL_LABELS["bullish"] if trend_points > 0 else SIGNAL_LABELS["bearish"] if trend_points < 0 else "Neutral",
        "points": trend_points,
    })

    ma20_points = 0
    if gold.get("last_ma20") is not None and gold.get("last_price") is not None:
        ma20_points = 1 if gold["last_price"] > gold["last_ma20"] else -1 if gold["last_price"] < gold["last_ma20"] else 0
    factors.append({
        "name": "Price vs 20-day average (short-term)",
        "detail": "Above" if ma20_points > 0 else "Below" if ma20_points < 0 else "At",
        "points": ma20_points,
    })

    cross_points = {"golden": 1, "death": -1}.get(gold["recent_cross"], 0)
    factors.append({
        "name": "Recent 50/200-day cross",
        "detail": "Golden cross (last 10 sessions)" if cross_points > 0 else "Death cross (last 10 sessions)" if cross_points < 0 else "None recently",
        "points": cross_points,
    })

    rsi_points = 0
    if gold.get("last_rsi") is not None:
        rsi_points = 1 if gold["last_rsi"] >= 55 else -1 if gold["last_rsi"] <= 45 else 0
    factors.append({
        "name": "Momentum (RSI vs midpoint)",
        "detail": f"RSI {gold['last_rsi']}" if gold.get("last_rsi") is not None else "n/a",
        "points": rsi_points,
    })

    week_change = gold["pct_changes"].get("1W")
    mom_points = 0
    if week_change is not None:
        mom_points = 1 if week_change > 0.1 else -1 if week_change < -0.1 else 0
    factors.append({
        "name": "1-week price change",
        "detail": f"{week_change:+.2f}%" if week_change is not None else "n/a",
        "points": mom_points,
    })

    score = sum(f["points"] for f in factors)
    if score >= 2:
        label = "bullish"
    elif score <= -2:
        label = "bearish"
    else:
        label = "mixed"

    cautions = []
    if gold.get("rsi_state") == "overbought":
        cautions.append("RSI is in overbought territory - momentum looks stretched, which raises pullback risk for anyone considering a fresh long here.")
    elif gold.get("rsi_state") == "oversold":
        cautions.append("RSI is in oversold territory - momentum looks stretched to the downside, which raises bounce risk for anyone considering a fresh short here.")
    if gold.get("vol_percentile") is not None and gold["vol_percentile"] >= 66:
        cautions.append("20-day volatility is elevated versus the past year - moves may be larger and choppier than usual; position size and stops accordingly.")

    context_notes = []
    usd = assets.get("usd_index")
    if usd is not None and usd["pct_changes"].get("1M") is not None and gold["pct_changes"].get("1M") is not None:
        gold_1m, usd_1m = gold["pct_changes"]["1M"], usd["pct_changes"]["1M"]
        if gold_1m * usd_1m < 0:
            context_notes.append("The US Dollar Index has moved opposite gold over the past month - the usual inverse relationship, which lines up with the read above.")
        elif gold_1m * usd_1m > 0:
            context_notes.append("The US Dollar Index has moved the same direction as gold over the past month - an atypical pairing, worth a second look before leaning on the trend alone.")
    yld = assets.get("yield_10y")
    if yld is not None and yld["pct_changes"].get("1M") is not None and gold["pct_changes"].get("1M") is not None:
        gold_1m, yld_1m = gold["pct_changes"]["1M"], yld["pct_changes"]["1M"]
        if gold_1m * yld_1m < 0:
            context_notes.append("The 10-year Treasury yield has moved opposite gold over the past month - consistent with gold's usual inverse relationship to rates.")
        elif gold_1m * yld_1m > 0:
            context_notes.append("The 10-year Treasury yield has moved the same direction as gold over the past month - not the usual pairing, worth noting.")

    return {
        "label": label,
        "label_text": SIGNAL_LABELS[label],
        "score": score,
        "max_score": 6,
        "factors": factors,
        "cautions": cautions,
        "context_notes": context_notes,
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gold Trend Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"></script>
<style>
  :root {
    color-scheme: light;
    --surface-1:      #fcfcfb;
    --page:           #f9f9f7;
    --text-primary:   #0b0b0b;
    --text-secondary: #52514e;
    --text-muted:     #898781;
    --gridline:       #e1e0d9;
    --baseline:       #c3c2b7;
    --border:         rgba(11,11,11,0.10);
    --series-1:       #2a78d6; /* blue   - gold price */
    --series-2:       #eb6834; /* orange - silver / MA50 */
    --series-3:       #1baf7a; /* aqua   - USD index / MA200 */
    --series-4:       #eda100; /* yellow - 10Y yield */
    --good:           #006300;
    --good-bg:        rgba(12,163,12,0.10);
    --warning:        #9a6b00;
    --warning-bg:     rgba(250,178,25,0.16);
    --critical:       #d03b3b;
    --critical-bg:    rgba(208,59,59,0.10);
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) {
      color-scheme: dark;
      --surface-1:      #1a1a19;
      --page:           #0d0d0d;
      --text-primary:   #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted:     #898781;
      --gridline:       #2c2c2a;
      --baseline:       #383835;
      --border:         rgba(255,255,255,0.10);
      --series-1:       #3987e5;
      --series-2:       #d95926;
      --series-3:       #199e70;
      --series-4:       #c98500;
      --good:           #0ca30c;
      --good-bg:        rgba(12,163,12,0.16);
      --warning:        #fab219;
      --warning-bg:     rgba(250,178,25,0.14);
      --critical:       #e66767;
      --critical-bg:    rgba(230,103,103,0.14);
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --surface-1:      #1a1a19;
    --page:           #0d0d0d;
    --text-primary:   #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted:     #898781;
    --gridline:       #2c2c2a;
    --baseline:       #383835;
    --border:         rgba(255,255,255,0.10);
    --series-1:       #3987e5;
    --series-2:       #d95926;
    --series-3:       #199e70;
    --series-4:       #c98500;
    --good:           #0ca30c;
    --good-bg:        rgba(12,163,12,0.16);
    --warning:        #fab219;
    --warning-bg:     rgba(250,178,25,0.14);
    --critical:       #e66767;
    --critical-bg:    rgba(230,103,103,0.14);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    background: var(--page);
    color: var(--text-primary);
    padding: 20px 16px 60px;
  }
  .wrap { max-width: 1080px; margin: 0 auto; }
  header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .subtitle { color: var(--text-secondary); font-size: 13px; margin: 0; }
  .theme-toggle {
    border: 1px solid var(--border); background: var(--surface-1); color: var(--text-secondary);
    border-radius: 8px; padding: 6px 12px; font-size: 12px; cursor: pointer;
  }
  .no-data { padding: 40px; text-align: center; color: var(--text-secondary); }

  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 20px; }
  .tile { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }
  .tile .label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .03em; margin-bottom: 6px; }
  .tile .value { font-size: 20px; font-weight: 600; }
  .tile .value.good { color: var(--good); }
  .tile .value.critical { color: var(--critical); }
  .delta { font-size: 12px; margin-top: 3px; color: var(--text-secondary); }
  .delta.good { color: var(--good); }
  .delta.critical { color: var(--critical); }

  .badge { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 600; padding: 3px 9px; border-radius: 999px; }
  .badge.good { color: var(--good); background: var(--good-bg); }
  .badge.warning { color: var(--warning); background: var(--warning-bg); }
  .badge.critical { color: var(--critical); background: var(--critical-bg); }
  .badge.muted { color: var(--text-secondary); background: var(--gridline); }

  .card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-bottom: 18px; }
  .card h2 { font-size: 15px; margin: 0 0 2px; }
  .card .card-sub { font-size: 12px; color: var(--text-muted); margin: 0 0 12px; }
  .card-head { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; }
  .chart-holder { position: relative; height: 300px; }
  .chart-holder.short { height: 150px; }

  .readout { font-size: 13px; line-height: 1.5; color: var(--text-secondary); margin: 10px 0 0; }
  .readout strong { color: var(--text-primary); }

  table.datatable { width: 100%; border-collapse: collapse; font-size: 12px; font-variant-numeric: tabular-nums; }
  table.datatable th, table.datatable td { text-align: right; padding: 5px 8px; border-bottom: 1px solid var(--gridline); }
  table.datatable th:first-child, table.datatable td:first-child { text-align: left; }
  table.datatable th { color: var(--text-muted); font-weight: 500; }
  .table-toggle { background: none; border: 1px solid var(--border); color: var(--text-secondary); border-radius: 8px; font-size: 12px; padding: 5px 10px; cursor: pointer; }
  .table-wrap { max-height: 260px; overflow: auto; margin-top: 10px; display: none; }
  .table-wrap.open { display: block; }

  .context-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
  .context-item .label { font-size: 12px; color: var(--text-muted); }
  .context-item .value { font-size: 16px; font-weight: 600; margin-top: 2px; }

  .signal-card { border-width: 1px; }
  .signal-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
  .signal-label { font-size: 19px; font-weight: 700; }
  .signal-bar-track { position: relative; height: 8px; border-radius: 999px; background: var(--gridline); margin: 4px 0 4px; }
  .signal-bar-mid { position: absolute; top: -3px; left: 50%; width: 2px; height: 14px; background: var(--baseline); }
  .signal-bar-fill { position: absolute; top: 0; height: 8px; border-radius: 999px; }
  .signal-bar-fill.good { background: var(--good); }
  .signal-bar-fill.critical { background: var(--critical); }
  .signal-bar-fill.muted { background: var(--text-muted); }
  .signal-bar-labels { display: flex; justify-content: space-between; font-size: 10px; color: var(--text-muted); margin-bottom: 14px; }

  .factor-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .factor-row { display: flex; justify-content: space-between; gap: 10px; font-size: 13px; padding: 7px 10px; border-radius: 8px; background: var(--page); }
  .factor-name { color: var(--text-secondary); }
  .factor-detail { font-weight: 600; white-space: nowrap; }
  .factor-detail.good { color: var(--good); }
  .factor-detail.critical { color: var(--critical); }

  .note-list { list-style: none; margin: 10px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .note-list li { font-size: 12.5px; line-height: 1.5; padding: 8px 10px; border-radius: 8px; }
  .note-list.cautions li { background: var(--warning-bg); color: var(--text-primary); }
  .note-list.context li { background: var(--page); color: var(--text-secondary); }

  .disclaimer { font-size: 11.5px; line-height: 1.5; color: var(--text-muted); border-top: 1px solid var(--gridline); margin-top: 14px; padding-top: 10px; }

  footer { color: var(--text-muted); font-size: 11px; text-align: center; margin-top: 24px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>Gold Trend Dashboard</h1>
      <p class="subtitle" id="generatedAt">-</p>
    </div>
    <button class="theme-toggle" id="themeToggle" type="button">Toggle dark mode</button>
  </header>

  <div id="content"></div>

  <footer>
    Generated locally by gold_trends.py. Data via Yahoo Finance (free, delayed up to ~15-20 min for spot/futures). Educational tool, not investment advice - always confirm against a live quote before trading.
  </footer>
</div>

<script>
const DATA = __GOLD_TRENDS_DATA__;

const TREND_LABEL = {
  "strong-uptrend": "Strong uptrend",
  "uptrend-forming": "Uptrend forming",
  "strong-downtrend": "Strong downtrend",
  "downtrend-forming": "Downtrend forming",
  "sideways": "Sideways / mixed",
  "insufficient-data": "Not enough data",
};
const TREND_TONE = {
  "strong-uptrend": "good",
  "uptrend-forming": "good",
  "strong-downtrend": "critical",
  "downtrend-forming": "critical",
  "sideways": "warning",
  "insufficient-data": "warning",
};
const RSI_LABEL = { overbought: "Overbought", oversold: "Oversold", neutral: "Neutral" };
const RSI_TONE = { overbought: "critical", oversold: "good", neutral: "warning" };
const SIGNAL_TONE = { bullish: "good", bearish: "critical", mixed: "muted" };

function fmt(n, digits) {
  if (n === null || n === undefined || Number.isNaN(n)) return "-";
  return n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
function fmtPct(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return "-";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}
function toneClass(n) {
  if (n === null || n === undefined) return "";
  return n > 0 ? "good" : n < 0 ? "critical" : "";
}
function ordinal(n) {
  const rounded = Math.round(n);
  const rem100 = rounded % 100;
  if (rem100 >= 11 && rem100 <= 13) return `${rounded}th`;
  switch (rounded % 10) {
    case 1: return `${rounded}st`;
    case 2: return `${rounded}nd`;
    case 3: return `${rounded}rd`;
    default: return `${rounded}th`;
  }
}
function arrow(n) {
  if (n === null || n === undefined) return "";
  return n > 0 ? "▲" : n < 0 ? "▼" : "–";
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// horizontal reference-line plugin (RSI 30/70 bands) - keeps us off an
// extra CDN dependency for a couple of static lines.
const refLinePlugin = {
  id: "refLines",
  afterDraw(chart, args, opts) {
    const lines = opts && opts.lines;
    if (!lines) return;
    const { ctx, chartArea, scales } = chart;
    const y = scales.y;
    ctx.save();
    lines.forEach((line) => {
      const yPos = y.getPixelForValue(line.value);
      ctx.strokeStyle = line.color;
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(chartArea.left, yPos);
      ctx.lineTo(chartArea.right, yPos);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = line.color;
      ctx.font = "11px system-ui, sans-serif";
      ctx.fillText(line.label, chartArea.left + 4, yPos - 4);
    });
    ctx.restore();
  },
};
Chart.register(refLinePlugin);

Chart.defaults.font.family = "system-ui, -apple-system, 'Segoe UI', sans-serif";

function baseGrid() {
  return { color: cssVar("--gridline"), drawTicks: false };
}
function baseTicks(extra) {
  return Object.assign({ color: cssVar("--text-muted"), font: { size: 11 }, maxRotation: 0 }, extra || {});
}

let priceChart, rsiChart, compareChart;

function renderPriceChart(gold) {
  const ctx = document.getElementById("priceChart").getContext("2d");
  if (priceChart) priceChart.destroy();
  priceChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: gold.dates,
      datasets: [
        { label: `Gold (${gold.source_name})`, data: gold.close, borderColor: cssVar("--series-1"), backgroundColor: "transparent", borderWidth: 2, pointRadius: 0, tension: 0.15 },
        { label: "50-day average", data: gold.ma50, borderColor: cssVar("--series-2"), backgroundColor: "transparent", borderWidth: 1.5, pointRadius: 0, tension: 0.15 },
        { label: "200-day average", data: gold.ma200, borderColor: cssVar("--series-3"), backgroundColor: "transparent", borderWidth: 1.5, pointRadius: 0, tension: 0.15 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom", labels: { color: cssVar("--text-secondary"), boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          backgroundColor: cssVar("--surface-1"), titleColor: cssVar("--text-primary"), bodyColor: cssVar("--text-secondary"),
          borderColor: cssVar("--border"), borderWidth: 1, padding: 10,
          callbacks: { label: (c) => `${c.dataset.label}: $${fmt(c.parsed.y, 2)}` },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: baseTicks({ maxTicksLimit: 8 }) },
        y: { grid: baseGrid(), ticks: baseTicks({ callback: (v) => "$" + fmt(v, 0) }), border: { color: cssVar("--baseline") } },
      },
    },
  });
}

function renderRsiChart(gold) {
  const ctx = document.getElementById("rsiChart").getContext("2d");
  if (rsiChart) rsiChart.destroy();
  rsiChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: gold.dates,
      datasets: [
        { label: "RSI (14)", data: gold.rsi, borderColor: cssVar("--series-1"), backgroundColor: "transparent", borderWidth: 2, pointRadius: 0, tension: 0.15 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        refLines: { lines: [
          { value: 70, color: cssVar("--critical"), label: "Overbought (70)" },
          { value: 30, color: cssVar("--good"), label: "Oversold (30)" },
        ]},
        tooltip: {
          backgroundColor: cssVar("--surface-1"), titleColor: cssVar("--text-primary"), bodyColor: cssVar("--text-secondary"),
          borderColor: cssVar("--border"), borderWidth: 1, padding: 10,
          callbacks: { label: (c) => `RSI: ${fmt(c.parsed.y, 1)}` },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: baseTicks({ maxTicksLimit: 8 }) },
        y: { min: 0, max: 100, grid: baseGrid(), ticks: baseTicks(), border: { color: cssVar("--baseline") } },
      },
    },
  });
}

function indexTo100(series) {
  const base = series.find((v) => v !== null && v !== undefined);
  if (!base) return series.map(() => null);
  return series.map((v) => (v === null || v === undefined ? null : (v / base) * 100));
}

function renderCompareChart(assets) {
  const ctx = document.getElementById("compareChart").getContext("2d");
  if (compareChart) compareChart.destroy();
  const order = [
    { key: "gold", color: "--series-1" },
    { key: "silver", color: "--series-2" },
    { key: "usd_index", color: "--series-3" },
    { key: "yield_10y", color: "--series-4" },
  ];
  const datasets = [];
  let labels = null;
  order.forEach((o) => {
    const a = assets[o.key];
    if (!a) return;
    labels = labels || a.dates;
    datasets.push({
      label: a.label, data: indexTo100(a.close), borderColor: cssVar(o.color),
      backgroundColor: "transparent", borderWidth: 2, pointRadius: 0, tension: 0.15,
    });
  });
  compareChart = new Chart(ctx, {
    type: "line",
    data: { labels: labels || [], datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom", labels: { color: cssVar("--text-secondary"), boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          backgroundColor: cssVar("--surface-1"), titleColor: cssVar("--text-primary"), bodyColor: cssVar("--text-secondary"),
          borderColor: cssVar("--border"), borderWidth: 1, padding: 10,
          callbacks: { label: (c) => `${c.dataset.label}: ${fmt(c.parsed.y, 1)} (indexed)` },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: baseTicks({ maxTicksLimit: 8 }) },
        y: { grid: baseGrid(), ticks: baseTicks(), border: { color: cssVar("--baseline") } },
      },
    },
  });
}

function buildTable(gold) {
  const rows = gold.dates.map((d, i) => ({
    date: d, close: gold.close[i], ma50: gold.ma50[i], ma200: gold.ma200[i], rsi: gold.rsi[i],
  })).reverse().slice(0, 90);
  const body = rows.map((r) => `
    <tr>
      <td>${r.date}</td>
      <td>${r.close === null ? "-" : "$" + fmt(r.close, 2)}</td>
      <td>${r.ma50 === null ? "-" : "$" + fmt(r.ma50, 2)}</td>
      <td>${r.ma200 === null ? "-" : "$" + fmt(r.ma200, 2)}</td>
      <td>${r.rsi === null ? "-" : fmt(r.rsi, 1)}</td>
    </tr>`).join("");
  return `<table class="datatable">
    <thead><tr><th>Date</th><th>Close</th><th>50D avg</th><th>200D avg</th><th>RSI</th></tr></thead>
    <tbody>${body}</tbody>
  </table>`;
}

function render() {
  const assets = DATA.assets;
  const gold = assets.gold;
  const content = document.getElementById("content");

  if (!gold) {
    content.innerHTML = `<div class="no-data">No gold data available in this run. Re-run gold_trends.py with a working internet connection.</div>`;
    return;
  }

  document.getElementById("generatedAt").textContent =
    `Updated ${new Date(DATA.generated_at).toLocaleString()} - source: ${gold.source_name} (${gold.source_ticker})`;

  const pc = gold.pct_changes;
  const tiles = [
    { label: "Last price", value: `$${fmt(gold.last_price, 2)}`, delta: null },
    { label: "1 day", value: fmtPct(pc["1D"]), tone: toneClass(pc["1D"]) },
    { label: "1 week", value: fmtPct(pc["1W"]), tone: toneClass(pc["1W"]) },
    { label: "1 month", value: fmtPct(pc["1M"]), tone: toneClass(pc["1M"]) },
    { label: "YTD", value: fmtPct(pc["YTD"]), tone: toneClass(pc["YTD"]) },
    { label: "1 year", value: fmtPct(pc["1Y"]), tone: toneClass(pc["1Y"]) },
  ];
  const tilesHtml = tiles.map((t) => `
    <div class="tile">
      <div class="label">${t.label}</div>
      <div class="value ${t.tone || ""}">${t.value}</div>
    </div>`).join("");

  const trendTone = TREND_TONE[gold.trend] || "warning";
  const rsiTone = RSI_TONE[gold.rsi_state] || "warning";
  let crossNote = "";
  if (gold.recent_cross === "golden") {
    crossNote = `<span class="badge good">↑ Golden cross in last 10 sessions</span>`;
  } else if (gold.recent_cross === "death") {
    crossNote = `<span class="badge critical">↓ Death cross in last 10 sessions</span>`;
  }

  const volTone = gold.vol_percentile === null ? "muted" : gold.vol_percentile >= 66 ? "warning" : "muted";
  const volWord = gold.vol_percentile === null ? "n/a" : gold.vol_percentile >= 66 ? "High" : gold.vol_percentile <= 33 ? "Low" : "Medium";

  const silver = assets.silver;
  const usd = assets.usd_index;
  const yld = assets.yield_10y;
  const contextItems = [];
  if (silver) {
    contextItems.push(`<div class="context-item"><div class="label">Silver</div><div class="value">$${fmt(silver.last_price, 2)} <span class="${toneClass(silver.pct_changes["1D"])}" style="font-size:12px">${fmtPct(silver.pct_changes["1D"])} 1D</span></div></div>`);
  }
  if (usd) {
    contextItems.push(`<div class="context-item"><div class="label">US Dollar Index</div><div class="value">${fmt(usd.last_price, 2)} <span class="${toneClass(usd.pct_changes["1D"])}" style="font-size:12px">${fmtPct(usd.pct_changes["1D"])} 1D</span></div></div>`);
  }
  if (yld) {
    contextItems.push(`<div class="context-item"><div class="label">10-Year Treasury Yield</div><div class="value">${fmt(yld.last_price, 2)}% <span class="${toneClass(yld.pct_changes["1D"])}" style="font-size:12px">${fmtPct(yld.pct_changes["1D"])} 1D</span></div></div>`);
  }

  const signal = DATA.signal;
  let signalHtml = "";
  if (signal) {
    const tone = SIGNAL_TONE[signal.label] || "muted";
    const pct = Math.max(-1, Math.min(1, signal.score / signal.max_score)); // -1..1
    const fillLeft = pct >= 0 ? 50 : 50 + pct * 50;
    const fillWidth = Math.abs(pct) * 50;
    const factorRows = signal.factors.map((f) => `
      <li class="factor-row">
        <span class="factor-name">${f.name}</span>
        <span class="factor-detail ${f.points > 0 ? "good" : f.points < 0 ? "critical" : ""}">${arrow(f.points)} ${f.detail}</span>
      </li>`).join("");
    const cautionItems = signal.cautions.map((c) => `<li>⚠ ${c}</li>`).join("");
    const contextItems2 = signal.context_notes.map((n) => `<li>${n}</li>`).join("");

    signalHtml = `
    <div class="card signal-card">
      <div class="signal-head">
        <div>
          <h2>Technical signal</h2>
          <p class="card-sub">A mechanical readout of the indicators below - not a recommendation.</p>
        </div>
        <span class="badge ${tone}" style="font-size:13px; padding:5px 12px;">${signal.label_text}</span>
      </div>

      <div class="signal-bar-track">
        <div class="signal-bar-mid"></div>
        <div class="signal-bar-fill ${tone}" style="left:${fillLeft}%; width:${fillWidth}%;"></div>
      </div>
      <div class="signal-bar-labels"><span>Bearish</span><span>Neutral</span><span>Bullish</span></div>

      <ul class="factor-list">${factorRows}</ul>

      ${cautionItems ? `<ul class="note-list cautions">${cautionItems}</ul>` : ""}
      ${contextItems2 ? `<ul class="note-list context">${contextItems2}</ul>` : ""}

      <p class="disclaimer">
        This score just adds up the trend/momentum indicators already on this page so you can see whether
        they agree or conflict - it is <strong>not</strong> financial advice, not a buy/sell/short
        recommendation, and it says nothing about position size or risk tolerance. Trend-following reads
        like this lag price and can whipsaw in choppy markets. Weigh it alongside your own research and
        risk management, and consider talking to a licensed financial advisor before trading.
      </p>
    </div>`;
  }

  content.innerHTML = `
    <div class="tiles">${tilesHtml}</div>
    ${signalHtml}

    <div class="card">
      <div class="card-head">
        <div>
          <h2>Trend read</h2>
          <p class="card-sub">Rule-based, from moving-average alignment - not a prediction.</p>
        </div>
        <span class="badge ${trendTone}">${TREND_LABEL[gold.trend]}</span>
      </div>
      <p class="readout">${DATA.trend_copy[gold.trend]}</p>
      <p class="readout">
        <span class="badge ${rsiTone}">RSI ${fmt(gold.last_rsi, 1)} - ${RSI_LABEL[gold.rsi_state]}</span>
        <span class="badge ${volTone}">Volatility: ${volWord}${gold.vol_percentile !== null ? ` (${ordinal(gold.vol_percentile)} pct, 1Y)` : ""}</span>
        ${crossNote}
      </p>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <h2>Gold price with 50 &amp; 200-day averages</h2>
          <p class="card-sub">${gold.source_name} - last ${gold.dates.length} sessions</p>
        </div>
        <button class="table-toggle" id="toggleTable" type="button">View as table</button>
      </div>
      <div class="chart-holder"><canvas id="priceChart"></canvas></div>
      <div class="table-wrap" id="tableWrap">${buildTable(gold)}</div>
    </div>

    <div class="card">
      <h2>Momentum - RSI (14)</h2>
      <p class="card-sub">Above 70 = historically overbought, below 30 = historically oversold.</p>
      <div class="chart-holder short"><canvas id="rsiChart"></canvas></div>
    </div>

    <div class="card">
      <h2>Gold vs. silver, US dollar and 10Y yield</h2>
      <p class="card-sub">All series indexed to 100 at the start of the window, so relative trends are comparable on one scale.</p>
      <div class="chart-holder"><canvas id="compareChart"></canvas></div>
      <div class="context-grid" style="margin-top:14px;">${contextItems.join("")}</div>
    </div>
  `;

  renderPriceChart(gold);
  renderRsiChart(gold);
  renderCompareChart(assets);

  document.getElementById("toggleTable").addEventListener("click", () => {
    document.getElementById("tableWrap").classList.toggle("open");
  });
}

document.getElementById("themeToggle").addEventListener("click", () => {
  const root = document.documentElement;
  const current = root.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  root.setAttribute("data-theme", next);
  render(); // re-render so Chart.js picks up new CSS variable colors
});

render();
</script>
</body>
</html>
"""


def main():
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Fetch gold/silver/USD/yield data and build a trend dashboard.")
    parser.add_argument("--output", "-o", default="gold_dashboard.html",
                         help="Path to write the dashboard HTML to (default: gold_dashboard.html). "
                              "Parent directories are created automatically - useful for CI, e.g. "
                              "--output site/index.html")
    args = parser.parse_args()

    print("Fetching market data...")
    payload = build_payload()
    print_summary(payload)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    out = render_dashboard(payload, out_path=args.output)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
