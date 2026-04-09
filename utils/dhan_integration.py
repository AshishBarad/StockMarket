import os
from dhanhq import dhanhq
import streamlit as st
import sqlite3
from utils.model_predictor import get_sim_config, DB_PATH

def get_sandbox_holdings():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""SELECT symbol, 
                     SUM(CASE WHEN action='BUY' THEN qty ELSE -qty END) as total_qty, 
                     SUM(CASE WHEN action='BUY' THEN qty*avg_price ELSE -qty*avg_price END)/SUM(CASE WHEN action='BUY' THEN qty ELSE 0.0001 END) as avg_cost 
                     FROM paper_trades GROUP BY symbol HAVING total_qty > 0""")
        rows = c.fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    
    holdings = []
    for r in rows:
        sym, qty, avg_p = r
        holdings.append({
            'tradingSymbol': sym,
            'totalQty': qty,
            'avgCostPrice': avg_p
        })
    return {"status": "success", "data": holdings}

def execute_sandbox_order(symbol, action, qty, price):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Mocking a market execution if limit price isn't explicitly 0
    c.execute("INSERT INTO paper_trades (symbol, action, qty, avg_price) VALUES (?, ?, ?, ?)", (symbol, action, qty, price))
    conn.commit()
    conn.close()
    
def get_sandbox_funds():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    baseline = 500000.0
    try:
        c.execute("""SELECT SUM(CASE WHEN action='BUY' THEN qty*avg_price ELSE -qty*avg_price END) FROM paper_trades""")
        spent = c.fetchone()[0]
        if not spent: spent = 0.0
    except Exception:
        spent = 0.0
    conn.close()
    return max(0.0, baseline - float(spent))

def get_available_funds():
    if get_sim_config()['sandbox_mode']:
        return get_sandbox_funds()
    
    dhan = get_dhan_client()
    if not dhan: return 0.0
    try:
        limits = dhan.get_fund_limits()
        if limits.get("status") == "success":
            data = limits.get("data", {})
            return float(data.get("availabelMargin", data.get("coreMarginAvailable", data.get("availableMargin", 0.0))))
        return 0.0
    except Exception:
        return 0.0

def get_dhan_client():
    client_id = None
    if 'dhan_client_id' in st.session_state and st.session_state.dhan_client_id:
        client_id = st.session_state.dhan_client_id
    else:
        client_id = os.environ.get('DHAN_CLIENT_ID')
    
    access_token = None
    if 'dhan_token' in st.session_state and st.session_state.dhan_token:
        access_token = st.session_state.dhan_token
    else:
        access_token = os.environ.get('DHAN_ACCESS_TOKEN')
    
    missing = []
    if not client_id:
        missing.append("DHAN_CLIENT_ID")
    if not access_token:
        missing.append("DHAN_ACCESS_TOKEN")
        
    if missing:
        st.error(f"Dhan credentials not found! Missing: {', '.join(missing)} (Please update them in the Settings Sidebar)")
        return None
        
    try:
        dhan = dhanhq(client_id, access_token)
        return dhan
    except Exception as e:
        st.error(f"Failed to initialize Dhan API client: {e}")
        return None
        
def get_holdings():
    if get_sim_config()['sandbox_mode']:
        return get_sandbox_holdings()
        
    dhan = get_dhan_client()
    if not dhan:
        return None
    try:
        # get_holdings relies on DhanHQ SDK
        holdings = dhan.get_holdings()
        return holdings
    except Exception as e:
        st.error(f"Error fetching holdings: {e}")
        return None

def get_portfolio_summary():
    holdings_resp = get_holdings()
    
    if not holdings_resp:
        return 0.0, 0.0, 0.0, 0.0
        
    if holdings_resp.get("status") != "success":
        # Dhan returns an explicit error object when holdings are just empty
        # e.g., {'error_code': 'DH-1111', 'error_message': 'No holdings available'}
        error_msg = holdings_resp.get("remarks", "")
        if not error_msg:
            # Sometmes it is inside the stringified object if the wrapper broke it
            error_msg = str(holdings_resp)
        if "No holdings available" in str(holdings_resp) or "DH-1111" in str(holdings_resp):
            return 0.0, 0.0, 0.0, 0.0
        st.error(f"Dhan API Error: {error_msg}")
        return 0.0, 0.0, 0.0, 0.0
        
    holdings = holdings_resp.get("data", [])
    total_invested = 0.0
    total_current = 0.0
    
    for h in holdings:
        total_qty = float(h.get('totalQty', h.get('heldQuantity', 0)))
        avg_price = float(h.get('avgCostPrice', h.get('costPrice', 0)))
        cur_price = float(h.get('lastTradedPrice', h.get('closePrice', avg_price)))
        
        total_invested += total_qty * avg_price
        total_current += total_qty * cur_price
        
    pnl = total_current - total_invested
    pnl_pct = (pnl / total_invested * 100) if total_invested > 0 else 0.0
    
    return total_invested, total_current, pnl, pnl_pct

def get_day_pnl():
    """
    Returns (day_pnl, day_pnl_pct) for today's trading activity.
    Sandbox: computed from paper_trades where date = today.
    Live   : computed from Dhan positions API (unrealised + realised).
    Resets automatically at midnight since it only looks at today's date.
    """
    try:
        sim_conf = get_sim_config()
        if sim_conf['sandbox_mode']:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            # Sold value - bought value for today's trades
            c.execute("""
                SELECT
                    SUM(CASE WHEN action='SELL' THEN qty * avg_price ELSE 0 END) as sell_val,
                    SUM(CASE WHEN action='BUY'  THEN qty * avg_price ELSE 0 END) as buy_val
                FROM paper_trades
                WHERE date(timestamp) = date('now')
            """)
            row = c.fetchone()
            conn.close()
            sell_val = float(row[0] or 0.0)
            buy_val  = float(row[1] or 0.0)
            day_pnl  = sell_val - buy_val
            day_pnl_pct = (day_pnl / buy_val * 100) if buy_val > 0 else 0.0
            return day_pnl, day_pnl_pct

        # Live mode: use Dhan positions
        dhan = get_dhan_client()
        if not dhan:
            return 0.0, 0.0
        resp = dhan.get_positions()
        if not resp or resp.get('status') != 'success':
            return 0.0, 0.0
        positions = resp.get('data', [])
        total_realised    = sum(float(p.get('realizedProfit', 0)) for p in positions)
        total_unrealised  = sum(float(p.get('unrealizedProfit', p.get('unrealisedProfit', 0))) for p in positions)
        day_pnl = total_realised + total_unrealised
        # Approx % based on net buy value
        net_buy = sum(
            float(p.get('buyAvg', 0)) * float(p.get('buyQty', 0))
            for p in positions
        )
        day_pnl_pct = (day_pnl / net_buy * 100) if net_buy > 0 else 0.0
        return day_pnl, day_pnl_pct
    except Exception:
        return 0.0, 0.0

def get_holding_for_symbol(symbol):
    holdings_resp = get_holdings()
    if not holdings_resp or holdings_resp.get("status") != "success":
        return None
        
    holdings = holdings_resp.get("data", [])
    for h in holdings:
        if h.get('tradingSymbol') == symbol:
            return h
    return None

def place_order_mock(symbol, transaction_type, quantity, order_type, product_type, price=0):
    sim_conf = get_sim_config()
    
    # Need live price if submitting market simulator
    if price == 0 and sim_conf['sandbox_mode']:
        l_price, _, _err = get_dhan_live_price(symbol)
        price = l_price

    if sim_conf['sandbox_mode']:
        execute_sandbox_order(symbol, transaction_type, quantity, price)
        # Using st._is_running_with_streamlit prevents background worker crash
        try: st.success(f"🧪 [SANDBOX] {transaction_type} executed for {quantity}x {symbol} at ₹{price}")
        except: pass
        return {"status": "success", "message": f"Successfully simulated order for {symbol}", "data": {"order_id": "MOCK12345"}}
        
    dhan = get_dhan_client()
    if not dhan:
        return None
        
    try:
        # Assuming actual live placing code would go here
        try: st.success(f"🚀 [LIVE EXECUTION] {transaction_type} executed for {quantity}x {symbol} at ₹{price}")
        except: pass
        return {"status": "success", "message": f"Successfully placed order for {symbol}", "data": {"order_id": "LIVE12345"}}
    except Exception as e:
        try: st.error(f"Failed to place order: {e}")
        except: pass
        return None

def get_batch_quotes(symbols):
    """
    Fetch close prices for multiple NSE symbols in ONE API call using ohlc_data.
    Returns dict: {symbol: (current_price, prev_close)}
    Falls back to empty dict on error (caller uses cached values).
    """
    dhan = get_dhan_client()
    if not dhan or not symbols:
        return {}
    try:
        from utils.data_loader import load_dhan_scrip_master
        import pandas as pd
        from datetime import datetime
        import time

        df_master = load_dhan_scrip_master()
        # Build sec_id -> symbol map
        sid_to_sym = {}
        sec_ids = []
        for sym in symbols:
            clean = sym.replace('.NS', '')
            match = df_master[df_master['SEM_TRADING_SYMBOL'] == clean]
            if not match.empty:
                sid = str(int(match.iloc[0]['SEM_SMST_SECURITY_ID']))
                sec_ids.append(sid)
                sid_to_sym[sid] = clean

        if not sec_ids:
            return {}

        # ohlc_data fetches open/high/low/close for multiple securities in one call
        res = dhan.ohlc_data({'NSE_EQ': sec_ids})
        result = {}
        if res and res.get('status') == 'success':
            data = res.get('data', {}).get('NSE_EQ', {})
            for sid, vals in data.items():
                sym = sid_to_sym.get(str(sid))
                if sym:
                    ltp = float(vals.get('last_price', vals.get('close', 0.0)))
                    prev = float(vals.get('prev_close', ltp))
                    result[sym] = (ltp, prev)
        return result
    except Exception:
        return {}

def get_dhan_indices():
    dhan = get_dhan_client()
    nifty, sensex = 0.0, 0.0
    nifty_chg, nifty_pct, sensex_chg, sensex_pct = 0.0, 0.0, 0.0, 0.0
    if not dhan: return nifty, sensex, nifty_chg, nifty_pct, sensex_chg, sensex_pct, "Dhan API Not Connected"
    
    import pandas as pd
    from datetime import datetime
    import time
    try:
        now_dt = datetime.today().strftime('%Y-%m-%d')
        past_dt = (datetime.today() - pd.Timedelta(days=10)).strftime('%Y-%m-%d')
        
        # NIFTY 50 -> SEC_ID 13, IDX_I segment, INDEX instrument
        res = dhan.historical_daily_data(
            security_id='13', exchange_segment='IDX_I',
            instrument_type='INDEX', from_date=past_dt, to_date=now_dt
        )
        if res and res.get('status') == 'success':
            data = res.get('data', {})
            closes = data.get('close', [])
            if len(closes) >= 2:
                nifty = float(closes[-1])
                prev = float(closes[-2])
                nifty_chg = round(nifty - prev, 2)
                nifty_pct = round((nifty_chg / prev) * 100, 2)
            elif len(closes) == 1:
                nifty = float(closes[-1])
            
        # RATE LIMITING: 1 request per second for Data APIs
        time.sleep(1.05)
            
        # SENSEX -> SEC_ID 51, IDX_I segment, INDEX instrument
        res = dhan.historical_daily_data(
            security_id='51', exchange_segment='IDX_I',
            instrument_type='INDEX', from_date=past_dt, to_date=now_dt
        )
        if res and res.get('status') == 'success':
            data = res.get('data', {})
            closes = data.get('close', [])
            if len(closes) >= 2:
                sensex = float(closes[-1])
                prev = float(closes[-2])
                sensex_chg = round(sensex - prev, 2)
                sensex_pct = round((sensex_chg / prev) * 100, 2)
            elif len(closes) == 1:
                sensex = float(closes[-1])
            
        return round(nifty, 2), round(sensex, 2), nifty_chg, nifty_pct, sensex_chg, sensex_pct, None
    except Exception as e:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, str(e)

def get_dhan_live_price(symbol):
    """
    Returns (current_price, prev_close, error).
    During market hours (9:15-15:30 IST): fetches latest intraday minute bar.
    Outside market hours: returns last two EOD closes.
    """
    dhan = get_dhan_client()
    if not dhan: return 0.0, 0.0, "Dhan API Not Connected"

    try:
        import pandas as pd
        from datetime import datetime, time as dtime
        import time
        from utils.data_loader import load_dhan_scrip_master

        df_master = load_dhan_scrip_master()
        clean_symbol = symbol.replace('.NS', '')
        match = df_master[df_master['SEM_TRADING_SYMBOL'] == clean_symbol]
        if match.empty: return 0.0, 0.0, "Symbol not found in Scrip Master"

        sec_id   = str(int(match.iloc[0]['SEM_SMST_SECURITY_ID']))
        now_dt   = datetime.today().strftime('%Y-%m-%d')
        past_dt  = (datetime.today() - pd.Timedelta(days=10)).strftime('%Y-%m-%d')

        # Check if inside NSE market hours (9:15 AM - 3:30 PM IST weekdays)
        now_t = datetime.now().time()
        is_market_hours = dtime(9, 15) <= now_t <= dtime(15, 30)

        time.sleep(1.05)  # rate limit

        # Always fetch EOD to get prev close for day-change calc
        res = dhan.historical_daily_data(
            security_id=sec_id, exchange_segment='NSE_EQ',
            instrument_type='EQUITY', from_date=past_dt, to_date=now_dt
        )
        eod_closes = []
        if res and res.get('status') == 'success':
            eod_closes = res.get('data', {}).get('close', [])

        prev_close = float(eod_closes[-1]) if eod_closes else 0.0

        if is_market_hours:
            # Try intraday for a live tick price
            time.sleep(1.05)
            try:
                intra = dhan.intraday_minute_data(
                    security_id=sec_id,
                    exchange_segment='NSE_EQ',
                    instrument_type='EQUITY'
                )
                if intra and intra.get('status') == 'success':
                    intra_closes = intra.get('data', {}).get('close', [])
                    if intra_closes:
                        return float(intra_closes[-1]), prev_close, None
            except Exception:
                pass  # fall through to EOD

        # Outside hours or intraday failed: use last two EOD closes
        if len(eod_closes) >= 2:
            return float(eod_closes[-1]), float(eod_closes[-2]), None
        elif len(eod_closes) == 1:
            return float(eod_closes[-1]), float(eod_closes[-1]), None
        return 0.0, 0.0, "No price data available"
    except Exception as e:
        return 0.0, 0.0, str(e)

def load_dhan_chart_data(symbol):
    dhan = get_dhan_client()
    if not dhan: raise Exception("Dhan API Not Connected")
    
    import pandas as pd
    from datetime import datetime
    from utils.data_loader import load_dhan_scrip_master
    
    df_master = load_dhan_scrip_master()
    clean_symbol = symbol.replace('.NS', '')
    match = df_master[df_master['SEM_TRADING_SYMBOL'] == clean_symbol]
    if match.empty: raise Exception("Symbol not found in Scrip Master")
    
    sec_id = str(int(match.iloc[0]['SEM_SMST_SECURITY_ID']))
    
    now_dt = datetime.today().strftime('%Y-%m-%d')
    past_dt = (datetime.today() - pd.Timedelta(days=365)).strftime('%Y-%m-%d')
    
    res = dhan.historical_daily_data(
        security_id=sec_id, exchange_segment='NSE_EQ',
        instrument_type='EQUITY', from_date=past_dt, to_date=now_dt
    )
    if res and res.get('status') == 'success':
        raw = res.get('data', {})
        df = pd.DataFrame(raw)
        # Convert unix timestamps to datetime index
        if 'timestamp' in df.columns:
            df.index = pd.to_datetime(df['timestamp'], unit='s')
        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)
        return df
    else:
        raise Exception(f"API Failure: {res.get('remarks', 'Empty response')}")
