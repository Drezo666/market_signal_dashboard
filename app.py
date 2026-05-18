import streamlit as st
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email_alert(subject, message):
    try:
        sender_email = st.secrets["EMAIL_USER"]
        sender_password = st.secrets["EMAIL_PASSWORD"]

        receiver_email = [
            email.strip()
            for email in st.secrets["ALERT_RECEIVER"].split(",")
        ]

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = ", ".join(receiver_email)
        msg["Subject"] = subject

        msg.attach(MIMEText(message, "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)

        server.sendmail(
            sender_email,
            receiver_email,
            msg.as_string()
        )

        server.quit()

        st.success("Test email sent.")

    except Exception as e:
        st.error(f"Email failed: {e}")
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

if "sent_alerts" not in st.session_state:
    st.session_state.sent_alerts = set()
def to_float(value):
    return float(np.array(value).flatten()[0])

def to_1d(value):
    return np.asarray(value).reshape(-1)
    
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
    y = to_1d(df["Close"])

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
        "trend": trend,
        "ema20": latest_ema20,
        "sma50": latest_sma50
    }
    st.sidebar.title("Controls")

if AUTO_REFRESH_AVAILABLE:
    auto_refresh = st.sidebar.checkbox("Auto Refresh", value=False)

    if auto_refresh:
        refresh_seconds = st.sidebar.selectbox("Refresh Every", [30, 60, 300])
        st_autorefresh(interval=refresh_seconds * 1000, key="market_refresh")
else:
    st.sidebar.warning("Auto-refresh not installed. Run: pip install streamlit-autorefresh")

watchlist = ["AAPL", "TSLA", "NVDA", "MU", "SPY", "QQQ"]

manual_ticker = st.sidebar.text_input("Ticker", "AAPL").upper()
selected_watch = st.sidebar.selectbox("Quick Watchlist", watchlist)

ticker = selected_watch if selected_watch else manual_ticker

period = st.sidebar.selectbox("History", ["6mo", "1y", "2y", "5y"])

st.title("Market Signal Dashboard")

st.subheader("Alert Controls")
email_alerts = st.checkbox("Email Alerts", value=False)

if email_alerts:
    if st.button("Send Test Email"):
        send_email_alert(
            "Test Alert from Market Dashboard",
            "This is a test email. Your market alert system is connected."
        )
        st.success("Test email sent.")

if st.button("Reset Sent Alerts"):
    st.session_state.sent_alerts = set()
    st.success("Sent alerts reset.")

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

scan_tickers = ["AAPL", "TSLA", "NVDA", "MU", "SPY", "QQQ"]

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

if email_alerts:

    strong_alerts = scanner_df[
        (
            (scanner_df["Signal"] == "BUY") |
            (scanner_df["Signal"] == "SELL")
        ) &
        (scanner_df["Confidence %"] >= 70)
    ]

    if not strong_alerts.empty:

        best_alert = strong_alerts.iloc[0]

        subject = f"Market Alert: {best_alert['Ticker']} {best_alert['Signal']} Signal"

        message = f"""
Market Signal Alert

Ticker: {best_alert['Ticker']}
Signal: {best_alert['Signal']}
Confidence: {best_alert['Confidence %']}%

Current Price: ${best_alert['Current Price']}
Predicted Price: ${best_alert['Predicted Price']}
Expected Move: {best_alert['Expected Move %']}%

RSI: {best_alert['RSI']}
Trend: {best_alert['Trend']}

Educational signal only. Not financial advice.
"""

        alert_key = f"{best_alert['Ticker']}_{best_alert['Signal']}"

        if alert_key not in st.session_state.sent_alerts:

            send_email_alert(subject, message)

            st.session_state.sent_alerts.add(alert_key)

            st.success(f"Email alert sent for {best_alert['Ticker']} {best_alert['Signal']}.")

        else:
            st.info(f"Alert already sent for {best_alert['Ticker']} {best_alert['Signal']} this session.")

st.subheader("Backtest Results")

backtest_ticker = st.selectbox(
    "Backtest Ticker",
    scan_tickers,
    index=0
)

backtest_period = st.selectbox(
    "Backtest Period",
    ["6mo", "1y", "2y", "5y"],
    index=1
)

starting_balance = st.number_input(
    "Starting Balance",
    min_value=100.0,
    value=10000.0,
    step=100.0
)

bt_df = prepare_data(backtest_ticker, backtest_period)

if bt_df is not None and not bt_df.empty:

    bt_df = bt_df.copy()

    bt_df["Signal"] = "WATCH"

    bt_df.loc[
        (bt_df["EMA20"] > bt_df["SMA50"]) &
        (bt_df["RSI"] < 70),
        "Signal"
    ] = "BUY"

    bt_df.loc[
        (bt_df["EMA20"] < bt_df["SMA50"]) |
        (bt_df["RSI"] > 75),
        "Signal"
    ] = "SELL"

    cash = starting_balance
    shares = 0
    position_open = False
    trades = []

    for i in range(len(bt_df)):
        price = to_float(bt_df["Close"].iloc[i])
        signal = bt_df["Signal"].iloc[i]
        date = bt_df.index[i]

        if signal == "BUY" and not position_open:
            shares = cash / price
            cash = 0
            position_open = True
            entry_price = price
            entry_date = date

        elif signal == "SELL" and position_open:
            cash = shares * price
            shares = 0
            position_open = False

            trade_return = ((price - entry_price) / entry_price) * 100

            trades.append({
                "Entry Date": entry_date,
                "Exit Date": date,
                "Entry Price": round(entry_price, 2),
                "Exit Price": round(price, 2),
                "Return %": round(trade_return, 2)
            })

    final_price = to_float(bt_df["Close"].iloc[i])

    if position_open:
        ending_balance = shares * final_price
    else:
        ending_balance = cash

    total_return = ((ending_balance - starting_balance) / starting_balance) * 100

    buy_hold_return = (
        (to_float(bt_df["Close"].iloc[-1]) - to_float(bt_df["Close"].iloc[0]))
/ to_float(bt_df["Close"].iloc[0])
    ) * 100

    trades_df = pd.DataFrame(trades)

    if not trades_df.empty:
        wins = trades_df[trades_df["Return %"] > 0]
        win_rate = (len(wins) / len(trades_df)) * 100
        avg_trade_return = trades_df["Return %"].mean()
    else:
        win_rate = 0
        avg_trade_return = 0

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Starting Balance", f"${starting_balance:,.2f}")
    col2.metric("Ending Balance", f"${ending_balance:,.2f}")
    col3.metric("Strategy Return", f"{total_return:.2f}%")
    col4.metric("Buy & Hold", f"{buy_hold_return:.2f}%")

    col5, col6, col7 = st.columns(3)

    col5.metric("Trades", len(trades_df))
    col6.metric("Win Rate", f"{win_rate:.1f}%")
    col7.metric("Avg Trade", f"{avg_trade_return:.2f}%")

    if total_return > buy_hold_return:
        st.success("Strategy beat buy-and-hold during this period.")
    else:
        st.warning("Strategy did not beat buy-and-hold during this period.")

    st.subheader("Trade Log")
    st.dataframe(trades_df, use_container_width=True)

else:
    st.error("Backtest data could not be loaded.")

st.caption("Educational prototype only. Not financial advice.")
