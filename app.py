import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from sklearn.linear_model import LinearRegression
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator, SMAIndicator

try:
    from streamlit_autorefresh import st_autorefresh
    AUTO_REFRESH_AVAILABLE = True
except ImportError:
    AUTO_REFRESH_AVAILABLE = False


st.set_page_config(page_title="Market Signal Dashboard", layout="wide")


def to_float(value):
    return float(np.array(value).flatten()[0])


def prepare_data(ticker, period="6mo"):
    data = yf.download(ticker, period=period, progress=False)

    if data.empty:
        return None

    close = data["Close"].squeeze()

    data["RSI"] = RSIIndicator(close=close, window=14).rsi()

    macd = MACD(close=close)
    data["MACD"] = macd.macd()
    data["MACD_SIGNAL"] = macd.macd_signal()

    data["EMA20"] = EMAIndicator(close=close, window=20).ema_indicator()
    data["SMA50"] = SMAIndicator(close=close, window=50).sma_indicator()

    df = data.dropna().copy()
    df["Days"] = np.arange(len(df))

    return df


def get_signal(df):
    X = df[["Days", "RSI", "MACD", "MACD_SIGNAL", "EMA20", "SMA50"]]
    y = df["Close"]

    model = LinearRegression()
    model.fit(X, y)

    latest = df.iloc[-1]

    latest_rsi = to_float(latest["RSI"])
    latest_macd = to_float(latest["MACD"])
    latest_macd_signal = to_float(latest["MACD_SIGNAL"])
    latest_ema20 = to_float(latest["EMA20"])
    latest_sma50 = to_float(latest["SMA50"])
    current_price = to_float(latest["Close"])

    next_day = pd.DataFrame([{
        "Days": len(df),
        "RSI": latest_rsi,
        "MACD": latest_macd,
        "MACD_SIGNAL": latest_macd_signal,
        "EMA20": latest_ema20,
        "SMA50": latest_sma50
    }])
prediction = to_float(model.predict(next_day))
change_pct = ((prediction - current_price) / current_price) * 100

if change_pct > 1 and latest_ema20 > latest_sma50:
    signal = "BUY"

elif change_pct < -1 and latest_ema20 < latest_sma50:
    signal = "SELL"

else:
    signal = "WATCH"

confidence = min(abs(change_pct) * 20, 100)

trend = "Bullish" if latest_ema20 > latest_sma50 else "Bearish"

if latest_rsi > 70:
    rsi_status = "Overbought"

elif latest_rsi < 30:
    rsi_status = "Oversold"

else:
    rsi_status = "Neutral"    
return {
        "current_price": current_price,
        "prediction": prediction,
        "change_pct": change_pct,
        "signal": signal,
        "confidence": confidence,
        "rsi": latest_rsi,
        "rsi_status": rsi_status,
        "ema20": latest_ema20,
        "sma50": latest_sma50,
        "trend": trend
    }


st.sidebar.title("Controls")

if AUTO_REFRESH_AVAILABLE:
    auto_refresh = st.sidebar.checkbox("Auto Refresh", value=False)

    if auto_refresh:
        refresh_seconds = st.sidebar.selectbox("Refresh Every", [30, 60, 300])
        st_autorefresh(interval=refresh_seconds * 1000, key="market_refresh")
else:
    st.sidebar.warning("Auto-refresh not installed. Run: pip install streamlit-autorefresh")

watchlist = ["AAPL", "TSLA", "NVDA", "MU", "SPY", "QQQ", "BTC-USD", "ETH-USD"]

manual_ticker = st.sidebar.text_input("Ticker", "AAPL").upper()
selected_watch = st.sidebar.selectbox("Quick Watchlist", watchlist)

ticker = selected_watch if selected_watch else manual_ticker

period = st.sidebar.selectbox("History", ["6mo", "1y", "2y", "5y"])

st.title("Market Signal Dashboard")

df = prepare_data(ticker, period)

