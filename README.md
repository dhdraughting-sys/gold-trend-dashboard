# Gold Trend Dashboard

A trend-following tool for spot gold: `gold_trends.py` pulls recent price
history, computes the indicators trend-followers actually use, and writes a
single self-contained HTML dashboard (`gold_dashboard.html`) you open in any
browser.

## Setup (one time)

You need Python 3 on your own computer (this needs a normal internet
connection to Yahoo Finance, so it won't work inside a locked-down sandbox).

```
pip install yfinance pandas pillow
```

(`pillow` is only used to draw the small app icon for "Add to Home Screen" below - the dashboard itself works fine without it, just with a generic icon.)

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
- A dark mode toggle and a "view as table" option on the price chart for
  the exact numbers.
- A big glanceable "hero" number up top (current price, today's move, and
  the trend/signal in one line) with a horizontally-scrolling strip of
  1D/1W/1M/3M/YTD/1Y changes underneath - opens like a weather app rather
  than a spreadsheet.

## Make it feel like an app (Add to Home Screen)

The dashboard now ships with a web app manifest and icon, so once it's
live on GitHub Pages you can add it to your phone's home screen and it
opens full-screen, with its own icon, no browser address bar:

- **iPhone (Safari):** open the dashboard link → tap the Share icon → **Add
  to Home Screen**.
- **Android (Chrome):** open the link → tap the **⋮** menu → **Add to Home
  screen** / **Install app**.

That's it - tapping the icon from then on opens straight to the dashboard.

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
2. **Add the files**, keeping the paths exactly as delivered:
   - `gold_trends.py` at the repo root
   - `.github/workflows/update-dashboard.yml` (the `.github` folder name
     must match exactly - GitHub only recognizes workflows there)

   `gold_trends.py` is safe to drag-and-drop via **Add file → Upload
   files**. For the workflow file, don't drag-and-drop the folder -
   browsers (especially on mobile) often silently drop the `.github` part
   since it's a hidden/dot-folder, and you end up with a `workflows/`
   folder at the repo root instead, which GitHub Actions never sees. Use
   this instead: **Add file → Create new file**, and in the "Name your
   file" box type the *whole path* `.github/workflows/update-dashboard.yml`
   - GitHub turns each `/` into a folder automatically. Then paste in the
   file's contents and commit. (If you're on a computer and comfortable
   with git: `git add . && git commit -m "init" && git push` avoids this
   problem entirely.)

   **If your dashboard was 404ing:** this is almost certainly why - check
   your repo for a `workflows/` folder (no `.github` in front) and/or a
   stray `update-dashboard.yml` sitting at the root. Delete both, then
   recreate the file at the correct path using the method above.
3. **Run it once manually**: go to the **Actions** tab → "Update Gold
   Trend Dashboard" → **Run workflow**. Wait ~1 minute for it to finish -
   this creates a new `gh-pages` branch in your repo with the built site.
4. **Turn on Pages**: repo **Settings → Pages → Build and deployment
   → Source**, select **Deploy from a branch**, then set **Branch** to
   `gh-pages` and the folder to `/ (root)`, and **Save**.
   (Some accounts/orgs only show "Deploy from a branch" as an option here,
   without a "GitHub Actions" choice - that's fine, this setup is built
   for exactly that case.)
5. Give it a minute, then your dashboard is live at
   `https://<your-username>.github.io/<repo-name>/` - Settings → Pages
   shows the exact URL once it's ready. Bookmark it on your phone.
6. After that, it refreshes on its own once a day (default: 12:00 UTC -
   edit the `cron:` line in the workflow file to change the time, or add
   more `cron:` lines to refresh more than once a day). Each run pushes a
   fresh commit to `gh-pages`, which Pages automatically republishes.

**One thing to know:** GitHub automatically disables scheduled workflows
after 60 days with no repo activity. If the dashboard ever looks stale,
open the Actions tab and click "Run workflow" - that also re-enables the
schedule. There's no cost for this at normal usage (public repos get
unlimited free Actions minutes; private repos get a generous free
monthly quota).
