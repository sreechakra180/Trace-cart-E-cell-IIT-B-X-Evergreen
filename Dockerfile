# Multi-stage production Dockerfile for TraceCart
# Stage 1: Build & wheels
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-core.txt pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir build && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -e .

# Stage 2: Minimal runtime image
FROM python:3.12-slim AS runner

# Security: run as non-root user
RUN groupadd -r tracecart && useradd -r -g tracecart -m -d /home/tracecart tracecart

WORKDIR /app

# Install minimal runtime system libraries needed for OpenCV headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements-core.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-core.txt uvicorn httpx

# Copy project code and configuration
COPY configs/ /app/configs/
COPY data/ /app/data/
COPY src/ /app/src/
COPY app/ /app/app/
COPY pyproject.toml README.md /app/

# Install local tracecart package
RUN pip install --no-cache-dir -e .

# Create persistent directories and set ownership
RUN mkdir -p /app/runs /app/data/uploads && \
    chown -R tracecart:tracecart /app

USER tracecart

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000"]
