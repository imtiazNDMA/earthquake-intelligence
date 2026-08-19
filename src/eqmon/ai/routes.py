"""Opt-in, unauthenticated shadow routes for bounded AI workflows."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from .. import db
from . import config, jobs
from .broker import (Broker, BrokerClosedError, BrokerFullError,
                     ExecutionDeadlineError, QueueDeadlineError)
from .client import LMStudioError
from .contracts import ToolFailure
from .registry import Role
from .registry import default_registry
from .workflows.agent_chat import (AGENT_CHAT_WORKFLOW_VERSION,
                                   AgentChatRequest, run_agent_chat)
from .workflows.catalog_query import (CATALOG_QUERY_WORKFLOW_VERSION,
                                      CatalogQueryRequest,
                                      translate_catalog_query)

router = APIRouter(prefix="/ai", tags=["ai"])
broker = Broker()


def _require_enabled() -> None:
    if not config.AI_ROUTES_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="AI routes are disabled; set EQMON_AI_ENABLED=true",
        )


@router.get("/health")
async def health() -> dict:
    inference_available = False
    loaded_models: list[str] = []
    inference_error = None
    if config.AI_ROUTES_ENABLED:
        try:
            async with httpx.AsyncClient(
                base_url=config.LMSTUDIO_BASE_URL,
                headers={"Authorization": f"Bearer {config.LMSTUDIO_API_KEY}"},
                timeout=5.0,
            ) as client:
                response = await client.get("/models")
                response.raise_for_status()
                loaded_models = [
                    item["id"] for item in response.json().get("data", [])
                    if isinstance(item, dict) and isinstance(item.get("id"), str)
                ]
            inference_available = config.MODEL_PRIMARY in loaded_models
            if not inference_available:
                inference_error = f"primary model not loaded: {config.MODEL_PRIMARY}"
        except (httpx.HTTPError, ValueError) as exc:
            inference_error = str(exc)
    return {
        "enabled": config.AI_ROUTES_ENABLED,
        "inference_available": inference_available,
        "mode": (
            "ready" if inference_available else
            "inference-unavailable" if config.AI_ROUTES_ENABLED else
            "disabled"
        ),
        "workflow": "agent_chat",
        "model": config.MODEL_PRIMARY,
        "loaded_models": loaded_models,
        "error": inference_error,
        "broker": broker.stats.as_dict(),
    }


@router.post("/catalog-query")
async def catalog_query(request: CatalogQueryRequest) -> dict:
    _require_enabled()
    with db.get_conn() as conn:
        job_id = jobs.create_catalog_query_job(
            conn, query=request.query,
            workflow_version=CATALOG_QUERY_WORKFLOW_VERSION,
        )

    try:
        result = await translate_catalog_query(
            broker, request, role=Role.VIEWER)
    except BrokerFullError as exc:
        _record_failure(job_id, "queue_full", str(exc))
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (QueueDeadlineError, ExecutionDeadlineError) as exc:
        _record_failure(job_id, "deadline", str(exc))
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (BrokerClosedError, LMStudioError) as exc:
        _record_failure(job_id, "inference_unavailable", str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ToolFailure as exc:
        _record_failure(job_id, exc.code, exc.message)
        raise HTTPException(status_code=422, detail=exc.as_dict()) from exc

    payload = result.model_dump(mode="json")
    with db.get_conn() as conn:
        jobs.complete_job(
            conn, job_id, result=payload, model=result.model, usage=result.usage)
    return {"job_id": job_id, **payload}


@router.post("/chat")
async def agent_chat(request: AgentChatRequest) -> dict:
    _require_enabled()
    with db.get_conn() as conn:
        job_id = jobs.create_agent_chat_job(
            conn, message=request.message,
            workflow_version=AGENT_CHAT_WORKFLOW_VERSION,
        )

    registry = default_registry()

    async def execute_tool(name: str, arguments: dict):
        with db.get_conn() as conn:
            return await registry.dispatch(
                conn, name, arguments,
                allowlist=registry.names(), role=Role.VIEWER,
            )

    try:
        result = await run_agent_chat(
            broker, request, execute_tool=execute_tool,
            registry=registry, role=Role.VIEWER,
        )
    except BrokerFullError as exc:
        _record_failure(job_id, "queue_full", str(exc))
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (QueueDeadlineError, ExecutionDeadlineError) as exc:
        _record_failure(job_id, "deadline", str(exc))
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (BrokerClosedError, LMStudioError) as exc:
        _record_failure(job_id, "inference_unavailable", str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ToolFailure as exc:
        _record_failure(job_id, exc.code, exc.message)
        raise HTTPException(status_code=422, detail=exc.as_dict()) from exc

    payload = result.model_dump(mode="json")
    with db.get_conn() as conn:
        jobs.complete_job(
            conn, job_id, result=payload, model=result.model, usage=result.usage)
    return {"job_id": job_id, **payload}


def _record_failure(job_id: int, code: str, message: str) -> None:
    with db.get_conn() as conn:
        jobs.fail_job(conn, job_id, code=code, message=message)