if df is None or df.empty:
    st.error("No market data found.")
    st.stop()

result = get_signal(df)

col1, col2, col3, col4 = st.columns(4)

col1.metric("Current Price", f"${result['current_price']:.2f}")
col2.metric("Predicted Price", f"${result['prediction']:.2f}")
col3.metric("Signal", result["signal"])
col4.metric("Confidence", f"{result['confidence']:.1f}%")

if result["signal"] == "BUY":
    st.success("BUY signal: prediction and trend structure are bullish.")
elif result["signal"] == "SELL":
    st.error("SELL signal: prediction and trend structure are bearish.")
else:
    st.warning("WATCH signal: setup is not strong enough yet.")

st.subheader("Candlestick Chart")

fig = go.Figure()

fig.add_trace(go.Candlestick(
    x=df.index,
    open=df["Open"].squeeze(),
    high=df["High"].squeeze(),
    low=df["Low"].squeeze(),
    close=df["Close"].squeeze(),
    name="Candles"
))

fig.add_trace(go.Scatter(
    x=df.index,
    y=df["EMA20"].squeeze(),
    mode="lines",
    name="EMA 20"
))

fig.add_trace(go.Scatter(
    x=df.index,
    y=df["SMA50"].squeeze(),
    mode="lines",
    name="SMA 50"
))

fig.update_layout(
    height=600,
    xaxis_rangeslider_visible=False
)

st.plotly_chart(fig, use_container_width=True)

st.subheader("Signal Breakdown")

st.write(f"""
Ticker: {ticker}

Current Price: ${result['current_price']:.2f}

Predicted Price: ${result['prediction']:.2f}

Expected Move: {result['change_pct']:.2f}%

Signal: {result['signal']}

Confidence: {result['confidence']:.1f}%

RSI: {result['rsi']:.2f} — {result['rsi_status']}

Trend: {result['trend']}

EMA 20: {result['ema20']:.2f}

SMA 50: {result['sma50']:.2f}
""")

st.subheader("Indicators")

st.dataframe(
    df[["Close", "RSI", "MACD", "MACD_SIGNAL", "EMA20", "SMA50"]].tail(10),
    use_container_width=True
)

st.subheader("Multi-Ticker Scanner")

scan_tickers = ["AAPL", "TSLA", "NVDA", "MU", "SPY", "QQQ", "BTC-USD", "ETH-USD"]

scanner_results = []

for scan_ticker in scan_tickers:
    try:
        scan_df = prepare_data(scan_ticker, "6mo")

        if scan_df is None or scan_df.empty:
            raise ValueError("No data")

        scan_result = get_signal(scan_df)

        scanner_results.append({
            "Ticker": scan_ticker,
            "Current Price": round(scan_result["current_price"], 2),
            "Predicted Price": round(scan_result["prediction"], 2),
            "Expected Move %": round(scan_result["change_pct"], 2),
            "Signal": scan_result["signal"],
            "Confidence %": round(scan_result["confidence"], 1),
            "RSI": round(scan_result["rsi"], 2),
            "Trend": scan_result["trend"]
        })

    except Exception as e:
        scanner_results.append({
            "Ticker": scan_ticker,
            "Current Price": "Error",
            "Predicted Price": "Error",
            "Expected Move %": "Error",
            "Signal": "ERROR",
            "Confidence %": 0,
            "RSI": "Error",
            "Trend": "Error"
        })

scanner_df = pd.DataFrame(scanner_results)

scanner_df = scanner_df.sort_values(
    by="Confidence %",
    ascending=False
)

st.dataframe(scanner_df, use_container_width=True)

top_buy = scanner_df[scanner_df["Signal"] == "BUY"]

if not top_buy.empty:
    best = top_buy.iloc[0]
    st.success(f"Strongest BUY setup: {best['Ticker']} with {best['Confidence %']}% confidence.")
else:
    st.info("No strong BUY setups found right now.")

st.caption("Educational prototype only. Not financial advice.")
