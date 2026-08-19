from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from eqmon.ai import routes
from eqmon.ai.workflows.catalog_query import CatalogQueryResult
from eqmon.events.search import EventSearchSpec


def _client():
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_health_discloses_disabled_mode(monkeypatch):
    monkeypatch.setattr(routes.config, "AI_ROUTES_ENABLED", False)
    body = _client().get("/ai/health").json()
    assert body["enabled"] is False
    assert body["inference_available"] is False
    assert body["mode"] == "disabled"


def test_health_reports_loaded_primary_model(monkeypatch):
    monkeypatch.setattr(routes.config, "AI_ROUTES_ENABLED", True)

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": routes.config.MODEL_PRIMARY}]}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, path):
            assert path == "/models"
            return _Response()

    monkeypatch.setattr(routes.httpx, "AsyncClient", lambda **kwargs: _Client())

    body = _client().get("/ai/health").json()

    assert body["enabled"] is True
    assert body["inference_available"] is True
    assert body["mode"] == "ready"
    assert body["workflow"] == "agent_chat"


def test_catalog_route_is_disabled_before_opening_database(monkeypatch):
    monkeypatch.setattr(routes.config, "AI_ROUTES_ENABLED", False)

    @contextmanager
    def forbidden_connection():
        raise AssertionError("disabled route must not open the database")
        yield

    monkeypatch.setattr(routes.db, "get_conn", forbidden_connection)
    response = _client().post("/ai/catalog-query", json={"query": "M5 today"})
    assert response.status_code == 503


def test_catalog_route_records_job_without_raw_query(monkeypatch):
    monkeypatch.setattr(routes.config, "AI_ROUTES_ENABLED", True)
    connection = object()

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(routes.db, "get_conn", fake_connection)
    recorded = {}

    def create(conn, **kwargs):
        recorded["create"] = kwargs
        return 44

    def complete(conn, job_id, **kwargs):
        recorded["complete"] = {"job_id": job_id, **kwargs}

    monkeypatch.setattr(routes.jobs, "create_catalog_query_job", create)
    monkeypatch.setattr(routes.jobs, "complete_job", complete)

    async def translate(*args, **kwargs):
        return CatalogQueryResult(
            spec=EventSearchSpec(min_magnitude=5),
            model="test-model", latency_s=0.2, usage={"total_tokens": 10},
        )

    monkeypatch.setattr(routes, "translate_catalog_query", translate)
    response = _client().post(
        "/ai/catalog-query", json={"query": "earthquakes M5 and above"})

    assert response.status_code == 200
    assert response.json()["job_id"] == 44
    assert response.json()["spec"]["min_magnitude"] == 5
    assert recorded["create"]["query"] == "earthquakes M5 and above"
    persisted = recorded["complete"]["result"]
    assert "query" not in persisted
    assert persisted["spec"]["min_magnitude"] == 5
