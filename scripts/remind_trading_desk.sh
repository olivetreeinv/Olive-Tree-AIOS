#!/bin/sh
# remind_trading_desk.sh — one-time Monday reminder to kick off the Quant Trading Desk.
# Fired by ~/Library/LaunchAgents/com.olivetree.trading-desk-reminder.plist.
# After firing, it unloads its own launchd job so it never repeats.

REPO="/Users/olivetree/Documents/Olive AIOS"
LOG="$REPO/logs/reminders.log"
PLIST="$HOME/Library/LaunchAgents/com.olivetree.trading-desk-reminder.plist"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M")

TITLE="Trading Desk — kick off today"
MSG="Stocks+crypto, paper-only first, hybrid LLM+quant on Opus 4.8. Day 1: scaffold module, Alpaca paper keys, backtest harness (SPY vs S&P), stub the agent loop. You still owe: Alpaca login choice + a risk ceiling (max % loss per position/day)."

sh "$REPO/scripts/notify.sh" "$TITLE" "$MSG"
echo "[$TIMESTAMP] Fired trading-desk reminder." >> "$LOG"

# Make it one-time: unload + remove the plist so it won't fire again.
launchctl unload "$PLIST" 2>/dev/null
rm -f "$PLIST"
echo "[$TIMESTAMP] Unloaded and removed one-time job." >> "$LOG"
