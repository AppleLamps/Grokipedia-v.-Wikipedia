# Use Python 3.11 slim image
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Build the SQLite slug database during Docker build
# This happens once and is baked into the image
RUN echo "Building slug database..." && \
    python scripts/build_slug_db.py --output /app/app/slugs.db && \
    echo "Database built successfully"

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application and built database
COPY --from=builder /app /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV RAILWAY_ENVIRONMENT=true

# Expose port
EXPOSE 8080

# Run the application
CMD ["gunicorn", "run:app", "--bind", "0.0.0.0:8080", "--timeout", "300", "--graceful-timeout", "120", "--workers", "1", "--threads", "2"]
