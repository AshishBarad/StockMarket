import streamlit as st
import plotly.graph_objs as go
import os
from dotenv import load_dotenv

from utils.data_loader import load_stock_data, load_dhan_scrip_master
from utils.dhan_integration import get_portfolio_summary, get_holding_for_symbol, place_order_mock, get_available_funds, get_holdings
from utils.model_predictor import (
    get_ai_status, toggle_ai_status, get_pending_signals, mark_signal_done,
    get_sim_config, update_sim_config, get_orders, update_order_status, add_order
)

# Load environment variables
load_dotenv()

st.set_page_config(page_title="Indian Stock Market Trading", layout="wide")

# --- Initialize Session State ---
if 'watchlist' not in st.session_state:
    st.session_state.watchlist = []
if 'dhan_token' not in st.session_state:
    st.session_state.dhan_token = os.environ.get('DHAN_ACCESS_TOKEN', '')
if 'dhan_client_id' not in st.session_state:
    st.session_state.dhan_client_id = os.environ.get('DHAN_CLIENT_ID', '')

with st.sidebar:
    st.header("⚙️ Settings")
    st.write("Your Dhan access token expires every 24 hours. Update your credentials here to continue trading.")
    new_client_id = st.text_input("Dhan Client ID", value=st.session_state.dhan_client_id)
    new_token = st.text_input("Dhan Access Token", value=st.session_state.dhan_token, type="password")
    if st.button("Update Credentials", use_container_width=True):
        st.session_state.dhan_client_id = new_client_id
        st.session_state.dhan_token = new_token
        os.environ['DHAN_CLIENT_ID'] = new_client_id
        os.environ['DHAN_ACCESS_TOKEN'] = new_token
        # Persist securely so background autonomous worker can access it
        with open(".env", "w") as f:
            f.write(f"DHAN_CLIENT_ID={new_client_id}\n")
            f.write(f"DHAN_ACCESS_TOKEN={new_token}\n")
        st.success("Credentials updated successfully!")
        st.rerun()

    st.divider()
    st.subheader("Data Refresh Settings")
    st.session_state.refresh_indices = st.slider("Indices Refresh (seconds)", min_value=1, max_value=120, value=st.session_state.get('refresh_indices', 2))
    st.session_state.refresh_chart = st.slider("Live Chart Refresh (seconds)", min_value=1, max_value=120, value=st.session_state.get('refresh_chart', 2))
    st.session_state.refresh_watchlist = st.slider("Watchlist Prices Refresh (seconds)", min_value=1, max_value=120, value=st.session_state.get('refresh_watchlist', 2))
    
    st.divider()
    st.subheader("🤖 Autonomous Agent")
    current_ai_status = get_ai_status()
    new_ai_status = st.toggle("Enable 24/7 Deep Learning Trading Agent", value=current_ai_status)
    if new_ai_status != current_ai_status:
        toggle_ai_status(new_ai_status)
        st.success(f"AI Agent {'Started' if new_ai_status else 'Stopped'}!")
        st.rerun()
        
    st.divider()
    st.subheader("🧪 Sandbox & Auto-Execution")
    c_cfg = get_sim_config()
    new_sand = st.toggle("Enable Paper-Trading Sandbox", value=c_cfg['sandbox_mode'], help="Routes all trades and portfolios to local simulated tables. No real money used.")
    new_auto = st.toggle("Enable AI Auto-Execution", value=c_cfg['auto_execute'], help="Allows AI to bypass the Review inbox and directly place Orders.")
    new_max = st.number_input("Max Daily AI Trades", min_value=1, max_value=100, value=c_cfg['max_trades_daily'])
    new_amt = st.number_input("Trade Size (₹ Amount)", min_value=100.0, value=c_cfg['trade_amount'], step=100.0)
    new_max_stocks = st.number_input("Max AI Stock Picks", min_value=1, max_value=50, value=c_cfg.get('max_ai_stocks', 10), help="How many stocks AI will scan and rank per cycle")
    
    if st.button("Save Automation Rules", use_container_width=True):
        update_sim_config(new_sand, new_auto, new_max, new_amt, new_max_stocks)
        st.success("Simulation Rules Updated!")
        st.rerun()

