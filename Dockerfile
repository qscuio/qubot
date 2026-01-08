FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and uv (fast Python package installer)
RUN apt-get update && apt-get install -y git curl && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    rm -rf /var/lib/apt/lists/*

# Add uv to PATH
ENV PATH="/root/.local/bin:$PATH"

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY . .

# Set python path
ENV PYTHONPATH=/app

# Run the application
CMD ["python", "app/main.py"]
