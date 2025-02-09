import streamlit as st
import yfinance as yf
import plotly.graph_objs as go
from utils.data_loader import load_stock_data
from utils.model_predictor import predict_stock_trend
from utils.error_handler import handle_error

# Page configuration
st.set_page_config(page_title="Stock Analysis App", layout="wide")

# Sidebar for settings
st.sidebar.title("Settings")
api_key = st.sidebar.text_input("Enter API Key:")
performance_profile = st.sidebar.slider("Performance Profile", 1, 10, 5)

# Main page
st.title("Indian Stock Market Analysis")

# Search bar
stock_symbol = st.text_input("Enter stock symbol (e.g., RELIANCE.NS):")

if stock_symbol:
    try:
        # Fetch and display stock data
        stock_data = load_stock_data(stock_symbol)
        st.write(f"Live Price: {stock_data['Close'][-1]}")

        # Plot graph
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=stock_data.index, y=stock_data['Close'], mode='lines', name='Close Price'))
        st.plotly_chart(fig)

        # Predict stock trend
        prediction = predict_stock_trend(stock_data)
        st.write(f"Prediction: {prediction}")

    except Exception as e:
        handle_error(e)