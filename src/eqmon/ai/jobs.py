"""Minimal AI job audit records without prompts or model reasoning."""
from __future__ import annotations

import hashlib

import psycopg
from psycopg.types.json import Jsonb


def request_fingerprint(query: str) -> dict:
    encoded = query.encode("utf-8")
    return {
        "query_sha256": hashlib.sha256(encoded).hexdigest(),
        "query_chars": len(query),
    }


def create_catalog_query_job(conn: psycopg.Connection, *, query: str,
                             workflow_version: str, role: str = "VIEWER",
                             actor_id: str = "unauthenticated-local") -> int:
    row = conn.execute(
        "INSERT INTO ai_job (workflow, workflow_version, actor_id, role, status, "
        "request_fingerprint, started_at) VALUES "
        "('catalog_query', %s, %s, %s, 'running', %s, now()) RETURNING id",
        (workflow_version, actor_id, role, Jsonb(request_fingerprint(query))),
    ).fetchone()
    return row[0]


def create_agent_chat_job(conn: psycopg.Connection, *, message: str,
                          workflow_version: str, role: str = "VIEWER",
                          actor_id: str = "unauthenticated-local") -> int:
    row = conn.execute(
        "INSERT INTO ai_job (workflow, workflow_version, actor_id, role, status, "
        "request_fingerprint, started_at) VALUES "
        "('agent_chat', %s, %s, %s, 'running', %s, now()) RETURNING id",
        (workflow_version, actor_id, role, Jsonb(request_fingerprint(message))),
    ).fetchone()
    return row[0]


def complete_job(conn: psycopg.Connection, job_id: int, *, result: dict,
                 model: str, usage: dict) -> None:
    conn.execute(
        "UPDATE ai_job SET status = 'completed', result = %s, model = %s, "
        "usage = %s, completed_at = now() WHERE id = %s AND status = 'running'",
        (Jsonb(result), model, Jsonb(usage), job_id),
    )


def fail_job(conn: psycopg.Connection, job_id: int, *, code: str,
             message: str) -> None:
    conn.execute(
        "UPDATE ai_job SET status = 'failed', error_code = %s, "
        "error_message = %s, completed_at = now() "
        "WHERE id = %s AND status = 'running'",
        (code, message[:500], job_id),
    )
