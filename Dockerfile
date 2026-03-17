FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for numpy/pandas compilation on slim)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY modules/ modules/
COPY master_strategy_engine.py .
COPY config.yaml .
COPY run_evaluator.py .

# Data directory will be mounted at runtime
RUN mkdir -p /app/Data /app/Outputs

# Default command
CMD ["python", "master_strategy_engine.py", "--config", "config.yaml"]
