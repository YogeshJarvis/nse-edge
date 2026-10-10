from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote
import re
import time

import feedparser
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# NSE EDGE: local research dashboard. Prices/news depend on public third-party endpoints.
IST = ZoneInfo("Asia/Kolkata")

st.set_page_config(
    page_title="NSE EDGE | Market Intelligence",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
:root { color-scheme: dark; }
.stApp { background: #080d16; color: #e5eaf3; }
[data-testid="stHeader"] { background: rgba(8,13,22,.92); }
[data-testid="stSidebar"] { background: #0d1422; border-right: 1px solid #1e293b; }
.block-container { padding-top: 1.25rem; padding-bottom: 2rem; max-width: 1600px; }
h1, h2, h3 { letter-spacing: -.025em; }
[data-testid="stMetric"] { background: #101827; border: 1px solid #243247; padding: 14px 16px; border-radius: 12px; }
[data-testid="stMetricLabel"] { color: #9fb0c7; }
[data-testid="stMetricValue"] { color: #f1f5f9; }
div[data-testid="stDataFrame"] { border: 1px solid #243247; border-radius: 10px; overflow: hidden; }
.stButton button { border-radius: 9px; }
.edge-card { background: #101827; border: 1px solid #243247; padding: 16px; border-radius: 12px; }
.edge-muted { color: #94a3b8; font-size: .86rem; }
.edge-pill { display:inline-block; padding: 3px 8px; border-radius: 999px; background:#172554; color:#bfdbfe; font-size:.78rem; }
hr { border-color: #243247; }
</style>
""", unsafe_allow_html=True)

# This is a practical starter universe, not a guaranteed complete/live official F&O list.
FO_SYMBOLS = [
    "ABB","ABCAPITAL","ABFRL","ACC","ADANIENSOL","ADANIENT","ADANIGREEN","ADANIPORTS",
    "ALKEM","AMBUJACEM","ANGELONE","APLAPOLLO","APOLLOHOSP","APOLLOTYRE","ASHOKLEY",
    "ASIANPAINT","ASTRAL","ATGL","AUBANK","AUROPHARMA","AXISBANK","BAJAJ-AUTO",
    "BAJAJFINSV","BAJFINANCE","BALKRISIND","BANDHANBNK","BANKBARODA","BANKINDIA",
    "BEL","BHARATFORG","BHARTIARTL","BHEL","BIOCON","BOSCHLTD","BPCL","BRITANNIA",
    "BSOFT","CANBK","CANFINHOME","CHOLAFIN","CIPLA","COALINDIA","COFORGE","COLPAL",
    "CONCOR","CROMPTON","CUMMINSIND","DABUR","DALBHARAT","DEEPAKNTR","DELHIVERY",
    "DIVISLAB","DIXON","DLF","DMART","DRREDDY","EICHERMOT","ESCORTS","EXIDEIND",
    "FEDERALBNK","GAIL","GLENMARK","GMRAIRPORT","GODREJCP","GODREJPROP","GRASIM",
    "HAL","HAVELLS","HCLTECH","HDFCAMC","HDFCBANK","HDFCLIFE","HEROMOTOCO","HINDALCO",
    "HINDPETRO","HINDUNILVR","HUDCO","ICICIBANK","ICICIGI","ICICIPRULI","IDEA",
    "IDFCFIRSTB","IEX","IGL","INDHOTEL","INDIANB","INDIGO","INDUSINDBK","INDUSTOWER",
    "INFY","IOC","IRCTC","IREDA","IRFC","ITC","JINDALSTEL","JIOFIN","JSWENERGY",
    "JSWSTEEL","JUBLFOOD","KALYANKJIL","KEI","KOTAKBANK","KPITTECH","LICHSGFIN",
    "LICI","LODHA","LT","LTF","LTIM","LTTS","LUPIN","M&M","MANAPPURAM","MARICO",
    "MARUTI","MAXHEALTH","MAZDOCK","MCX","MFSL","MOTHERSON","MPHASIS","MUTHOOTFIN",
    "NATIONALUM","NAUKRI","NBCC","NCC","NESTLEIND","NHPC","NMDC","NTPC","NYKAA",
    "OBEROIRLTY","OFSS","OIL","ONGC","PAGEIND","PAYTM","PERSISTENT","PETRONET",
    "PFC","PHOENIXLTD","PIDILITIND","PIIND","PNB","POLICYBZR","POLYCAB","POWERGRID",
    "POWERINDIA","PRAJIND","PRESTIGE","PVRINOX","RAMCOCEM","RBLBANK","RECLTD",
    "RELIANCE","SAIL","SBICARD","SBILIFE","SBIN","SHREECEM","SHRIRAMFIN","SIEMENS",
    "SOLARINDS","SONACOMS","SRF","SUNPHARMA","SUPREMEIND","SYNGENE","TATACHEM",
    "TATACOMM","TATACONSUM","TATAELXSI","TATAMOTORS","TATAPOWER","TATASTEEL","TCS",
    "TECHM","TIINDIA","TITAGARH","TITAN","TORNTPHARM","TRENT","TVSMOTOR","UBL",
    "ULTRACEMCO","UNITDSPR","UNOMINDA","UPL","VEDL","VOLTAS","WIPRO","YESBANK","ZEEL",
    "ZYDUSLIFE"
]
# De-duplicate while preserving order
FO_SYMBOLS = list(dict.fromkeys(FO_SYMBOLS))

CATALYST_RULES = [
    ("Strong", ["acquisition", "merger", "large order", "major order", "contract worth",
                "block deal", "open offer", "fraud", "ban", "default", "resignation of ceo",
                "resigns as ceo", "guidance cut", "guidance raised", "results", "quarterly results",
                "net profit", "profit jumps", "profit falls", "usfda", "us fda", "insolvency"]),
    ("Medium", ["order win", "new order", "approval", "dividend", "capacity", "production",
                "partnership", "stake sale", "stake sold", "fund raising", "fundraising",
                "rating upgrade", "rating downgrade", "promoter", "plant", "revenue rises"]),
]

def catalyst_strength(text: str) -> str:
    t = (text or "").lower()
    for level, words in CATALYST_RULES:
        if any(w in t for w in words):
            return level
    return "Weak / review"

def fetch_prices(symbols: list[str], period: str = "3mo") -> tuple[pd.DataFrame, str | None]:
    tickers = [f"{s}.NS" for s in symbols]
    try:
        data = yf.download(
            tickers=tickers,
            period=period,
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            progress=False,
            threads=True,
            timeout=20,
        )
        if data is None or data.empty:
            return pd.DataFrame(), "Yahoo Finance returned no price data."
        closes = {}
        if isinstance(data.columns, pd.MultiIndex):
            level0 = set(data.columns.get_level_values(0))
            for symbol in symbols:
                ticker = f"{symbol}.NS"
                if ticker in level0 and (ticker, "Close") in data.columns:
                    closes[symbol] = data[(ticker, "Close")].dropna()
                elif ticker in level0 and (ticker, "Adj Close") in data.columns:
                    closes[symbol] = data[(ticker, "Adj Close")].dropna()
        else:
            # Fallback for one ticker
            symbol = symbols[0]
            col = "Close" if "Close" in data.columns else "Adj Close"
            if col in data.columns:
                closes[symbol] = data[col].dropna()
        if not closes:
            return pd.DataFrame(), "No usable closing-price columns were returned."
        frame = pd.DataFrame(closes).sort_index()
        frame.index = pd.to_datetime(frame.index).tz_localize(None)
        return frame, None
    except Exception as exc:
        return pd.DataFrame(), f"Price download failed: {exc}"

def build_movers(close: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for symbol in close.columns:
        series = close[symbol].dropna()
        if len(series) < 2:
            continue
        last = float(series.iloc[-1])
        prev = float(series.iloc[-2])
        day = (last / prev - 1) * 100 if prev else None
        week_base = float(series.iloc[-6]) if len(series) >= 6 else None
        month_base = float(series.iloc[-22]) if len(series) >= 22 else None
        week = (last / week_base - 1) * 100 if week_base else None
        month = (last / month_base - 1) * 100 if month_base else None
        rows.append({
            "Symbol": symbol,
            "Last close (₹)": round(last, 2),
            "Daily %": round(day, 2) if day is not None else None,
            "Weekly %": round(week, 2) if week is not None else None,
            "Monthly %": round(month, 2) if month is not None else None,
            "Price date": pd.Timestamp(series.index[-1]).strftime("%d %b %Y"),
        })
    return pd.DataFrame(rows)

def fetch_google_news(query: str, days: int = 3, max_items: int = 40) -> list[dict]:
    rss_url = (
        "https://news.google.com/rss/search?q="
        + quote(f"{query} when:{days}d")
        + "&hl=en-IN&gl=IN&ceid=IN:en"
    )
    try:
        resp = requests.get(rss_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        items = []
        for entry in parsed.entries[:max_items]:
            title = entry.get("title", "Untitled")
            source = entry.get("source", {}).get("title", "Google News feed")
            published = entry.get("published", "Publication time not supplied")
            summary = re.sub("<[^>]+>", " ", entry.get("summary", "")).strip()
            items.append({
                "Headline": title,
                "Published (feed)": published,
                "Source": source,
                "Catalyst": catalyst_strength(title + " " + summary),
                "Link": entry.get("link", ""),
            })
        return items
    except Exception as exc:
        return [{"Headline": f"News feed unavailable: {exc}", "Published (feed)": "Unavailable",
                 "Source": "RSS error", "Catalyst": "N/A", "Link": ""}]

def fmt_pct(value):
    if pd.isna(value):
        return "—"
    return f"{value:+.2f}%"

now = datetime.now(IST)
st.markdown(
    f"<div class='edge-muted'>MARKET INTELLIGENCE / INDIA &nbsp; • &nbsp; "
    f"{now.strftime('%a, %d %b %Y')} &nbsp; • &nbsp; {now.strftime('%I:%M:%S %p IST')}</div>",
    unsafe_allow_html=True
)
st.title("NSE EDGE")
st.caption("F&O movers · Upcoming events · Evidence-based historical reaction")
st.markdown("---")

with st.sidebar:
    st.markdown("## Control room")
    st.caption("Local research prototype")
    page = st.radio("Workspace", [
        "Market overview", "Gainers & losers", "Catalyst scanner",
        "Event Radar", "Results watch", "Event reaction"
    ], label_visibility="collapsed")
    st.markdown("---")
    universe_size = st.selectbox("Universe size", [40, 80, 120, len(FO_SYMBOLS)], index=2)
    symbols = FO_SYMBOLS[:universe_size] if universe_size != len(FO_SYMBOLS) else FO_SYMBOLS
    if st.button("Refresh market data", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Prices are from Yahoo Finance and may be delayed, incomplete, or unavailable.")
    st.caption("News headlines are from Google News RSS. They are not official exchange timestamps.")

@st.cache_data(ttl=300, show_spinner=False)
def cached_prices(symbols_tuple):
    return fetch_prices(list(symbols_tuple))

@st.cache_data(ttl=600, show_spinner=False)
def cached_news(query, days, max_items):
    return fetch_google_news(query, days, max_items)

with st.spinner("Loading recent daily prices for the selected F&O universe..."):
    closes, price_error = cached_prices(tuple(symbols))

movers = build_movers(closes) if not closes.empty else pd.DataFrame()
last_data_date = movers["Price date"].max() if not movers.empty else "Unavailable"

if page == "Market overview":
    st.subheader("Market pulse")
    if not movers.empty:
        day_avg = movers["Daily %"].mean()
        advancing = int((movers["Daily %"] > 0).sum())
        declining = int((movers["Daily %"] < 0).sum())
        best = movers.sort_values("Daily %", ascending=False).iloc[0]
        worst = movers.sort_values("Daily %", ascending=True).iloc[0]
        a, b, c, d = st.columns(4)
        a.metric("Stocks scanned", len(movers))
        b.metric("Advancers / decliners", f"{advancing} / {declining}")
        c.metric("Average daily move", fmt_pct(day_avg))
        d.metric("Latest price date", last_data_date)
        left, right = st.columns(2)
        with left:
            st.markdown("### Top gainers · Daily")
            st.dataframe(movers.sort_values("Daily %", ascending=False).head(8),
                         hide_index=True, width="stretch")
        with right:
            st.markdown("### Top losers · Daily")
            st.dataframe(movers.sort_values("Daily %").head(8),
                         hide_index=True, width="stretch")
        st.markdown("### Strongest moves across timeframes")
        timeframe = st.segmented_control("Rank by", ["Daily %", "Weekly %", "Monthly %"],
                                         default="Daily %")
        if timeframe:
            st.dataframe(movers.sort_values(timeframe, ascending=False).head(12),
                         hide_index=True, width="stretch")
        st.caption("Returns use the latest available daily close, not guaranteed live intraday prices.")
    else:
        st.error(price_error or "No price data is available.")
        st.info("Check internet access or try a smaller universe in the sidebar.")

    st.markdown("---")
    st.markdown("### Latest broad market catalysts")
    def _load_overview_news():
        st.session_state["overview_news_data"] = cached_news(
            "India NSE stocks results order win corporate announcement", 2, 25
        )

    st.button("Load latest catalysts", key="overview_news_button", on_click=_load_overview_news)
    news = st.session_state.get("overview_news_data", [])
    if news:
        for item in news[:10]:
            with st.container(border=True):
                st.markdown(f"**{item['Headline']}**")
                st.caption(f"{item['Published (feed)']} · {item['Source']} · Catalyst heuristic: {item['Catalyst']}")
                if item["Link"]:
                    st.markdown(f"[Open source article]({item['Link']})")

elif page == "Gainers & losers":
    st.subheader("Performance scanner")
    period_choice = st.segmented_control(
        "Timeframe", ["Daily %", "Weekly %", "Monthly %"], default="Daily %"
    )
    if movers.empty:
        st.error(price_error or "No market data available.")
    else:
        top_n = st.slider("Rows per list", 5, 25, 10)
        left, right = st.columns(2)
        with left:
            st.markdown("### 🟢 Gainers")
            st.dataframe(movers.sort_values(period_choice, ascending=False).head(top_n),
                         hide_index=True, width="stretch")
        with right:
            st.markdown("### 🔴 Losers")
            st.dataframe(movers.sort_values(period_choice, ascending=True).head(top_n),
                         hide_index=True, width="stretch")
        st.download_button("Download all scanned returns (CSV)",
                           movers.to_csv(index=False).encode("utf-8"),
                           file_name="nse_edge_movers.csv", mime="text/csv")
        st.caption("Weekly ≈ 5 trading sessions; monthly ≈ 21 trading sessions. Price source: Yahoo Finance.")

elif page == "Catalyst scanner":
    st.subheader("News & catalyst scanner")
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Company, symbol, or topic", "NSE F&O stocks results order win")
    with col2:
        days = st.selectbox("Lookback", [1, 2, 3, 7], index=2)
    if st.button("Scan news", type="primary"):
        st.session_state["catalyst_news"] = cached_news(query, days, 60)
    items = st.session_state.get("catalyst_news", [])
    if items:
        filter_level = st.multiselect("Catalyst level", ["Strong", "Medium", "Weak / review"],
                                      default=["Strong", "Medium", "Weak / review"])
        visible = [x for x in items if x.get("Catalyst") in filter_level]
        for item in visible:
            with st.container(border=True):
                st.markdown(f"**{item['Headline']}**")
                st.caption(f"{item['Published (feed)']} · {item['Source']} · Heuristic: {item['Catalyst']}")
                if item["Link"]:
                    st.markdown(f"[Open article]({item['Link']})")
        st.warning("Catalyst levels are keyword-based triage, not an AI-verified materiality decision. Verify company-specific news on NSE/BSE.")
    else:
        st.info("Enter a topic or symbol, then click Scan news.")


elif page == "Event Radar":
    st.subheader("Event Radar · upcoming catalysts + historical evidence")
    st.write(
        "Track what may be coming, record the official evidence, and compare it with "
        "the stock's previous reaction. Dates and times are never treated as confirmed "
        "unless you enter or verify an official source."
    )

    st.markdown("### 1 · Upcoming events")
    horizon = st.radio("Planning window", ["Next 7 days", "Next 30 days"], horizontal=True)
    lookback_days = 7 if horizon == "Next 7 days" else 30
    q1, q2 = st.columns([3, 1])
    with q1:
        event_query = st.text_input(
            "Search upcoming events / companies",
            "NSE F&O quarterly results board meeting order win dividend"
        )
    with q2:
        event_days = st.selectbox("News lookback", [1, 3, 7, 14], index=2)
    if st.button("Find event leads", type="primary", key="event_radar_search"):
        st.session_state["event_radar_news"] = cached_news(event_query, event_days, 50)
    event_items = st.session_state.get("event_radar_news", [])
    if event_items:
        st.caption(
            "These are news leads, not a verified future-events calendar. News lookback is "
            f"{event_days} days; planning window selected is {horizon}. Confirm future dates "
            "from the official filing before relying on them."
        )
        for item in event_items:
            with st.container(border=True):
                st.markdown(f"**{item.get('Headline', 'Untitled headline')}**")
                st.caption(
                    f"Published by feed: {item.get('Published (feed)', 'Time unavailable')} · "
                    f"{item.get('Source', 'Source unavailable')} · Triage: {item.get('Catalyst', 'Unclassified')}"
                )
                if item.get("Link"):
                    st.markdown(f"[Open article / evidence source]({item['Link']})")
                st.caption("Evidence status: NEWS LEAD ONLY · confirm event date/time and material facts in the official filing.")
    else:
        st.info("Click **Find event leads** to collect recent news that may point to upcoming catalysts.")

    st.markdown("### 2 · Evidence ledger")
    st.write("Record confirmed events and source URLs. This editable table is your audit trail; it does not invent a calendar.")
    if "event_ledger" not in st.session_state:
        st.session_state["event_ledger"] = pd.DataFrame([
            {
                "Symbol": "HCLTECH",
                "Event type": "Quarterly results",
                "Event date (YYYY-MM-DD)": "",
                "Release time (IST, HH:MM)": "",
                "Status": "Needs verification",
                "Official source URL": "",
                "Prior comparable event date": "",
                "Notes": ""
            }
        ])
    ledger = st.data_editor(
        st.session_state["event_ledger"],
        num_rows="dynamic",
        width="stretch",
        key="event_ledger_editor"
    )
    st.session_state["event_ledger"] = ledger
    st.download_button(
        "Export evidence ledger (CSV)",
        ledger.to_csv(index=False).encode("utf-8"),
        file_name="nse_edge_event_evidence_ledger.csv",
        mime="text/csv"
    )
    st.markdown(
        "- [NSE corporate announcements](https://www.nseindia.com/companies-listing/corporate-filings-announcements)  \n"
        "- [NSE financial results](https://www.nseindia.com/companies-listing/corporate-filings-financial-results)  \n"
        "- [BSE corporate announcements](https://www.bseindia.com/corporates/ann.html)"
    )

    st.markdown("### 3 · Automatically fetch recent intraday prices")
    st.write(
        "Fetch recent one-minute candles and compare the verified public release time with the price reaction. "
        "Yahoo Finance is a convenience source, not an official exchange feed; intraday history is limited and can be incomplete."
    )
    auto_c1, auto_c2 = st.columns(2)
    with auto_c1:
        sorted_symbols = sorted(FO_SYMBOLS)
        auto_symbol = st.selectbox(
            "Stock to analyze", sorted_symbols,
            index=sorted_symbols.index("ABB") if "ABB" in sorted_symbols else 0,
            key="auto_event_symbol"
        )
    with auto_c2:
        auto_release_dt = st.text_input(
            "Public news release time (IST)",
            value=(now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M"),
            help="Use verified public release time. Format: YYYY-MM-DD HH:MM.",
            key="auto_event_release_time"
        )
    if st.button("Fetch 1-minute data and calculate reaction", type="primary", key="auto_fetch_event_reaction"):
        try:
            ticker = f"{auto_symbol}.NS"
            with st.spinner(f"Fetching recent 1-minute candles for {ticker}..."):
                intraday = yf.download(
                    ticker, period="7d", interval="1m",
                    auto_adjust=False, progress=False, threads=False, timeout=25
                )
            if intraday is None or intraday.empty:
                st.error(
                    f"No 1-minute data returned for {ticker}. The symbol may be unsupported, the provider may be rate-limiting, "
                    "or the event may be outside the available intraday-history window."
                )
            else:
                if isinstance(intraday.columns, pd.MultiIndex):
                    intraday.columns = intraday.columns.get_level_values(0)
                intraday.columns = [str(c).strip().lower() for c in intraday.columns]
                if "adj close" in intraday.columns and "close" not in intraday.columns:
                    intraday = intraday.rename(columns={"adj close": "close"})
                required_cols = ["open", "high", "low", "close", "volume"]
                if not all(c in intraday.columns for c in required_cols):
                    st.error("The data provider returned an unexpected column layout; reaction calculation stopped.")
                else:
                    intraday = intraday[required_cols].copy().dropna(subset=["close"]).sort_index()
                    idx = pd.to_datetime(intraday.index)
                    # Yahoo's NSE timestamps may already be exchange-local or timezone-aware.
                    # Treat naive timestamps as IST; only convert timestamps that carry a timezone.
                    if idx.tz is None:
                        idx = idx.tz_localize(IST)
                    else:
                        idx = idx.tz_convert(IST)
                    intraday.index = idx
                    intraday.index.name = "timestamp"
                    release = pd.Timestamp(datetime.strptime(auto_release_dt.strip(), "%Y-%m-%d %H:%M")).tz_localize(IST)

                    before = intraday.loc[intraday.index < release]
                    after = intraday.loc[intraday.index >= release]
                    session_start = release.normalize() + pd.Timedelta(hours=9, minutes=15)
                    session_end = release.normalize() + pd.Timedelta(hours=15, minutes=30)
                    after_hours = release < session_start or release >= session_end

                    # If release is outside regular hours or on a non-trading day, use the next
                    # available session's opening bars and label it as a next-session reaction.
                    next_session_mode = False
                    if after.empty and after_hours:
                        future = intraday.loc[intraday.index > release]
                        if not future.empty:
                            first_date = future.index[0].date()
                            after = future.loc[[ts.date() == first_date for ts in future.index]].head(15)
                            prior = intraday.loc[intraday.index < after.index[0]]
                            if not prior.empty:
                                before = prior
                                next_session_mode = True

                    if after.empty:
                        st.warning(
                            "No candles at or after this release time were returned. Check the timestamp, "
                            "ticker coverage and Yahoo's recent intraday-history limit."
                        )
                    elif before.empty:
                        st.warning(
                            "No pre-event reference candle is available. Try a newer event date/time or use a provider "
                            "with longer intraday history. The app will not fabricate a baseline."
                        )
                    else:
                        # Avoid implying 15 consecutive minutes if timestamps have gaps.
                        after = after.head(15)
                        baseline = float(before.iloc[-1]["close"])
                        first_close = float(after.iloc[0]["close"])
                        end_close = float(after.iloc[-1]["close"])
                        max_high = float(after["high"].max())
                        min_low = float(after["low"].min())
                        total_volume = float(after["volume"].fillna(0).sum())
                        measured_minutes = max(1, int((after.index[-1] - after.index[0]).total_seconds() / 60) + 1)
                        a1, a2, a3, a4 = st.columns(4)
                        a1.metric("First bar vs baseline", f"{(first_close / baseline - 1) * 100:+.2f}%")
                        a2.metric("Window close vs baseline", f"{(end_close / baseline - 1) * 100:+.2f}%")
                        a3.metric("Max upside in window", f"{(max_high / baseline - 1) * 100:+.2f}%")
                        a4.metric("Max downside in window", f"{(min_low / baseline - 1) * 100:+.2f}%")
                        st.metric("Volume across measured bars", f"{total_volume:,.0f}")
                        if next_session_mode:
                            st.info(
                                "This announcement time was outside regular market hours or had no same-time candles. "
                                "The result is labelled as a next-available-session reaction, not an immediate 15-minute reaction."
                            )
                        if len(after) < 15 or measured_minutes > 15:
                            st.warning(
                                f"Only {len(after)} bars were measured across approximately {measured_minutes} minutes. "
                                "Treat this as a partial/gapped window, not a complete 15-minute sample."
                            )
                        chart = after[["close"]].copy()
                        chart.index = chart.index.strftime("%H:%M")
                        st.line_chart(chart)
                        display = after.reset_index()
                        st.dataframe(display, hide_index=True, width="stretch")
                        st.caption(
                            f"Ticker: {ticker} · Source: Yahoo Finance · Reference candle: {before.index[-1]} · "
                            f"Measured window: {after.index[0]} to {after.index[-1]}. "
                            "Verify the original announcement timestamp. Price reaction alone does not prove causation."
                        )
                        st.download_button(
                            "Download fetched intraday bars (CSV)",
                            intraday.reset_index().to_csv(index=False).encode("utf-8"),
                            file_name=f"{auto_symbol.lower()}_intraday_1m.csv",
                            mime="text/csv",
                            key="download_auto_intraday"
                        )
        except Exception as exc:
            st.error(f"Automatic intraday fetch failed: {exc}")
            st.info("Check the release timestamp format, internet connection and provider availability. Manual CSV upload remains available.")
    st.caption(
        "Data limitations: Yahoo intraday history is short-window and may be delayed or incomplete. "
        "For reliable historical event studies, connect a licensed intraday provider and an official announcement feed."
    )

    st.markdown("### 3 · Measure the first 15 minutes after release")
    st.write(
        "Upload a one-minute OHLCV CSV from a data provider. The file should contain timestamp, "
        "open, high, low, close and volume. Use timestamps in India time or include a timezone. "
        "For an announcement during market hours, the tool measures the first 15 one-minute bars "
        "at/after the release timestamp against the last bar before release. For pre-market or "
        "after-hours events, this measures the first 15 bars from the next available session, "
        "which must be interpreted separately."
    )
    up1, up2 = st.columns(2)
    with up1:
        intraday_file = st.file_uploader("One-minute OHLCV CSV", type=["csv"], key="event_intraday_csv")
    with up2:
        release_dt = st.text_input(
            "Public release timestamp (IST)",
            value=(now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M"),
            help="Format: YYYY-MM-DD HH:MM, e.g. 2026-10-09 14:32"
        )
    if intraday_file is not None:
        try:
            raw = pd.read_csv(intraday_file)
            raw.columns = [str(c).strip().lower() for c in raw.columns]
            aliases = {
                "datetime": "timestamp", "date": "timestamp", "time": "timestamp",
                "adj close": "close", "vol": "volume"
            }
            raw = raw.rename(columns={c: aliases.get(c, c) for c in raw.columns})
            required = {"timestamp", "open", "high", "low", "close", "volume"}
            missing = required - set(raw.columns)
            if missing:
                st.error("CSV is missing required columns: " + ", ".join(sorted(missing)))
                st.caption("Required headers: timestamp, open, high, low, close, volume")
            else:
                raw["timestamp"] = pd.to_datetime(raw["timestamp"], errors="coerce")
                for col in ["open", "high", "low", "close", "volume"]:
                    raw[col] = pd.to_numeric(raw[col], errors="coerce")
                raw = raw.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
                # Treat naive input timestamps as IST. Convert timezone-aware timestamps to IST.
                if raw["timestamp"].dt.tz is None:
                    raw["timestamp"] = raw["timestamp"].dt.tz_localize(IST, ambiguous="NaT", nonexistent="NaT")
                else:
                    raw["timestamp"] = raw["timestamp"].dt.tz_convert(IST)
                raw = raw.dropna(subset=["timestamp"])
                release = pd.Timestamp(datetime.strptime(release_dt.strip(), "%Y-%m-%d %H:%M")).tz_localize(IST)
                before = raw[raw["timestamp"] < release]
                after = raw[raw["timestamp"] >= release].head(15)
                if before.empty:
                    st.warning("No pre-release bar found. Upload data that includes at least one bar before the release.")
                elif len(after) < 15:
                    st.warning(f"Only {len(after)} bars found at/after release. The result is partial, not a full 15-minute reaction.")
                else:
                    baseline = float(before.iloc[-1]["close"])
                    first_close = float(after.iloc[0]["close"])
                    end_close = float(after.iloc[-1]["close"])
                    max_high = float(after["high"].max())
                    min_low = float(after["low"].min())
                    total_volume = float(after["volume"].fillna(0).sum())
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("First bar close vs baseline", f"{(first_close / baseline - 1) * 100:+.2f}%")
                    m2.metric("15-bar close vs baseline", f"{(end_close / baseline - 1) * 100:+.2f}%")
                    m3.metric("15-bar max upside", f"{(max_high / baseline - 1) * 100:+.2f}%")
                    m4.metric("15-bar max downside", f"{(min_low / baseline - 1) * 100:+.2f}%")
                    st.metric("Volume across measured bars", f"{total_volume:,.0f}")
                    chart_df = after.set_index("timestamp")[["open", "high", "low", "close"]]
                    st.line_chart(chart_df[["close"]])
                    st.dataframe(after, hide_index=True, width="stretch")
                    st.caption(
                        f"Baseline: last close before release at {before.iloc[-1]['timestamp']}. "
                        f"Measured window: {after.iloc[0]['timestamp']} to {after.iloc[-1]['timestamp']}. "
                        "This is an event-window calculation, not proof that the event caused the move."
                    )
                with st.expander("CSV format example"):
                    st.code(
                        "timestamp,open,high,low,close,volume\n"
                        "2026-10-09 14:31,100,100.2,99.9,100.1,12000\n"
                        "2026-10-09 14:32,100.1,101,100,100.8,35000",
                        language="csv"
                    )
        except Exception as exc:
            st.error(f"Could not process this CSV: {exc}")
            st.info("Check the timestamp format and numeric OHLCV columns, then upload again.")
    else:
        st.info("No intraday file uploaded yet. The first-15-minute result stays blank until real intraday evidence is supplied.")

    st.warning(
        "Evidence rules: keep the original official filing link and timestamp; do not substitute "
        "a news-feed publication time for the exchange receipt time; do not label a move as caused "
        "by the event without corroboration; and do not treat this research tool as a buy/sell signal."
    )

elif page == "Results watch":
    st.subheader("Results & board-meeting tracker")
    st.write("Track company events without inventing release times. This starter list is a reminder list only; verify every date from an official notice.")
    default_calendar = pd.DataFrame([
        {"Symbol": "HCLTECH", "Event": "Quarterly results", "Event date": "", "Release time (IST)": "Not announced; could be before, during, or after market hours", "Status": "Needs official verification", "Official URL": ""},
        {"Symbol": "RBLBANK", "Event": "Quarterly results", "Event date": "", "Release time (IST)": "Not announced; could be before, during, or after market hours", "Status": "Needs official verification", "Official URL": ""},
        {"Symbol": "DMART", "Event": "Quarterly results", "Event date": "", "Release time (IST)": "Not announced; could be before, during, or after market hours", "Status": "Needs official verification", "Official URL": ""},
    ])
    st.caption("Edit the rows below. These are placeholders, not claims that the events are confirmed for today.")
    edited = st.data_editor(default_calendar, num_rows="dynamic", width="stretch", key="calendar_editor")
    st.download_button("Export results watchlist CSV", edited.to_csv(index=False).encode("utf-8"),
                       file_name="nse_edge_results_watch.csv", mime="text/csv")
    st.markdown("### Official sources")
    st.markdown("- [NSE Corporate Announcements](https://www.nseindia.com/companies-listing/corporate-filings-announcements)")
    st.markdown("- [NSE Financial Results](https://www.nseindia.com/companies-listing/corporate-filings-financial-results)")
    st.markdown("- [BSE Corporate Announcements](https://www.bseindia.com/corporates/ann.html)")
    st.info("Official filing timestamps must be entered from the exchange record. News publication times and conference-call times are not exchange receipt times.")

elif page == "Event reaction":
    st.subheader("Event reaction lab")
    st.write("Inspect historical daily price moves around a known event date. This does not automatically prove the event caused the move.")
    if not closes.empty:
        selected = st.selectbox("F&O symbol", sorted(closes.columns))
        series = closes[selected].dropna()
        if not series.empty:
            hist = pd.DataFrame({"Close (₹)": series})
            hist["1-session %"] = hist["Close (₹)"].pct_change() * 100
            hist["5-session %"] = hist["Close (₹)"].pct_change(5) * 100
            hist["21-session %"] = hist["Close (₹)"].pct_change(21) * 100
            event_date = st.date_input("Known event date", value=now.date() - timedelta(days=1))
            idx = pd.to_datetime(event_date)
            earlier = hist.loc[hist.index <= idx]
            if earlier.empty:
                st.warning("No available price data on or before that date.")
            else:
                row = earlier.iloc[-1]
                a, b, c = st.columns(3)
                a.metric("1-session move", fmt_pct(row["1-session %"]))
                b.metric("5-session move", fmt_pct(row["5-session %"]))
                c.metric("21-session move", fmt_pct(row["21-session %"]))
                st.caption(f"Using closest available close on or before {event_date}. Latest source date: {hist.index[-1].date()}.")
            st.line_chart(hist["Close (₹)"].tail(60))
            st.dataframe(hist.tail(25).sort_index(ascending=False), width="stretch")
    else:
        st.error(price_error or "Price data unavailable; reaction lab needs daily closes.")

st.markdown("---")
st.caption(
    "NSE EDGE is a research prototype, not an execution system. Public data can be delayed, incomplete, rate-limited or corrected. "
    "Always verify material events and timestamps against official NSE/BSE filings. No trade is recommended by this app."
)
