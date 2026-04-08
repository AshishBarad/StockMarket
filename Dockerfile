FROM python:3.9-slim

LABEL maintainer="StockMarket AI Dashboard"
LABEL description="Dhan Trading Dashboard + Autonomous AI Agent"

WORKDIR /app

# System deps for pandas/numpy compilation (slim image needs these)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create persistent DB directory
RUN mkdir -p /app/db

# Copy streamlit theme config
RUN mkdir -p /app/.streamlit
COPY .streamlit/config.toml /app/.streamlit/config.toml

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

EXPOSE 8501

ENTRYPOINT ["/app/entrypoint.sh"]
