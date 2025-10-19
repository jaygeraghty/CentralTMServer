FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy application code
COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV API_SERVER_URL="http://api:5000"
ENV LOCATION=""

# Expose port for the web interface
EXPOSE 5001

# Command to run the location-specific web application
CMD ["python", "location_container.py"]