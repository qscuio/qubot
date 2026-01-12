FROM python:3.11-slim

WORKDIR /app

# Install system dependencies, uv, Node.js 20 and CLI agents
RUN apt-get update && apt-get install -y git curl gnupg && \
    # Install uv (fast Python package installer)
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    # Install Node.js 20
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    # Install CLI coding agents for Vibe Remote
    npm install -g @google/gemini-cli @anthropic-ai/claude-code @openai/codex 2>/dev/null || true && \
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
