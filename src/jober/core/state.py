"""Shared LangGraph state helpers."""

from __future__ import annotations

from typing import Annotated, Any, Mapping, cast
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from jober.core.models import (
    DocumentosGenerados,
    OfertaTrabajo,
    PerfilMaestro,
    ResultadoAplicacion,
)


class JoberState(TypedDict, total=False):
    """TypedDict state that flows through LangGraph."""

    messages: Annotated[list[BaseMessage], add_messages]
    perfil: PerfilMaestro
    cv_raw_text: str
    oferta: OfertaTrabajo
    job_url: str
    should_apply: bool
    screening_notes: list[str]
    documentos: DocumentosGenerados
    resultado_aplicacion: ResultadoAplicacion
    current_agent: str
    next_step: str
    error: str


STATE_MODEL_FACTORIES = {
    "perfil": PerfilMaestro,
    "oferta": OfertaTrabajo,
    "documentos": DocumentosGenerados,
    "resultado_aplicacion": ResultadoAplicacion,
}

STATE_DEFAULT_FACTORIES = {
    "messages": list,
    "perfil": PerfilMaestro,
    "cv_raw_text": str,
    "oferta": OfertaTrabajo,
    "job_url": str,
    "should_apply": lambda: False,
    "screening_notes": list,
    "documentos": DocumentosGenerados,
    "resultado_aplicacion": ResultadoAplicacion,
    "current_agent": str,
    "next_step": str,
    "error": str,
}

STATE_KEYS = tuple(STATE_DEFAULT_FACTORIES.keys())


def _coerce_state_value(key: str, value: Any) -> Any:
    if key in STATE_MODEL_FACTORIES:
        model_factory = STATE_MODEL_FACTORIES[key]
        if value is None:
            return model_factory()
        if isinstance(value, model_factory):
            return value
        return model_factory.model_validate(value)
    if key in {"messages", "screening_notes"}:
        if value is None:
            return []
        return list(value)
    if key in {"cv_raw_text", "job_url", "current_agent", "next_step", "error"}:
        return "" if value is None else str(value)
    if key == "should_apply":
        return bool(value)
    return value


def coerce_state(state: Mapping[str, Any] | "StateView" | None = None, **overrides: Any) -> JoberState:
    """Normalize a raw mapping into a full JoberState dict."""
    raw: dict[str, Any]
    if state is None:
        raw = {}
    elif isinstance(state, StateView):
        raw = dict(state.as_dict())
    else:
        raw = dict(state)
    raw.update(overrides)

    normalized: dict[str, Any] = {}
    for key, factory in STATE_DEFAULT_FACTORIES.items():
        normalized[key] = _coerce_state_value(key, raw.get(key, factory()))
    return cast(JoberState, normalized)


def new_state(**overrides: Any) -> JoberState:
    """Create a fresh state with defaults plus overrides."""
    return coerce_state(None, **overrides)


class StateView:
    """Attribute-friendly wrapper around the TypedDict state."""

    __slots__ = ("_state",)

    def __init__(self, state: Mapping[str, Any] | "StateView" | None = None, **overrides: Any) -> None:
        object.__setattr__(self, "_state", coerce_state(state, **overrides))

    def __getattr__(self, name: str) -> Any:
        if name in STATE_DEFAULT_FACTORIES:
            return self._state[name]
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_state":
            object.__setattr__(self, name, value)
            return
        if name in STATE_DEFAULT_FACTORIES:
            self._state[name] = _coerce_state_value(name, value)
            return
        raise AttributeError(name)

    def __getitem__(self, key: str) -> Any:
        return self._state[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._state[key] = _coerce_state_value(key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def items(self):
        return self._state.items()

    def keys(self):
        return self._state.keys()

    def values(self):
        return self._state.values()

    def as_dict(self) -> JoberState:
        return self._state


def view_state(state: Mapping[str, Any] | StateView | None = None, **overrides: Any) -> StateView:
    """Wrap a raw state mapping with attribute access."""
    return StateView(state, **overrides)