# --- Custom Styling (Kite Theme) ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
.block-container {
    padding-top: 1rem;
    padding-bottom: 0rem;
}
.metric-row { display: flex; justify-content: space-between; margin-bottom: 20px;}
.metric-card { 
    background-color: #1e1e1e; 
    padding: 20px; 
    border-radius: 4px; 
    flex: 1; 
    margin: 0 10px; 
    text-align: left; 
    border: none;
    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
}
.metric-value { font-size: 28px; font-weight: 500; margin-top: 5px; }
.metric-label { font-size: 13px; color: #9B9B9B; text-transform: uppercase; letter-spacing: 0.5px;}
.green { color: #4caf50 !important; }
.red { color: #ff5722 !important; }
.watchlist-row {
    border-bottom: 1px solid #2b2b2b;
    padding: 10px 0;
}
</style>
""", unsafe_allow_html=True)
import time
from utils.dhan_integration import get_dhan_indices, get_dhan_live_price, load_dhan_chart_data

def get_cached_chart(symbol):
    ttl = st.session_state.get('refresh_chart', 2)
    if 'cache_chart' not in st.session_state: st.session_state.cache_chart = {}
    
    cache = st.session_state.cache_chart.get(symbol)
    if not cache or time.time() - cache['time'] > ttl:
        data = load_dhan_chart_data(symbol)
        st.session_state.cache_chart[symbol] = {'time': time.time(), 'data': data}
        return data
    return cache['data']

def get_cached_live_price(symbol):
    ttl = st.session_state.get('refresh_watchlist', 2)
    if 'cache_price' not in st.session_state: st.session_state.cache_price = {}
    
    cache = st.session_state.cache_price.get(symbol)
    if not cache or time.time() - cache['time'] > ttl or len(cache['data']) != 3:
        data = get_dhan_live_price(symbol)  # returns (cur, prev, err)
        st.session_state.cache_price[symbol] = {'time': time.time(), 'data': data}
        return data
    return cache['data']

# --- Top Header: Nifty / Sensex ---
def get_indices():
    ttl = st.session_state.get('refresh_indices', 2)
    cached = st.session_state.get('cache_indices')
    # Invalidate if missing, expired, OR wrong shape (old 3-tuple vs new 7-tuple)
    if (not cached
            or time.time() - cached['time'] > ttl
            or len(cached['data']) != 7):
        data = get_dhan_indices()
        st.session_state.cache_indices = {'time': time.time(), 'data': data}
        return data
    return cached['data']

nifty_val, sensex_val, nifty_chg, nifty_pct, sensex_chg, sensex_pct, idx_err = get_indices()

# Count pending AI signals for notification badge
pending_signals = get_pending_signals()
pending_ai_orders = get_orders(source='AI', status='PENDING_APPROVAL')
total_pending = len(pending_signals) + len(pending_ai_orders)
notif_badge = f" 🔔 ({total_pending}" + " new)" if total_pending > 0 else ""

# --- Page Title with Live Indices ---
col_title, col_nifty, col_sensex = st.columns([3, 1, 1])
with col_title:
    st.title(f"📈 Stock Market Dashboard{notif_badge}")

def _idx_card(label, val, chg, pct, base_color):
    """Render a single index card with change badge."""
    if val == 0.0:
        return f"""
        <div style='padding:16px;background:#1e1e1e;border-radius:4px;margin-top:14px'>
          <div style='font-size:11px;color:#9B9B9B;text-transform:uppercase'>{label}</div>
          <div style='font-size:24px;color:#ff5722'>⚠ Error</div>
        </div>"""
    sign = "+" if chg >= 0 else ""
    chg_color = "#4caf50" if chg >= 0 else "#ff5722"
    arrow = "▲" if chg >= 0 else "▼"
    return f"""
    <div style='padding:16px;background:#1e1e1e;border-radius:4px;margin-top:14px'>
      <div style='font-size:11px;color:#9B9B9B;text-transform:uppercase'>{label}</div>
      <div style='font-size:24px;font-weight:500;color:{base_color}'>{val:,.2f}</div>
      <div style='font-size:13px;color:{chg_color};margin-top:4px'>
        {arrow} {sign}{chg:,.2f} ({sign}{pct:.2f}%)
      </div>
    </div>"""

with col_nifty:
    st.markdown(_idx_card("NIFTY 50", nifty_val, nifty_chg, nifty_pct, "#4caf50"), unsafe_allow_html=True)
with col_sensex:
    st.markdown(_idx_card("SENSEX", sensex_val, sensex_chg, sensex_pct, "#4184f3"), unsafe_allow_html=True)
st.divider()

# --- Portfolio Summary & Margin ---
margin_val = get_available_funds()
inv_val, cur_val, pnl, pnl_pct = get_portfolio_summary()

color_class = "green" if pnl >= 0 else "red"
sign = "+" if pnl >= 0 else ""

st.subheader("Funds & Portfolio")
st.markdown(f"""
<div class="metric-row">
    <div class="metric-card">
        <div class="metric-label">Available Margin</div>
        <div class="metric-value" style="color: #4184f3;">₹ {margin_val:,.2f}</div>
    </div>
    <div class="metric-card">
        <div class="metric-label">Invested</div>
        <div class="metric-value">₹ {inv_val:,.2f}</div>
    </div>
    <div class="metric-card">
        <div class="metric-label">Current Value</div>
        <div class="metric-value">₹ {cur_val:,.2f}</div>
    </div>
    <div class="metric-card">
        <div class="metric-label">Overall P&L</div>
        <div class="metric-value {color_class}">{sign}₹ {pnl:,.2f} <span style="font-size:16px;">({sign}{pnl_pct:.2f}%)</span></div>
    </div>
</div>
""", unsafe_allow_html=True)

# Open positions from holdings
holdings_data = get_holdings()
if holdings_data and holdings_data.get("status") == "success" and holdings_data.get("data"):
    st.markdown("**(Live Open Positions)**")
    for h in holdings_data["data"]:
        sym = h.get('tradingSymbol')
        h_qty = float(h.get('totalQty', h.get('heldQuantity', 0)))
        if h_qty <= 0: continue
        h_avg = float(h.get('avgCostPrice', h.get('costPrice', 0)))
        cur_price2, prev_price2, _ = get_cached_live_price(sym)
        h_cur = cur_price2
        day_chg = round(cur_price2 - prev_price2, 2)
        day_pct = round((day_chg / prev_price2) * 100, 2) if prev_price2 > 0 else 0.0
        chg_sign = "+" if day_chg >= 0 else ""
        chg_color = "#4caf50" if day_chg >= 0 else "#ff5722"
        chg_arrow = "▲" if day_chg >= 0 else "▼"
        h_pnl = (h_cur - h_avg) * h_qty
        h_pct = (h_pnl / (h_avg * h_qty) * 100) if h_avg > 0 else 0.0
        hc_class = "green" if h_pnl >= 0 else "red"
        h_sign = "+" if h_pnl >= 0 else ""
        # Plain text expander header — st.expander doesn't render HTML
        pos_arrow = "▲" if day_chg >= 0 else "▼"
        pos_header = f"📦 {sym}  ──  Qty {int(h_qty)}  |  CMP ₹{h_cur:,.2f}  {pos_arrow} {chg_sign}{day_chg:,.2f} ({chg_sign}{day_pct:.2f}%)"
        with st.expander(pos_header):
            st.markdown(
                f"""**Avg:** `₹{h_avg:,.2f}` | **CMP:** `₹{h_cur:,.2f}` """
                f"""<span style='color:{chg_color}'>{chg_arrow} {chg_sign}{day_chg:,.2f} ({chg_sign}{day_pct:.2f}%)</span>"""
                f""" | **P&L:** <span class="{hc_class}">{h_sign}₹{h_pnl:,.2f} ({h_sign}{h_pct:.2f}%)</span>""",
                unsafe_allow_html=True
            )
            col_s, col_c = st.columns(2)
            with col_s:
                if st.button("Exit Position", key=f"pos_exit_{sym}", use_container_width=True):
                    order_ticket_modal(sym, "SELL", h_qty)
            with col_c:
                if st.button("Chart", key=f"pos_chart_{sym}", use_container_width=True):
                    chart_modal(sym)

st.divider()

# ==========================================
# MODALS — defined here so they exist before tab buttons call them
# ==========================================
@st.dialog("Live Price Chart", width="large")
def chart_modal(symbol):
    st.write(f"Loading chart for {symbol}...")
    try:
        data = get_cached_chart(symbol)
        fig = go.Figure(data=[go.Candlestick(
            x=data.index, open=data['Open'], high=data['High'],
            low=data['Low'], close=data['Close']
        )])
        fig.update_layout(
            xaxis_rangeslider_visible=False,
            plot_bgcolor='#121212', paper_bgcolor='#121212',
            font=dict(color='#ffffff'),
            margin=dict(l=0, r=0, t=30, b=0), height=500
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Could not load chart: {e}")

@st.dialog("Execute Order")
def order_ticket_modal(symbol, default_txn="BUY", default_qty=1, default_limit=0.0, default_tsl=0.0, is_ai=False, ai_signal_idx=None):
    if is_ai:
        st.subheader(f"🤖 AI Suggested Order: {symbol}")
        st.info("AI parameters are pre-filled. Override any value before confirming.")
    else:
        st.subheader(f"New Order: {symbol}")
        
    col1, col2 = st.columns(2)
    with col1:
        txn_type = st.radio("Transaction", options=["BUY", "SELL"], index=0 if default_txn=="BUY" else 1)
        order_type_options = ["MARKET", "LIMIT"]
        if is_ai or default_tsl > 0:
            order_type_options.append("TRAILING_STOPLOSS")
        order_type = st.selectbox("Order Type", order_type_options, index=1 if default_limit > 0 else 0)
        product_type = st.selectbox("Product Type", ["INTRADAY", "CNC"])
        
    with col2:
        qty = st.number_input("Quantity", min_value=1, value=int(default_qty))
        price = 0.0
        tsl_val = 0.0
        if order_type in ["LIMIT", "TRAILING_STOPLOSS"]:
            price = st.number_input("Limit Price", min_value=0.0, value=float(default_limit), format="%.2f")
        if order_type == "TRAILING_STOPLOSS":
            tsl_val = st.number_input("Trailing Stop-Loss", min_value=0.0, value=float(default_tsl), format="%.2f")
            
    exec_btn = "✅ Confirm AI Trade" if is_ai else "✅ Place Order"
    colA, colB = st.columns(2)
    with colA:
        if st.button(exec_btn, type="primary", use_container_width=True):
            res = place_order_mock(symbol, txn_type, qty, order_type, product_type, price)
            if res and is_ai:
                mark_signal_done(ai_signal_idx, "EXECUTED")
            if res:
                st.rerun()
    with colB:
        if is_ai and st.button("✗ Reject", use_container_width=True):
            mark_signal_done(ai_signal_idx, "REJECTED")
            st.rerun()

# ==========================================
# MAIN CONTENT TABS
# ==========================================
ai_order_count = len(pending_ai_orders)
tab_label_ai = f"🤖 AI Orders ({ai_order_count} pending)" if ai_order_count > 0 else "🤖 AI Orders"
tab_label_inbox = f"🔔 AI Inbox ({len(pending_signals)})" if pending_signals else "🔔 AI Inbox"
tab_watchlist, tab_ai_orders, tab_user_orders, tab_inbox = st.tabs(["📊 Watchlist", tab_label_ai, "📋 My Orders", tab_label_inbox])

# ---- TAB: WATCHLIST ----
with tab_watchlist:
    df_master = load_dhan_scrip_master()
    search_options = []
    if not df_master.empty:
        search_options = df_master['SEM_TRADING_SYMBOL'].tolist()

    col_search, col_add = st.columns([4, 1])
    with col_search:
        selected_symbol = st.selectbox("Search for a stock", options=[""] + search_options, index=0, label_visibility="collapsed", key="watchlist_search")
    with col_add:
        if st.button("+ Add", type="primary", use_container_width=True):
            if selected_symbol and selected_symbol not in st.session_state.watchlist:
                st.session_state.watchlist.append(selected_symbol)
                st.rerun()
    
    if not st.session_state.watchlist:
        st.info("Search above to add stocks to your Watchlist.")
    else:
        for symbol in st.session_state.watchlist:
            cur_price, prev_price, stock_fetch_err = get_cached_live_price(symbol)
            day_chg = round(cur_price - prev_price, 2)
            day_pct = round((day_chg / prev_price) * 100, 2) if prev_price > 0 else 0.0
            chg_sign = "+" if day_chg >= 0 else ""
            chg_color = "#4caf50" if day_chg >= 0 else "#ff5722"
            chg_arrow = "▲" if day_chg >= 0 else "▼"
            holding = get_holding_for_symbol(symbol)
            
            # Plain-text header for st.expander (no HTML allowed in labels)
            chg_arrow_plain = "▲" if day_chg >= 0 else "▼"
            header_plain = f"{symbol}  ──  ₹{cur_price:,.2f}  {chg_arrow_plain} {chg_sign}{day_chg:,.2f} ({chg_sign}{day_pct:.2f}%)"
            if holding:
                h_qty = float(holding.get('totalQty', holding.get('heldQuantity', 0)))
                h_avg = float(holding.get('avgCostPrice', holding.get('costPrice', 0)))
                h_pnl = (cur_price - h_avg) * h_qty
                h_sign2 = "+" if h_pnl >= 0 else ""
                header_plain += f"  |  Holding {int(h_qty)} qty  {h_sign2}₹{h_pnl:,.0f}"
            
            with st.expander(header_plain):
                if stock_fetch_err:
                    st.warning(f"Price fetch error: {stock_fetch_err}")
                # Day change row
                st.markdown(
                    f"₹{cur_price:,.2f} <span style='color:{chg_color};font-size:14px'>{chg_arrow} {chg_sign}{day_chg:,.2f} ({chg_sign}{day_pct:.2f}%)</span>",
                    unsafe_allow_html=True
                )
                if holding:
                    h_qty = float(holding.get('totalQty', holding.get('heldQuantity', 0)))
                    h_avg = float(holding.get('avgCostPrice', holding.get('costPrice', 0)))
                    h_pnl = (cur_price - h_avg) * h_qty
                    h_pct = (h_pnl / (h_avg * h_qty) * 100) if h_avg > 0 else 0.0
                    hc_class = "green" if h_pnl >= 0 else "red"
                    h_sign = "+" if h_pnl >= 0 else ""
                    st.markdown(f"**Holdings:** Avg `₹{h_avg:,.2f}` | Qty `{int(h_qty)}` | P&L <span class='{hc_class}'>{h_sign}₹{h_pnl:,.2f} ({h_sign}{h_pct:.2f}%)</span>", unsafe_allow_html=True)
                
                col_b, col_s, col_e, col_c, col_d = st.columns(5)
                with col_b:
                    if st.button("Buy", key=f"buy_{symbol}", use_container_width=True):
                        order_ticket_modal(symbol, "BUY", 1)
                with col_s:
                    if st.button("Sell", key=f"sell_{symbol}", use_container_width=True):
                        order_ticket_modal(symbol, "SELL", 1)
                with col_e:
                    if holding and h_qty > 0:
                        if st.button("Exit", key=f"exit_{symbol}", use_container_width=True):
                            order_ticket_modal(symbol, "SELL", h_qty)
                with col_c:
                    if st.button("Chart", key=f"chart_{symbol}", use_container_width=True):
                        chart_modal(symbol)
                with col_d:
                    if st.button("🗑️", key=f"del_{symbol}", use_container_width=True):
                        st.session_state.watchlist.remove(symbol)
                        st.rerun()

# ---- TAB: AI ORDERS ----
with tab_ai_orders:
    ai_orders = get_orders(source='AI')
    ai_signals = get_pending_signals()
    
    # Show AI picked stocks from signals (pending review)
    if ai_signals:
        st.markdown("### 🟡 Pending AI Trade Signals")
        st.caption("Stocks picked by the AI agent — review and approve to execute")
        for sig in ai_signals:
            action_color = "#4caf50" if sig['action'] == 'BUY' else "#ff5722"
            col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 1])
            with col1:
                st.markdown(f"<span style='background:{action_color};padding:3px 10px;border-radius:3px;font-weight:600;font-size:13px'>{sig['action']}</span>", unsafe_allow_html=True)
            with col2:
                st.markdown(f"**{sig['symbol']}**  `{sig['confidence']}% conf`")
            with col3:
                st.markdown(f"Limit: **₹{sig['limit_price']:,.2f}**  |  Target: ₹{sig['target_price']:,.2f}")
            with col4:
                st.markdown(f"TSL: ₹{sig['trailing_sl']:,.2f}  |  `{sig['timestamp'][:16]}`")
            with col5:
                if st.button("▶ Execute", key=f"exec_sig_{sig['id']}", type="primary", use_container_width=True):
                    order_ticket_modal(sig['symbol'], default_txn=sig['action'], default_qty=1,
                                       default_limit=sig['limit_price'], default_tsl=sig['trailing_sl'],
                                       is_ai=True, ai_signal_idx=sig['id'])
            st.markdown("<hr style='border-color:#2b2b2b;margin:4px 0'>", unsafe_allow_html=True)
    
    # Show placed AI orders
    if ai_orders:
        st.markdown("### 📋 AI Order History")
        for o in ai_orders:
            status_color = {"PENDING_APPROVAL": "#f0ad4e", "EXECUTED": "#4caf50", "REJECTED": "#ff5722"}.get(o['status'], "#9B9B9B")
            col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 1])
            with col1:
                action_c = "#4caf50" if o['action'] == 'BUY' else "#ff5722"
                st.markdown(f"<span style='background:{action_c};padding:3px 10px;border-radius:3px;font-size:13px'>{o['action']}</span>", unsafe_allow_html=True)
            with col2:
                st.markdown(f"**{o['symbol']}**  ×{int(o['quantity'])}")
            with col3:
                st.markdown(f"₹{o['price']:,.2f} ({o['order_type']})")
            with col4:
                st.markdown(f"<span style='color:{status_color};font-weight:600'>{o['status']}</span>  `{o['timestamp'][:16]}`", unsafe_allow_html=True)
            with col5:
                if o['status'] == 'PENDING_APPROVAL':
                    if st.button("✓ Approve", key=f"app_ai_{o['id']}", use_container_width=True):
                        res = place_order_mock(o['symbol'], o['action'], o['quantity'], o['order_type'], 'INTRADAY', o['price'])
                        if res:
                            update_order_status(o['id'], 'EXECUTED')
                            st.rerun()
            st.markdown("<hr style='border-color:#2b2b2b;margin:4px 0'>", unsafe_allow_html=True)
    
    if not ai_signals and not ai_orders:
        st.info("🤖 AI has not picked any stocks yet. Enable the Autonomous Agent in Settings and wait for the next 15-minute sweep.")

# ---- TAB: USER ORDERS ----
with tab_user_orders:
    user_orders = get_orders(source='USER')
    if user_orders:
        st.markdown("### 📋 Your Order History")
        for o in user_orders:
            status_color = {"PENDING_APPROVAL": "#f0ad4e", "EXECUTED": "#4caf50", "REJECTED": "#ff5722"}.get(o['status'], "#9B9B9B")
            col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 1])
            with col1:
                action_c = "#4caf50" if o['action'] == 'BUY' else "#ff5722"
                st.markdown(f"<span style='background:{action_c};padding:3px 10px;border-radius:3px;font-size:13px'>{o['action']}</span>", unsafe_allow_html=True)
            with col2:
                st.markdown(f"**{o['symbol']}**  ×{int(o['quantity'])}")
            with col3:
                st.markdown(f"₹{o['price']:,.2f} ({o['order_type']})")
            with col4:
                st.markdown(f"<span style='color:{status_color};font-weight:600'>{o['status']}</span>  `{o['timestamp'][:16]}`", unsafe_allow_html=True)
            with col5:
                if o['status'] == 'PENDING_APPROVAL':
                    if st.button("✓ Execute", key=f"exec_usr_{o['id']}", type="primary", use_container_width=True):
                        res = place_order_mock(o['symbol'], o['action'], o['quantity'], o['order_type'], 'INTRADAY', o['price'])
                        if res:
                            update_order_status(o['id'], 'EXECUTED')
                            st.rerun()
                    if st.button("✗ Cancel", key=f"cancel_usr_{o['id']}", use_container_width=True):
                        update_order_status(o['id'], 'REJECTED')
                        st.rerun()
            st.markdown("<hr style='border-color:#2b2b2b;margin:4px 0'>", unsafe_allow_html=True)
    else:
        st.info("No orders placed yet. Use the Watchlist to place your first trade!")

# ---- TAB: AI INBOX (legacy signals) ----
with tab_inbox:
    if pending_signals:
        st.markdown("### 🔔 AI Trading Inbox")
        st.caption("Review and approve or reject AI trade suggestions")
        for sig in pending_signals:
            action_color = "#4caf50" if sig['action'] == 'BUY' else "#ff5722"
            colA, colB, colC, colD, colE = st.columns([1, 2, 2, 2, 1])
            with colA:
                st.markdown(f"<span style='background:{action_color};padding:3px 10px;border-radius:3px;font-weight:600'>{sig['action']}</span>", unsafe_allow_html=True)
            with colB:
                st.markdown(f"**{sig['symbol']}**  `{sig['confidence']}% conf`")
            with colC:
                st.markdown(f"Limit: **₹{sig['limit_price']:,.2f}**")
            with colD:
                st.markdown(f"TSL: ₹{sig['trailing_sl']:,.2f}  |  Target: ₹{sig['target_price']:,.2f}")
            with colE:
                if st.button("Review", key=f"inbox_rev_{sig['id']}", type="primary", use_container_width=True):
                    order_ticket_modal(sig['symbol'], default_txn=sig['action'], default_qty=1,
                                       default_limit=sig['limit_price'], default_tsl=sig['trailing_sl'],
                                       is_ai=True, ai_signal_idx=sig['id'])
            st.markdown("<hr style='border-color:#2b2b2b;margin:4px 0'>", unsafe_allow_html=True)
    else:
        st.info("No pending AI signals. The agent will notify you here when it finds trade opportunities.")
