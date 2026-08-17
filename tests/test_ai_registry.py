"""Tool registry: what a given workflow and role may call.

Offering a tool is what authorizes it — the client already refuses any name it
did not send. The registry decides what gets sent, so its refusals are the
enforcement point that prompt text cannot argue with.
"""
import pytest

from eqmon.ai.contracts import ToolFailure
from eqmon.ai.registry import (CostClass, Role, ToolRegistry, ToolSpec,
                               default_registry)


def _spec(name: str, *, authz: Role = Role.VIEWER, **kwargs) -> ToolSpec:
    return ToolSpec(
        name=name,
        schema_version="1.0",
        schema={"type": "function", "function": {"name": name}},
        handler=lambda *a, **k: None,
        authz=authz,
        cost_class=kwargs.get("cost_class", CostClass.DB),
    )


def _registry(*specs) -> ToolRegistry:
    registry = ToolRegistry()
    for spec in specs:
        registry.register(spec)
    return registry


def test_registered_tool_can_be_resolved():
    registry = _registry(_spec("search_events"))
    assert registry.get("search_events").name == "search_events"


def test_duplicate_registration_is_rejected():
    """Two tools sharing a name would make authorization order-dependent."""
    registry = _registry(_spec("search_events"))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_spec("search_events"))


def test_unknown_tool_is_a_typed_failure():
    with pytest.raises(ToolFailure) as failure:
        _registry().get("nonexistent")
    assert failure.value.code == "not_found"


# --- the allowlist ---------------------------------------------------------

def test_schemas_are_offered_only_for_the_workflow_allowlist():
    registry = _registry(_spec("search_events"), _spec("get_catalog_analytics"))
    offered = registry.schemas_for(["search_events"], role=Role.ANALYST)
    assert [schema["function"]["name"] for schema in offered] == ["search_events"]


def test_tool_outside_the_allowlist_is_refused_at_dispatch():
    """Defence in depth: even if a name reaches dispatch, the allowlist decides."""
    registry = _registry(_spec("search_events"), _spec("get_catalog_analytics"))
    with pytest.raises(ToolFailure) as failure:
        registry.resolve("get_catalog_analytics", allowlist=["search_events"],
                         role=Role.ANALYST)
    assert failure.value.code == "invalid_request"


def test_insufficient_role_is_refused():
    registry = _registry(_spec("privileged", authz=Role.ADMINISTRATOR))
    with pytest.raises(ToolFailure) as failure:
        registry.resolve("privileged", allowlist=["privileged"], role=Role.VIEWER)
    assert failure.value.code == "invalid_request"


def test_sufficient_role_is_allowed():
    registry = _registry(_spec("privileged", authz=Role.ANALYST))
    assert registry.resolve("privileged", allowlist=["privileged"],
                            role=Role.ADMINISTRATOR).name == "privileged"


def test_role_below_requirement_never_sees_the_schema():
    """A tool a role may not call must not be advertised to it either."""
    registry = _registry(_spec("privileged", authz=Role.ADMINISTRATOR))
    assert registry.schemas_for(["privileged"], role=Role.VIEWER) == []


# --- side effects ----------------------------------------------------------

def test_registering_a_side_effecting_tool_is_rejected():
    """No rung of the agency ladder writes unattended. Until a phase admits
    side effects, the registry refuses to hold such a tool at all."""
    with pytest.raises(ValueError, match="side effect"):
        ToolRegistry().register(ToolSpec(
            name="delete_event", schema_version="1.0",
            schema={}, handler=lambda: None, authz=Role.ADMINISTRATOR,
            cost_class=CostClass.DB, side_effects="write"))


# --- the shipped registry --------------------------------------------------

def test_default_registry_exposes_the_catalog_tools():
    names = set(default_registry().names())
    assert {"search_events", "get_event_summary"} <= names


def test_every_registered_tool_declares_no_side_effects():
    registry = default_registry()
    assert all(registry.get(name).side_effects == "none"
               for name in registry.names())
