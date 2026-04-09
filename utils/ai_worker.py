import sqlite3
import time
import os
import sys
import random
from datetime import datetime, date, time as dtime

from dotenv import load_dotenv
load_dotenv()

# ── Path setup so we can import utils from the project root ───────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)  # Ensure relative paths (like db/) resolve correctly

from utils.model_predictor import init_db, get_ai_status, DB_PATH, get_sim_config

# ─── NSE Universe – liquid NSE stocks ────────────────────────────────────────
NSE_UNIVERSE = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "SBIN", "BHARTIARTL", "BAJFINANCE", "KOTAKBANK",
    "ASIANPAINT", "AXISBANK", "LTIM", "MARUTI", "TITAN",
    "SUNPHARMA", "WIPRO", "ULTRACEMCO", "M&M", "POWERGRID",
    "NESTLEIND", "ONGC", "NTPC", "COALINDIA", "BPCL",
    "TECHM", "HCLTECH", "TATAMOTORS", "TATASTEEL", "JSWSTEEL",
    "BAJAJ-AUTO", "DRREDDY", "CIPLA", "DIVISLAB", "SBILIFE",
    "HDFCLIFE", "EICHERMOT", "GRASIM", "ADANIENT", "ADANIPORTS",
    "ZOMATO", "NYKAA", "IRCTC", "DMART", "PIDILITIND",
    "ABB", "SIEMENS", "HAVELLS", "VOLTAS", "TRENT",
]

# ─── Market Hours (IST) ───────────────────────────────────────────────────────
MARKET_OPEN  = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)

def is_market_open():
    """Returns True only on weekdays within NSE trading hours."""
    now = datetime.now()
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def fetch_real_prices(symbols):
    """
    Fetch OHLC data for all symbols in one batch API call via Dhan.
    Returns dict: {symbol: (ltp, prev_close)}
    """
    try:
        from dhanhq import dhanhq
        from utils.data_loader import load_dhan_scrip_master
        import pandas as pd

        client_id    = os.environ.get('DHAN_CLIENT_ID')
        access_token = os.environ.get('DHAN_ACCESS_TOKEN')
        if not client_id or not access_token:
            return {}

        dhan = dhanhq(client_id, access_token)
        df_master = load_dhan_scrip_master()

        sid_to_sym, sec_ids = {}, []
        for sym in symbols:
            match = df_master[df_master['SEM_TRADING_SYMBOL'] == sym]
            if not match.empty:
                sid = str(int(match.iloc[0]['SEM_SMST_SECURITY_ID']))
                sec_ids.append(sid)
                sid_to_sym[sid] = sym

        if not sec_ids:
            return {}

        res = dhan.ohlc_data({'NSE_EQ': sec_ids})
        result = {}
        if res and res.get('status') == 'success':
            data = res.get('data', {}).get('NSE_EQ', {})
            for sid, vals in data.items():
                sym = sid_to_sym.get(str(sid))
                if sym:
                    ltp  = float(vals.get('last_price', vals.get('close', 0.0)))
                    prev = float(vals.get('prev_close', ltp))
                    result[sym] = (ltp, prev)
        return result
    except Exception as e:
        print(f"  ⚠️  Price fetch error: {e}")
        return {}


def score_symbol(symbol, ltp, prev_close):
    """
    Score a symbol using real price momentum vs previous close.
    Returns (action, confidence, limit, target, tsl) or None if signal is weak.
    """
    if prev_close <= 0 or ltp <= 0:
        return None

    change_pct = (ltp - prev_close) / prev_close * 100

    # Bullish momentum: price up > 0.5% from yesterday
    if change_pct >= 0.5:
        action     = "BUY"
        confidence = min(95, int(60 + change_pct * 5))
        limit      = round(ltp * 1.001, 2)          # 0.1% above LTP
        target     = round(ltp * 1.03, 2)           # 3% target
        tsl        = round(ltp * 0.985, 2)          # 1.5% trailing stop-loss
    # Bearish momentum: price down > 0.5% from yesterday
    elif change_pct <= -0.5:
        action     = "SELL"
        confidence = min(95, int(60 + abs(change_pct) * 5))
        limit      = round(ltp * 0.999, 2)
        target     = round(ltp * 0.97, 2)
        tsl        = round(ltp * 1.015, 2)
    else:
        return None  # Neutral — no signal

    return action, confidence, limit, target, tsl


def count_today_executions(c):
    c.execute(
        "SELECT COUNT(id) FROM signals WHERE status='EXECUTED' AND date(timestamp) = date('now')"
    )
    return c.fetchone()[0]


