# -*- coding: utf-8 -*-
"""
Telegram Crypto Analysis Bot - RENDER VERSION
"""

import logging
import os
import io
from typing import Optional
import requests
import pandas as pd
import numpy as np
from pycoingecko import CoinGeckoAPI
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from langdetect import detect
import matplotlib.pyplot as plt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN environment variable")

DEFAULT_VS_CURRENCY = "usd"
DEFAULT_DAYS = 120
DEFAULT_INTERVAL = "daily"
ENABLE_AFFILIATE_FOOTER = True
AFFILIATE_TEXT = "Try our free analytics — future pro tier coming soon."

# Initialize CoinGecko API
cg = CoinGeckoAPI()

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Helper functions
def cg_find_id_by_symbol_or_name(q: str) -> Optional[str]:
    try:
        res = cg.search(q)
        for c in res.get("coins", []):
            if c.get("symbol", "").lower() == q.lower():
                return c.get("id")
        for c in res.get("coins", []):
            if c.get("name", "").lower() == q.lower():
                return c.get("id")
        if res.get("coins"):
            return res["coins"][0]["id"]
    except Exception:
        return None
    return None

def cg_market_chart_df(coin_id: str, days: int = DEFAULT_DAYS,
                       vs: str = DEFAULT_VS_CURRENCY,
                       interval: str = DEFAULT_INTERVAL) -> Optional[pd.DataFrame]:
    try:
        data = cg.get_coin_market_chart_by_id(id=coin_id, vs_currency=vs, days=days, interval=interval)
        prices = data.get("prices", [])
        vols = data.get("total_volumes", [])
        if not prices:
            return None
        df_p = pd.DataFrame(prices, columns=["time", "price"])
        df_p["time"] = pd.to_datetime(df_p["time"], unit="ms")
        df_p.set_index("time", inplace=True)
        df_v = pd.DataFrame(vols, columns=["time", "volume"]) if vols else None
        if df_v is not None:
            df_v["time"] = pd.to_datetime(df_v["time"], unit="ms")
            df_v.set_index("time", inplace=True)
            df = df_p.join(df_v, how="left")
        else:
            df = df_p
            df["volume"] = float("nan")
        ohlc = df["price"].resample("1D").ohlc()
        vol = df["volume"].resample("1D").sum(min_count=1)
        out = ohlc.join(vol)
        out.dropna(how="any", inplace=True)
        out.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"}, inplace=True)
        return out
    except Exception:
        return None

def localize(text: str, lang: str = "en") -> str:
    messages = {
        "welcome": {
            "en": "Welcome! Send /analyze <symbol or token name> to get a professional technical analysis.",
            "pl": "Witaj! Wyślij /analyze <symbol lub nazwa tokena>, aby otrzymać profesjonalną analizę techniczną.",
        },
        "not_found": {
            "en": "❌ Sorry, I could not find this token.",
            "pl": "❌ Przykro mi, nie znalazłem tego tokena.",
        },
        "processing": {
            "en": "⏳ Fetching data and generating analysis...",
            "pl": "⏳ Pobieram dane i generuję analizę...",
        },
    }
    return messages.get(text, {}).get(lang, messages.get(text, {}).get("en", text))

