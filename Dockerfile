FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (git for gitpython, nodejs/npm for legacy hooks)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set python path
ENV PYTHONPATH=/app

# Run the application
CMD ["python", "app/main.py"]
