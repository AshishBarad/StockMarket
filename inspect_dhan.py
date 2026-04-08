import inspect
try:
    from dhanhq import dhanhq
    print(inspect.signature(dhanhq.quote_data))
    print(inspect.signature(dhanhq.intraday_minute_data))
    print(inspect.signature(dhanhq.historical_daily_data))
except Exception as e:
    print(f"Error: {e}")
