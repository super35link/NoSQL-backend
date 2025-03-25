FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies in smaller batches with increased timeout
# First batch: Basic dependencies
RUN pip install --no-cache-dir --timeout 100 \
    fastapi \
    uvicorn \
    pydantic-settings \
    PyYAML \
    pytest

# Second batch: Database dependencies
RUN pip install --no-cache-dir --timeout 100 \
    sqlalchemy \
    asyncpg \
    psycopg2-binary \
    alembic \
    fastapi-users \
    fastapi-users-db-sqlalchemy

# Third batch: MongoDB dependencies
RUN pip install --no-cache-dir --timeout 100 \
    motor \
    pymongo

# Fourth batch: Qdrant dependencies
RUN pip install --no-cache-dir --timeout 100 \
    qdrant-client

# Install PyTorch using the official method instead of pip
RUN pip install --no-cache-dir --timeout 100 \
    sentence-transformers==3.3.1 \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.0

# Copy the application code
COPY . .

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
