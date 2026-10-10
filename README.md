# NSE EDGE - Local market scanner

## Install
Open Command Prompt in the project folder with `.venv` activated, then run:

    pip install -r requirements.txt

## Run

    streamlit run app.py

Open http://localhost:8501 if the browser does not open automatically.

## Current capabilities
- Daily, weekly (about 5 sessions), and monthly (about 21 sessions) performance ranks
- Public Google News RSS headlines with heuristic catalyst triage
- Editable/exportable results watchlist
- Historical close-return inspection around a user-entered event date
- Dark dashboard UI

## Important limitations
- Price data is from Yahoo Finance and can be delayed, incomplete, rate-limited, or unavailable.
- The included F&O universe is a starter list and is not guaranteed to be the complete current NSE derivatives universe.
- News timestamps are publisher/feed timestamps, not official NSE/BSE receipt timestamps.
- Catalyst ratings are keyword heuristics, not verified materiality assessments.
- The app does not place trades or produce guaranteed buy/sell signals.
- Results-calendar rows are placeholders until checked against official filings.


## Event Radar (evidence-first)
- News leads for possible upcoming catalysts; news leads are explicitly not treated as a confirmed calendar.
- Editable evidence ledger for official dates, times, links and comparable historical events.
- First-15-minute event-window calculator using a user-supplied one-minute OHLCV CSV.
- Requires a bar before the event timestamp and calculates first-bar, 15-bar close, high/low excursion and volume.
- For pre-market/after-hours releases, the next-session window needs separate interpretation.
- This does not prove causality and does not produce trade recommendations.