def agent_loop():
    init_db()
    print(f"[{datetime.now()}] ✅ AI Trading Agent Initialized.")
    print(f"  Universe: {len(NSE_UNIVERSE)} stocks | Market hours: {MARKET_OPEN}–{MARKET_CLOSE} IST (weekdays only)")

    while True:
        try:
            if not get_ai_status():
                time.sleep(30)
                continue

            # ── Gate: only run during market hours ───────────────────────────
            if not is_market_open():
                now = datetime.now()
                print(f"[{now.strftime('%H:%M')}] Market closed. Next check in 5 minutes.")
                time.sleep(5 * 60)
                continue

            cfg           = get_sim_config()
            max_picks     = cfg.get("max_ai_stocks", 10)
            max_trades    = cfg["max_trades_daily"]
            auto_execute  = cfg["auto_execute"]
            trade_amount  = cfg["trade_amount"]

            print(f"\n[{datetime.now().strftime('%H:%M')}] ── Sweep Start ──")
            print(f"  Config: max_picks={max_picks} | max_trades={max_trades} | auto={auto_execute}")

            # ── Fetch real prices for a random sample of the universe ─────────
            candidates = random.sample(NSE_UNIVERSE, min(len(NSE_UNIVERSE), max_picks * 3))
            prices = fetch_real_prices(candidates)

            if not prices:
                print("  ⚠️  Could not fetch prices. Retrying in 5 min.")
                time.sleep(5 * 60)
                continue

            # Score each symbol using real momentum data
            scored = []
            for sym, (ltp, prev) in prices.items():
                result = score_symbol(sym, ltp, prev)
                if result:
                    scored.append((sym, ltp, result))

            # Sort by confidence descending, take top N
            scored.sort(key=lambda x: x[2][1], reverse=True)
            top_picks = scored[:max_picks]

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            signals_fired = 0

            for symbol, ltp, (action, conf, limit, target_p, tsl) in top_picks:
                # Skip if active signal for this stock already exists today
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
                        print(f"  ⚡ AUTO-EXECUTE: {action} {symbol} x{qty} @ ₹{limit} (LTP ₹{ltp})")
                        c.execute(
                            """INSERT INTO signals
                               (symbol, action, confidence, limit_price, target_price, trailing_sl, status)
                               VALUES (?, ?, ?, ?, ?, ?, 'EXECUTED')""",
                            (symbol, action, conf, limit, target_p, tsl)
                        )
                        signals_fired += 1
                        continue

                # Push to Pending Inbox
                c.execute(
                    """INSERT INTO signals
                       (symbol, action, confidence, limit_price, target_price, trailing_sl, status)
                       VALUES (?, ?, ?, ?, ?, ?, 'PENDING')""",
                    (symbol, action, conf, limit, target_p, tsl)
                )
                print(f"  📥 INBOX: {action} {symbol} | {conf}% | LTP ₹{ltp} | Limit ₹{limit}")
                signals_fired += 1

            # ── Trailing Stop-Loss monitor ────────────────────────────────────
            c.execute(
                "SELECT id, symbol, trailing_sl, action, target_price FROM signals WHERE status='EXECUTED'"
            )
            for t_id, t_symbol, t_sl, t_action, t_target in c.fetchall():
                live = prices.get(t_symbol)
                if not live:
                    continue
                ltp_now = live[0]
                # Tighten TSL if price has moved favourably by > 1%
                if t_action == "BUY" and ltp_now > t_sl * 1.01:
                    new_tsl = round(ltp_now * 0.985, 2)
                    c.execute(
                        """INSERT INTO signals (symbol, action, confidence, limit_price, target_price, trailing_sl, status)
                           VALUES (?, 'MODIFY SL', 99, 0.0, ?, ?, 'PENDING')""",
                        (t_symbol, t_target, new_tsl)
                    )
                    c.execute("UPDATE signals SET status='MONITORED' WHERE id=?", (t_id,))
                    print(f"  🛡️  TSL tightened: {t_symbol} → ₹{new_tsl} (LTP ₹{ltp_now})")
                elif t_action == "SELL" and ltp_now < t_sl * 0.99:
                    new_tsl = round(ltp_now * 1.015, 2)
                    c.execute(
                        """INSERT INTO signals (symbol, action, confidence, limit_price, target_price, trailing_sl, status)
                           VALUES (?, 'MODIFY SL', 99, 0.0, ?, ?, 'PENDING')""",
                        (t_symbol, t_target, new_tsl)
                    )
                    c.execute("UPDATE signals SET status='MONITORED' WHERE id=?", (t_id,))
                    print(f"  🛡️  TSL tightened: {t_symbol} → ₹{new_tsl} (LTP ₹{ltp_now})")

            conn.commit()
            conn.close()

            print(f"[{datetime.now().strftime('%H:%M')}] ── Sweep done: {signals_fired} new signal(s). Sleeping 15 min ──\n")
            time.sleep(15 * 60)

        except KeyboardInterrupt:
            print("Agent stopped.")
            break
        except Exception as e:
            print(f"[{datetime.now()}] ❌ WORKER ERROR: {e}")
            time.sleep(60)


if __name__ == "__main__":
    agent_loop()
