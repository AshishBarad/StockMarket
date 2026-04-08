import sqlite3
import time
import os
import sys
import random
from datetime import datetime, date
from dotenv import load_dotenv

# Load env variables globally for separate process
load_dotenv()

# ── The worker runs from utils/ so we need parent on the path ──
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.model_predictor import init_db, get_ai_status, DB_PATH, get_sim_config

# ─── NSE 500 Universe – an expanded, real list of liquid NSE stocks ───────────
NSE_UNIVERSE = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "SBIN", "BHARTIARTL", "BAJFINANCE", "KOTAKBANK",
    "ASIANPAINT", "AXISBANK", "LTIM", "MARUTI", "TITAN",
    "SUNPHARMA", "WIPRO", "ULTRACEMCO", "M&M", "POWERGRID",
    "NESTLEIND", "ONGC", "NTPC", "COALINDIA", "BPCL",
    "TECHM", "HCLTECH", "TATAMOTORS", "TATASTEEL", "JSWSTEEL",
    "BAJAJ-AUTO", "DRREDDY", "CIPLA", "DIVISLAB", "SBILIFE",
    "HDFCLIFE", "EICHERMOT", "GRASIM", "ADANIENT", "ADANIPORTS",
    "ZOMATO", "NYKAA", "PAYTM", "IRCTC", "DMART",
    "PIDILITIND", "ABB", "SIEMENS", "HAVELLS", "VOLTAS",
]


def score_symbol(symbol):
    """
    Simulated AI scoring engine.
    In production, replace with:
      - FinBERT sentiment on today's news headlines
      - RSI/MACD momentum from Dhan OHLC API
      - Volume spike detection
      - F&O OI buildup signal
    Returns (action, confidence, base_price)
    """
    # Simulate momentum scoring (higher = more bullish signal)
    momentum_score = random.uniform(0, 100)

    if momentum_score >= 70:
        action = "BUY"
        confidence = int(momentum_score)
    elif momentum_score <= 30:
        action = "SELL"
        confidence = int(100 - momentum_score)
    else:
        return None  # Neutral — skip this stock

    base_price = random.randint(200, 4000)
    limit = round(base_price * (1.002 if action == "BUY" else 0.998), 2)
    target = round(base_price * (1.05 if action == "BUY" else 0.95), 2)
    tsl = round(base_price * (0.98 if action == "BUY" else 1.02), 2)

    return action, confidence, limit, target, tsl


def count_today_executions(c):
    c.execute(
        "SELECT COUNT(id) FROM signals WHERE status='EXECUTED' AND date(timestamp) = date('now')"
    )
    return c.fetchone()[0]


def agent_loop():
    init_db()
    print(f"[{datetime.now()}] ✅ Autonomous AI Trading Agent Initialized.")
    print(f"[{datetime.now()}] Universe: {len(NSE_UNIVERSE)} stocks available for scanning.")

    while True:
        try:
            if not get_ai_status():
                time.sleep(10)
                continue

            cfg = get_sim_config()
            max_picks = cfg.get("max_ai_stocks", 10)
            max_trades = cfg["max_trades_daily"]
            auto_execute = cfg["auto_execute"]
            trade_amount = cfg["trade_amount"]

            print(f"\n[{datetime.now()}] ── Sweep Start ──")
            print(f"  Scanning up to {max_picks} stocks | Auto-execute: {auto_execute} | Budget/trade: ₹{trade_amount:,.0f}")

            # Randomly sample from universe (in production: rank by real score)
            candidates = random.sample(NSE_UNIVERSE, min(len(NSE_UNIVERSE), max_picks * 2))

            scored = []
            for sym in candidates:
                result = score_symbol(sym)
                if result:
                    scored.append((sym, result))

            # Sort by confidence descending, take top max_picks
            scored.sort(key=lambda x: x[1][1], reverse=True)
            top_picks = scored[:max_picks]

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()

            signals_fired = 0
            for symbol, (action, conf, limit, target_p, tsl) in top_picks:
                # Skip if we already have an active signal for this stock today
                c.execute(
                    "SELECT id FROM signals WHERE symbol=? AND status IN ('PENDING','EXECUTED') AND date(timestamp)=date('now')",
                    (symbol,)
                )
                if c.fetchone():
                    continue

                if auto_execute:
                    executed_today = count_today_executions(c)
                    if executed_today < max_trades:
                        qty = max(1, int(trade_amount / limit))
                        print(f"  ⚡ AUTO-EXECUTE: {action} {symbol} x{qty} @ ₹{limit}")
                        c.execute(
                            """INSERT INTO signals (symbol, action, confidence, limit_price, target_price, trailing_sl, status)
                               VALUES (?, ?, ?, ?, ?, ?, 'EXECUTED')""",
                            (symbol, action, conf, limit, target_p, tsl)
                        )
                        signals_fired += 1
                        continue

                # Push to Pending Inbox for user review
                c.execute(
                    """INSERT INTO signals (symbol, action, confidence, limit_price, target_price, trailing_sl, status)
                       VALUES (?, ?, ?, ?, ?, ?, 'PENDING')""",
                    (symbol, action, conf, limit, target_p, tsl)
                )
                print(f"  📥 INBOX: {action} {symbol} | {conf}% conf | Limit ₹{limit}")
                signals_fired += 1

            # ── Trailing Stop-Loss monitor for existing executed trades ──
            c.execute(
                "SELECT id, symbol, trailing_sl, action, target_price FROM signals WHERE status='EXECUTED'"
            )
            for t_id, t_symbol, t_sl, t_action, t_target in c.fetchall():
                if random.random() > 0.7:
                    new_tsl = round(t_sl * (1.01 if t_action == "BUY" else 0.99), 2)
                    c.execute(
                        """INSERT INTO signals (symbol, action, confidence, limit_price, target_price, trailing_sl, status)
                           VALUES (?, 'MODIFY SL', 99, 0.0, ?, ?, 'PENDING')""",
                        (t_symbol, t_target, new_tsl)
                    )
                    c.execute("UPDATE signals SET status='MONITORED' WHERE id=?", (t_id,))
                    print(f"  🛡️  TSL adjusted: {t_symbol} → ₹{new_tsl}")

            conn.commit()
            conn.close()

            print(f"[{datetime.now()}] ── Sweep Done: {signals_fired} signal(s) fired. Sleeping 15 min ──\n")
            time.sleep(15 * 60)

        except KeyboardInterrupt:
            print("Agent stopped by user.")
            break
        except Exception as e:
            print(f"[{datetime.now()}] ❌ WORKER ERROR: {e}")
            time.sleep(30)


if __name__ == "__main__":
    agent_loop()
