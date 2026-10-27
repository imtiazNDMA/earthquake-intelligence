"""Gunicorn entry point: the Flask app with layer caches preloaded, as
``server.py``'s ``main()`` does for the development server."""

from server import STORE, app  # noqa: F401  - gunicorn serves `wsgi:app`

if not STORE.missing():
    STORE.preload()
