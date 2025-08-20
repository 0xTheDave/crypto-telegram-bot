# -*- coding: utf-8 -*-
"""
Telegram Crypto Analysis Bot
Author: You
"""

import logging
import os
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from langdetect import detect
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
if not hasattr(np, 'NaN'):
    np.NaN = np.nan
import pandas_ta as ta

from src.config import TELEGRAM_BOT_TOKEN, IMG_DIR, ENABLE_AFFILIATE_FOOTER, AFFILIATE_TEXT
from src.data_sources import cg_find_id_by_symbol_or_name, cg_market_chart_df

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# --------- Helper: Detect language and respond accordingly ---------
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


# --------- Start Command ---------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_lang = "en"
    try:
        user_lang = detect(update.effective_user.language_code or "en")
    except Exception:
        pass

    await update.message.reply_text(localize("welcome", user_lang))


# --------- Analyze Command ---------
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

    # Step 3: Add indicators
    df["RSI"] = ta.rsi(df["Close"], length=14)
    df["MACD"] = ta.macd(df["Close"]).iloc[:, 0]
    df["EMA20"] = ta.ema(df["Close"], length=20)
    df["SMA50"] = ta.sma(df["Close"], length=50)
    bb = ta.bbands(df["Close"], length=20)
    df["BB_lower"] = bb["BBL_20_2.0"]
    df["BB_upper"] = bb["BBU_20_2.0"]

    # Step 4: Plot chart
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(df.index, df["Close"], label="Price", color="blue")
    ax.plot(df.index, df["EMA20"], label="EMA20", color="orange")
    ax.plot(df.index, df["SMA50"], label="SMA50", color="green")
    ax.fill_between(df.index, df["BB_lower"], df["BB_upper"], color="gray", alpha=0.2)
    ax.set_title(f"Technical Analysis: {query.upper()}")
    ax.legend()

    # Save chart
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format="png")
    img_buf.seek(0)
    plt.close(fig)

    # Step 5: NOWA LOGIKA - Generowanie poziomów tradingowych
    last_price = df["Close"].iloc[-1]
    rsi = df["RSI"].iloc[-1]
    macd = df["MACD"].iloc[-1]
    ema20 = df["EMA20"].iloc[-1]
    sma50 = df["SMA50"].iloc[-1]
    bb_upper = df["BB_upper"].iloc[-1]
    bb_lower = df["BB_lower"].iloc[-1]
    
    # Określ trend
    trend = "Bullish" if ema20 > sma50 else "Bearish"
    
    # Generuj sygnały tradingowe
    signal_type = "HOLD"
    entry_price = last_price
    stop_loss = None
    take_profit_1 = None
    take_profit_2 = None
    confidence = "LOW"
    
    # Logika dla LONG
    if trend == "Bullish" and rsi < 70 and macd > 0:
        signal_type = "LONG 🚀"
        entry_price = last_price
        stop_loss = max(bb_lower, last_price * 0.97)  # 3% poniżej lub Bollinger Lower
        take_profit_1 = last_price * 1.05  # 5% zysk
        take_profit_2 = min(bb_upper, last_price * 1.08)  # Bollinger Upper lub 8% zysk
        
        # Oblicz confidence
        confidence_score = 0
        if 30 < rsi < 60:
            confidence_score += 1
        if macd > 0:
            confidence_score += 1
        if ema20 > sma50:
            confidence_score += 1
        
        confidence = "HIGH" if confidence_score >= 3 else "MEDIUM" if confidence_score >= 2 else "LOW"
    
    # Logika dla SHORT
    elif trend == "Bearish" and rsi > 30 and macd < 0:
        signal_type = "SHORT 📉"
        entry_price = last_price
        stop_loss = min(bb_upper, last_price * 1.03)  # 3% powyżej lub Bollinger Upper
        take_profit_1 = last_price * 0.95  # 5% zysk
        take_profit_2 = max(bb_lower, last_price * 0.92)  # Bollinger Lower lub 8% zysk
        
        # Oblicz confidence
        confidence_score = 0
        if 40 < rsi < 70:
            confidence_score += 1
        if macd < 0:
            confidence_score += 1
        if ema20 < sma50:
            confidence_score += 1
            
        confidence = "HIGH" if confidence_score >= 3 else "MEDIUM" if confidence_score >= 2 else "LOW"

    # Podstawowa analiza (stary tekst)
    basic_analysis = (
        f"✅ **Analysis for {query.upper()}**\n"
        f"Price: {last_price:.2f} USD\n"
        f"RSI: {rsi:.2f}\n"
        f"MACD: {macd:.2f}\n"
        f"EMA20 vs SMA50 trend: {trend}\n"
        f"Suggestion: {trend} momentum\n\n"
    )
    
    # NOWY TEKST - Poziomy tradingowe
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

    # Połącz teksty
    analysis_text = basic_analysis + "=" * 40 + "\n" + trading_signal

    if ENABLE_AFFILIATE_FOOTER:
        analysis_text += f"{AFFILIATE_TEXT}"

    # Step 6: Send results
    await update.message.reply_photo(photo=img_buf, caption=analysis_text, parse_mode="Markdown")

# (Removed duplicate analysis and reply block that was outside async context)


# --------- Main ---------
def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("analyze", analyze))

    application.run_polling()


if __name__ == "__main__":
    main()
