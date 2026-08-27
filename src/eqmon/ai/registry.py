"""Tool registration, authorization, and dispatch.

Three checks stand between a model and a domain service, and they are
deliberately redundant:

1. `schemas_for` decides what is *offered* for a workflow and role. A tool that
   is never offered is one the model has no way to name.
2. `client.py` refuses any returned name that was not offered, so a hallucinated
   name dies before it reaches dispatch.
3. `resolve` re-checks the allowlist and the role at dispatch, because the first
   two are prompt-adjacent and this one is not.

Prompt text can talk a model into *asking* for anything. None of it changes what
this module will hand back, which is the point.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
import inspect
from typing import Callable, Iterable, Literal, Sequence

from pydantic import BaseModel, ValidationError

from .contracts import ToolFailure


class Role(IntEnum):
    """Ordered so authorization is a comparison rather than a lookup table."""
    VIEWER = 10
    ANALYST = 20
    OPERATOR = 30
    REVIEWER = 40
    ADMINISTRATOR = 50


class CostClass(str, Enum):
    """What a call costs, used to budget a run rather than to price it."""
    CHEAP = "cheap"          # pure computation, no I/O
    DB = "db"                # one or more PostGIS queries
    EXTERNAL = "external"    # an approved third-party service
    COMPUTE = "compute"      # raster or grid work


@dataclass(frozen=True)
class ToolSpec:
    """One registered capability."""
    name: str
    schema_version: str
    schema: dict
    handler: Callable
    authz: Role
    cost_class: CostClass
    side_effects: Literal["none", "write"] = "none"
    freshness_s: float | None = None
    input_model: type[BaseModel] | None = None
    output_model: type[BaseModel] | None = None
    argument_mode: Literal["kwargs", "model"] = "kwargs"


@dataclass
class ToolRegistry:
    """The set of tools this deployment admits."""
    _specs: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.side_effects != "none":
            raise ValueError(
                f"tool {spec.name!r} declares a side effect; no phase of the "
                "agency ladder admits unattended writes")
        if spec.name in self._specs:
            raise ValueError(f"tool {spec.name!r} is already registered")
        self._specs[spec.name] = spec
        return spec

    def names(self) -> list[str]:
        return sorted(self._specs)

    def get(self, name: str) -> ToolSpec:
        spec = self._specs.get(name)
        if spec is None:
            raise ToolFailure("not_found", f"no tool named {name!r}",
                              detail={"tool": name})
        return spec

    def schemas_for(self, allowlist: Sequence[str], *, role: Role) -> list[dict]:
        """Schemas to offer, filtered by workflow allowlist and role."""
        return [spec.schema for name in allowlist
                if (spec := self._specs.get(name)) is not None
                and role >= spec.authz]

    def resolve(self, name: str, *, allowlist: Iterable[str],
                role: Role) -> ToolSpec:
        """The spec for a call the model actually made, or a typed refusal."""
        spec = self.get(name)
        if name not in set(allowlist):
            raise ToolFailure(
                "invalid_request",
                f"tool {name!r} is not available in this workflow",
                detail={"tool": name})
        if role < spec.authz:
            raise ToolFailure(
                "invalid_request",
                f"tool {name!r} requires {spec.authz.name}",
                detail={"tool": name, "required_role": spec.authz.name})
        return spec

    async def dispatch(self, conn, name: str, arguments: dict, *,
                       allowlist: Iterable[str], role: Role) -> BaseModel:
        """Authorize, validate, invoke, and validate one model-requested call."""
        spec = self.resolve(name, allowlist=allowlist, role=role)
        if spec.input_model is None or spec.output_model is None:
            raise ToolFailure("invalid_request", f"tool {name!r} has no typed contract")
        try:
            request = spec.input_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolFailure(
                "invalid_request", f"invalid arguments for {name!r}",
                detail={"issues": exc.errors(include_input=False)},
            ) from exc
        if spec.argument_mode == "model":
            result = spec.handler(conn, request)
        else:
            result = spec.handler(
                conn, **request.model_dump(exclude_none=True))
        if inspect.isawaitable(result):
            result = await result
        try:
            return spec.output_model.model_validate(result)
        except ValidationError as exc:
            raise ToolFailure(
                "partial", f"invalid result from {name!r}",
                detail={"issues": exc.errors(include_input=False)},
            ) from exc


_default: ToolRegistry | None = None


def default_registry() -> ToolRegistry:
    """The registry this deployment ships.

    Built lazily and cached: registration imports the adapter modules, and those
    import domain services, so doing it at module scope would make importing the
    registry pull in half the application.
    """
    global _default
    if _default is None:
        _default = _build()
    return _default


def _build() -> ToolRegistry:
    from eqmon.aftershock_service import AftershockForecastInput
    from eqmon.events.search import EventSearchSpec

    from .contracts import (AftershockSummaryResult, CatalogAnalyticsInput,
                            CatalogAnalyticsResult, EventAnalysisResult,
                            EventIdInput, EventSummary, ExposureSummaryInput,
                            ExposureSummaryResult, PlaceResolutionInput,
                            PlaceResolutionResult, SearchEventsResult)
    from .tools import events as event_tools
    from .tools.schemas import (SEARCH_EVENTS_TOOL_NAME,
                                SEARCH_EVENTS_TOOL_SCHEMA_VERSION,
                                get_event_summary_tool, search_events_tool)

    registry = ToolRegistry()
    registry.register(ToolSpec(
        name=SEARCH_EVENTS_TOOL_NAME,
        schema_version=SEARCH_EVENTS_TOOL_SCHEMA_VERSION,
        schema=search_events_tool(),
        handler=event_tools.search_events,
        authz=Role.VIEWER,
        cost_class=CostClass.DB,
        input_model=EventSearchSpec,
        output_model=SearchEventsResult,
        argument_mode="model",
    ))
    registry.register(ToolSpec(
        name="get_event_summary",
        schema_version="1.0",
        schema=get_event_summary_tool(),
        handler=event_tools.get_event_summary,
        authz=Role.VIEWER,
        cost_class=CostClass.DB,
        input_model=EventIdInput,
        output_model=EventSummary,
    ))

    from .tools import analysis as analysis_tools
    from .tools import places as place_tools
    from .tools.schemas import (GET_EVENT_ANALYSIS_TOOL_SCHEMA_VERSION,
                                 get_aftershock_summary_tool,
                                 get_catalog_analytics_tool,
                                 get_event_analysis_tool, resolve_place_tool)

    registry.register(ToolSpec(
        name="get_catalog_analytics",
        schema_version="1.0",
        schema=get_catalog_analytics_tool(),
        handler=analysis_tools.get_catalog_analytics,
        authz=Role.VIEWER,
        cost_class=CostClass.DB,
        input_model=CatalogAnalyticsInput,
        output_model=CatalogAnalyticsResult,
    ))
    registry.register(ToolSpec(
        name="get_event_analysis",
        schema_version=GET_EVENT_ANALYSIS_TOOL_SCHEMA_VERSION,
        schema=get_event_analysis_tool(),
        handler=analysis_tools.get_event_analysis,
        authz=Role.VIEWER,
        cost_class=CostClass.COMPUTE,
        input_model=EventIdInput,
        output_model=EventAnalysisResult,
    ))
    registry.register(ToolSpec(
        name="get_aftershock_summary",
        schema_version="1.0",
        schema=get_aftershock_summary_tool(),
        handler=analysis_tools.get_aftershock_summary,
        authz=Role.VIEWER,
        cost_class=CostClass.COMPUTE,
        input_model=AftershockForecastInput,
        output_model=AftershockSummaryResult,
    ))
    registry.register(ToolSpec(
        name="resolve_place",
        schema_version="1.0",
        schema=resolve_place_tool(),
        handler=place_tools.resolve_place,
        authz=Role.VIEWER,
        cost_class=CostClass.DB,
        input_model=PlaceResolutionInput,
        output_model=PlaceResolutionResult,
    ))
    from .tools import exposure as exposure_tools
    from .tools.schemas import get_exposure_summary_tool

    registry.register(ToolSpec(
        name="get_exposure_summary",
        schema_version="1.0",
        schema=get_exposure_summary_tool(),
        handler=exposure_tools.get_exposure_summary,
        authz=Role.VIEWER,
        cost_class=CostClass.EXTERNAL,
        freshness_s=None,
        input_model=ExposureSummaryInput,
        output_model=ExposureSummaryResult,
    ))
    return registry
