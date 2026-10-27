# Hugging Face Space image: eqmon API (public, :7860) + eq_arc (container-local,
# :5000) in one container. Built from the staging tree that
# scripts/deploy_hf_space.py uploads, not from the repo root.
#
# eq_arc runs on the image's system Python so it gets the bundled osgeo
# bindings; eqmon runs in its own uv venv with rasterio/fiona's vendored GDAL.
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.10.3

COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /usr/local/bin/uv

WORKDIR /app

RUN python3 -c "import urllib.request as u; u.urlretrieve('https://bootstrap.pypa.io/get-pip.py', '/tmp/get-pip.py')" \
    && python3 /tmp/get-pip.py --break-system-packages --root-user-action=ignore \
    && rm /tmp/get-pip.py

COPY eq_arc/requirements.txt eq_arc/requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages --root-user-action=ignore \
    -r eq_arc/requirements.txt

ENV UV_PYTHON=/usr/bin/python3 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
COPY pyproject.toml uv.lock ./
COPY notebooks/pyproject.toml notebooks/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-project --no-install-workspace --no-cache

COPY src/ src/
COPY migrations/ migrations/
COPY data/Vs30.tif data/Vs30.tif
COPY eq_arc/ eq_arc/
RUN mkdir -p eq_arc/data/uploads && chown 1000:1000 eq_arc/data/uploads

# Spaces run the container as uid 1000.
USER 1000
ENV HOME=/tmp \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    EQMON_VS30_TIF=/app/data/Vs30.tif \
    ARC_URL=http://127.0.0.1:5000

EXPOSE 7860

CMD ["sh", "-c", "cd /app/eq_arc/scripts && python3 -m gunicorn --bind 127.0.0.1:5000 --workers 1 --threads 4 --timeout 300 wsgi:app & cd /app && exec /app/.venv/bin/uvicorn eqmon.api:app --host 0.0.0.0 --port 7860 --proxy-headers --forwarded-allow-ips='*'"]
