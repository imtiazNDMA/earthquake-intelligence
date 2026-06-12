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
COPY data/ data/
COPY web/ web/

ENV EQMON_VS30_TIF=data/Vs30.tif \
    DATABASE_URL=postgres://eqmon:eqmon@db:5432/eqmon \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "eqmon.api:app", "--host", "0.0.0.0", "--port", "8000"]