# Simple RSI calculation
def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_lang = "en"
    try:
        user_lang = detect(update.effective_user.language_code or "en")
    except Exception:
        pass

    await update.message.reply_text(localize("welcome", user_lang))

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /analyze <symbol or token name>")
        return

    query = context.args[0]
    lang = "en"
    try:
        lang = detect(update.effective_user.language_code or "en")
    except Exception:
        pass

    await update.message.reply_text(localize("processing", lang))

    # Step 1: Find coin id
    coin_id = cg_find_id_by_symbol_or_name(query)
    if not coin_id:
        await update.message.reply_text(localize("not_found", lang))
        return

    # Step 2: Fetch OHLCV data
    df = cg_market_chart_df(coin_id, days=120)
    if df is None or df.empty:
        await update.message.reply_text(localize("not_found", lang))
        return

    # Step 3: Add indicators (simplified)
    df["RSI"] = calculate_rsi(df["Close"], 14)
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["SMA50"] = df["Close"].rolling(window=50).mean()
    df["BB_middle"] = df["Close"].rolling(window=20).mean()
    df["BB_std"] = df["Close"].rolling(window=20).std()
    df["BB_lower"] = df["BB_middle"] - (df["BB_std"] * 2)
    df["BB_upper"] = df["BB_middle"] + (df["BB_std"] * 2)
    
    # Simple MACD calculation
    ema12 = df["Close"].ewm(span=12).mean()
    ema26 = df["Close"].ewm(span=26).mean()
    df["MACD"] = ema12 - ema26

    # Step 4: Plot chart
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(df.index, df["Close"], label="Price", color="blue", linewidth=2)
    ax.plot(df.index, df["EMA20"], label="EMA20", color="orange", linewidth=1)
    ax.plot(df.index, df["SMA50"], label="SMA50", color="green", linewidth=1)
    ax.fill_between(df.index, df["BB_lower"], df["BB_upper"], color="gray", alpha=0.2, label="Bollinger Bands")
    ax.set_title(f"Technical Analysis: {query.upper()}", fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Save chart
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format="png", dpi=150, bbox_inches='tight')
    img_buf.seek(0)
    plt.close(fig)

    # Step 5: Analysis logic
    last_price = df["Close"].iloc[-1]
    rsi = df["RSI"].iloc[-1]
    macd = df["MACD"].iloc[-1]
    ema20 = df["EMA20"].iloc[-1]
    sma50 = df["SMA50"].iloc[-1]
    bb_upper = df["BB_upper"].iloc[-1]
    bb_lower = df["BB_lower"].iloc[-1]
    
    # Determine trend
    trend = "Bullish" if ema20 > sma50 else "Bearish"
    
    # Generate trading signals
    signal_type = "HOLD"
    entry_price = last_price
    stop_loss = None
    take_profit_1 = None
    take_profit_2 = None
    confidence = "LOW"
    
    # Long logic
    if trend == "Bullish" and rsi < 70 and macd > 0:
        signal_type = "LONG 🚀"
        entry_price = last_price
        stop_loss = max(bb_lower, last_price * 0.97)
        take_profit_1 = last_price * 1.05
        take_profit_2 = min(bb_upper, last_price * 1.08)
        
        confidence_score = 0
        if 30 < rsi < 60:
            confidence_score += 1
        if macd > 0:
            confidence_score += 1
        if ema20 > sma50:
            confidence_score += 1
        
        confidence = "HIGH" if confidence_score >= 3 else "MEDIUM" if confidence_score >= 2 else "LOW"
    
    # Short logic
    elif trend == "Bearish" and rsi > 30 and macd < 0:
        signal_type = "SHORT 📉"
        entry_price = last_price
        stop_loss = min(bb_upper, last_price * 1.03)
        take_profit_1 = last_price * 0.95
        take_profit_2 = max(bb_lower, last_price * 0.92)
        
        confidence_score = 0
        if 40 < rsi < 70:
            confidence_score += 1
        if macd < 0:
            confidence_score += 1
        if ema20 < sma50:
            confidence_score += 1
            
        confidence = "HIGH" if confidence_score >= 3 else "MEDIUM" if confidence_score >= 2 else "LOW"

    # Basic analysis text
    basic_analysis = (
        f"✅ **Analysis for {query.upper()}**\n"
        f"Price: ${last_price:.2f} USD\n"
        f"RSI: {rsi:.2f}\n"
        f"MACD: {macd:.2f}\n"
        f"EMA20 vs SMA50 trend: {trend}\n"
        f"Suggestion: {trend} momentum\n\n"
    )
    
    # Trading signal text
    if signal_type == "HOLD":
        trading_signal = (
            f"🔄 **TRADING SIGNAL: HOLD**\n"
            f"💰 Current Price: ${entry_price:.2f}\n"
            f"📊 Mixed signals - wait for clearer setup\n"
            f"⚠️ No clear entry opportunity\n\n"
        )
    else:
        confidence_emoji = {"HIGH": "🔥", "MEDIUM": "⚡", "LOW": "⚠️"}[confidence]
        trading_signal = (
            f"🎯 **TRADING SIGNAL: {signal_type}**\n\n"
            f"📍 **Entry:** ${entry_price:.2f}\n"
            f"🛑 **Stop Loss:** ${stop_loss:.2f}\n"
            f"🎯 **TP1:** ${take_profit_1:.2f}\n"
            f"🎯 **TP2:** ${take_profit_2:.2f}\n\n"
            f"📊 **Analysis:**\n"
            f"• RSI: {rsi:.2f}\n"
            f"• Trend: {trend}\n"
            f"• MACD: {'Bullish' if macd > 0 else 'Bearish'}\n\n"
            f"{confidence_emoji} **Confidence:** {confidence}\n\n"
            f"⚠️ *Risk Management: Never risk more than 2-3% per trade*\n\n"
        )

    # Combine texts
    analysis_text = basic_analysis + "=" * 40 + "\n" + trading_signal

    if ENABLE_AFFILIATE_FOOTER:
        analysis_text += f"{AFFILIATE_TEXT}"

    # Send results
    await update.message.reply_photo(photo=img_buf, caption=analysis_text, parse_mode="Markdown")

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("analyze", analyze))
    
    logger.info("Bot started successfully!")
    application.run_polling()

if __name__ == "__main__":
    main()
