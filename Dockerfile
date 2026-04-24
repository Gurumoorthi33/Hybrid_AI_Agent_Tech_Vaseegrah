# ─────────────────────────────────────────────────────────────────
# Stage 1 — builder: install all Python dependencies
# ─────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System packages needed to compile C extensions (faiss, numpy, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    git \
    curl \
    libgomp1 \
  && rm -rf /var/lib/apt/lists/*

# Copy only requirements first — layer cache
COPY requirements.txt .

# Install into /install so we can copy cleanly into stage 2
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────────────────────────
# Stage 2 — runtime: lean image, no build tools
# ─────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime OS packages only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY agents/      ./agents/
COPY auth/        ./auth/
COPY config/      ./config/
COPY graph/       ./graph/
COPY memory/      ./memory/
COPY routers/     ./routers/
COPY utils/       ./utils/
COPY server.py    ./server.py
COPY main.py      ./main.py
COPY setup.py     ./setup.py
COPY dashboard/   ./dashboard/

# Create data directories (RAG indexes + customer files)
RUN mkdir -p data/default data/customers

# Non-root user for security
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

# Health check — calls /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Uvicorn with 2 workers — scale up in docker-compose / ECS task definition
CMD ["uvicorn", "server:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
