FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.6.13

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY src/ src/
COPY scripts/ scripts/
COPY migrations/ migrations/
COPY data/ data/
COPY web/ web/

# Vs30.tif is gitignored, so git-based builds (Render) fetch it from object storage.
ARG VS30_URL=""
RUN if [ -n "$VS30_URL" ] && [ ! -f data/Vs30.tif ]; then \
      python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], 'data/Vs30.tif')" "$VS30_URL"; \
    fi

ENV EQMON_VS30_TIF=data/Vs30.tif \
    DATABASE_URL=postgres://eqmon:eqmon@db:5432/eqmon \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD uv run uvicorn eqmon.api:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips="*"
