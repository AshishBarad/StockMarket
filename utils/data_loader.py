import yfinance as yf
import pandas as pd
from datetime import datetime

def load_stock_data(stock_symbol):
    try:
        # Fetch stock data
        stock_data = yf.download(stock_symbol, start="2023-01-01", end=datetime.today().strftime('%Y-%m-%d'))
        return stock_data
    except Exception as e:
        raise Exception(f"Error loading stock data: {e}")