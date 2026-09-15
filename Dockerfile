FROM python:3.11-slim

LABEL maintainer="ULTRON Dev Team"
LABEL description="ULTRON Streaming Live RAG Pipeline"

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency specs
COPY pyproject.toml ./
COPY requirements.txt ./

# Install Python dependencies
RUN uv pip install --system -e ".[dev]"

# Copy application code
COPY . .

# Logs directory
RUN mkdir -p logs

# Default: run benchmark gates
CMD ["python", "scripts/run_benchmark.py"]
