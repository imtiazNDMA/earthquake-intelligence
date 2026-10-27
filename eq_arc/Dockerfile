# GDAL image ships Python 3.12 with osgeo + numpy; numpy is left to the image so
# the GDAL bindings stay ABI-compatible.
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.10.3

WORKDIR /app

RUN python3 -c "import urllib.request as u; u.urlretrieve('https://bootstrap.pypa.io/get-pip.py', '/tmp/get-pip.py')" \
    && python3 /tmp/get-pip.py --break-system-packages --root-user-action=ignore \
    && rm /tmp/get-pip.py

COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --break-system-packages --root-user-action=ignore -r requirements.txt

COPY scripts/ scripts/
COPY data/sample_mmi/ data/sample_mmi/

# The 146 MB layer caches are gitignored; git-based builds (Render) fetch them.
ARG ARC_CACHE_URL=""
RUN mkdir -p data/cache data/uploads \
    && if [ -n "$ARC_CACHE_URL" ]; then python3 scripts/fetch_cache.py "$ARC_CACHE_URL"; fi

EXPOSE 5000

# One worker: each worker holds its own ~150 MB copy of the caches.
CMD gunicorn --chdir scripts --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 4 --timeout 300 wsgi:app
