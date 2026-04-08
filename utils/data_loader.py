import pandas as pd
from datetime import datetime
import streamlit as st

@st.cache_data(ttl=86400)
def load_dhan_scrip_master():
    try:
        url = "https://images.dhan.co/api-data/api-scrip-master.csv"
        df = pd.read_csv(url, low_memory=False)
        nse_eq = df[df['SEM_EXM_EXCH_ID'] == 'NSE']
        nse_eq = nse_eq[nse_eq['SEM_INSTRUMENT_NAME'] == 'EQUITY']
        nse_eq = nse_eq.dropna(subset=['SEM_TRADING_SYMBOL'])
        return nse_eq
    except Exception as e:
        st.error(f"Failed to load Dhan Scrip list: {e}")
        return pd.DataFrame()

def load_stock_data(stock_symbol):
    """
    Returns OHLCV DataFrame for a symbol using Dhan's historical API.
    Falls back to an empty DataFrame on error.
    """
    try:
        from utils.dhan_integration import load_dhan_chart_data
        return load_dhan_chart_data(stock_symbol)
    except Exception as e:
        raise Exception(f"Error loading stock data: {e}")