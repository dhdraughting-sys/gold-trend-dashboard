# Gold Trend Dashboard

A trend-following tool for spot gold: `gold_trends.py` pulls recent price
history, computes the indicators trend-followers actually use, and writes a
single self-contained HTML dashboard (`gold_dashboard.html`) you open in any
browser.

## Setup (one time)

You need Python 3 on your own computer (this needs a normal internet
connection to Yahoo Finance, so it won't work inside a locked-down sandbox).

```
pip install yfinance pandas
```

## Run it

```
python3 gold_trends.py
```

This fetches fresh data, prints a plain-text trend summary to your terminal,
and writes `gold_dashboard.html` next to the script. Open that file in your
browser. Re-run the script whenever you want fresh numbers - once a day is
plenty for a swing-trading horizon; you can also wire it to Task
Scheduler/cron if you want it to refresh automatically every morning.

## What it shows

- **Gold price chart** with 50-day and 200-day moving averages, so you can
  see the trend at a glance and spot golden/death crosses.
- **RSI (14)** momentum panel - flags when gold looks historically
  overbought (>70) or oversold (<30).
- **Rolling 20-day volatility**, shown as a percentile against the last
  year, so you know if the current move is a normal wobble or unusually
  sharp.
- **% change** over 1 day / 1 week / 1 month / 3 months / YTD / 1 year.
- **Gold vs. silver, the US Dollar Index, and the 10-year Treasury yield**,
  all indexed to 100 so you can see how gold is moving relative to the
  dollar and rates - the two things that usually drive its trend.
- A plain-English "trend read" card (strong uptrend / uptrend forming /
  sideways / downtrend forming / strong downtrend) based on where price
  sits relative to its 50- and 200-day averages.
- A **technical signal** card: adds up five of the indicators already on
  the page (trend, price vs 20-day average, recent golden/death cross,
  RSI vs its midpoint, and 1-week momentum) into one "Bullish lean /
  Bearish lean / Mixed" read, with a transparent breakdown of exactly
  what fed into it, plus flags for overbought/oversold and elevated
  volatility, and how gold's move lines up with the dollar and yields.
  See the note below - this is a mechanical summary, not advice.
- A dark mode toggle and a "view as table" option on the price chart for
  the exact numbers.

## About the "technical signal" - please read

You asked whether the app could help you decide between buying and
shorting. I built the signal card above for that, but I want to be
upfront about what it is and isn't:

- It's arithmetic, not a forecast. It just adds up the same five
  indicators shown elsewhere on the dashboard (trend direction, short-term
  average, recent crossover, RSI, and last week's move) into a single
  score, so you can see at a glance whether they agree or conflict. It has
  no view on news, positioning, central bank policy, or anything not in
  the price series itself.
- It says nothing about position size, stop placement, or your personal
  risk tolerance - all of which matter more to trading outcomes than
  which way a trend indicator points.
- Trend indicators lag price by design (that's what the moving averages
  are) and they whipsaw in sideways/choppy markets - a "bullish lean" can
  flip to "bearish lean" a few sessions later with no news at all.
- I'm not a financial advisor and this isn't financial advice. Treat the
  signal as one input alongside your own judgment, and consider talking
  to a licensed advisor before trading, especially with leverage (which
  is inherent to shorting).

## Data source & honesty note

Data comes from Yahoo Finance via the free `yfinance` library - no API key,
but it can lag the true live tick by a few minutes and (rarely) has small
gaps. The script prefers true spot gold/silver tickers and automatically
falls back to the COMEX futures contract if spot data isn't available that
day; whichever one it used is always labeled at the top of the dashboard.
This is meant to help you read trends, not as a live execution price or
investment advice - always check a live quote before you actually trade.

## Customizing

Open `gold_trends.py` and look at the `ASSETS` dict near the top if you
want to swap tickers, and `LOOKBACK_PERIOD` / `DISPLAY_WINDOW_DAYS` if you
want more or less history. The moving-average windows (20/50/200) and RSI
period (14) are set where `analyze_asset()` is defined.

## Always-on version (check from your phone, no computer needed)

This package also includes `.github/workflows/update-dashboard.yml`, which
runs the script automatically on a schedule and publishes the dashboard to
a free GitHub Pages URL. I can't create the GitHub repo for you from here
(no access to your account), but the setup is about 5 minutes:

1. **Create a new repository** on [github.com](https://github.com) (public
   repos get free GitHub Pages; private works too on most plans). Any name
   is fine, e.g. `gold-trend-dashboard`.
2. **Upload the files**, keeping the folder structure exactly as delivered:
   - `gold_trends.py` at the repo root
   - `.github/workflows/update-dashboard.yml` (the `.github` folder name
     must match exactly - GitHub only recognizes workflows there)

   Easiest way: on the repo page, click **Add file → Upload files**, drag
   the whole unzipped folder in, and commit. (If you're comfortable with
   git: `git add . && git commit -m "init" && git push`.)
3. **Turn on Pages**: repo **Settings → Pages → Build and deployment
   → Source**, select **GitHub Actions**.
4. **Run it once manually**: go to the **Actions** tab → "Update Gold
   Trend Dashboard" → **Run workflow**. After it finishes (~1 minute),
   your dashboard is live at `https://<your-username>.github.io/<repo-name>/`
   - Settings → Pages shows the exact URL. Bookmark it on your phone.
5. After that, it refreshes on its own once a day (default: 12:00 UTC -
   edit the `cron:` line in the workflow file to change the time, or add
   more `cron:` lines to refresh more than once a day).

**One thing to know:** GitHub automatically disables scheduled workflows
after 60 days with no repo activity. If the dashboard ever looks stale,
open the Actions tab and click "Run workflow" - that also re-enables the
schedule. There's no cost for this at normal usage (public repos get
unlimited free Actions minutes; private repos get a generous free
monthly quota).
