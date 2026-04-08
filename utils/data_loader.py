import yfinance as yf
import pandas as pd
from datetime import datetime
import streamlit as st

@st.cache_data(ttl=86400)
def load_dhan_scrip_master():
    try:
        url = "https://images.dhan.co/api-data/api-scrip-master.csv"
        df = pd.read_csv(url, low_memory=False)
        # We only want NSE Equity for simplicity
        nse_eq = df[df['SEM_EXM_EXCH_ID'] == 'NSE']
        nse_eq = nse_eq[nse_eq['SEM_INSTRUMENT_NAME'] == 'EQUITY']
        nse_eq = nse_eq.dropna(subset=['SEM_TRADING_SYMBOL'])
        return nse_eq
    except Exception as e:
        st.error(f"Failed to load Dhan Scrip list: {e}")
        return pd.DataFrame()

def load_stock_data(stock_symbol):
    try:
        if not stock_symbol.endswith('.NS'):
            stock_symbol += '.NS'
        stock_data = yf.download(stock_symbol, start="2024-01-01", end=datetime.today().strftime('%Y-%m-%d'))
        return stock_data
    except Exception as e:
        raise Exception(f"Error loading stock data: {e}")