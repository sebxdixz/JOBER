"""Estado compartido del grafo LangGraph (multiagente)."""

from __future__ import annotations

from typing import Annotated, Optional

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage

from jober.core.models import (
    DocumentosGenerados,
    OfertaTrabajo,
    PerfilMaestro,
)


class JoberState(BaseModel):
    """Estado global que fluye entre todos los nodos/agentes del grafo."""

    # Mensajes del chat (para agentes conversacionales como el onboarding)
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # Datos del usuario
    perfil: PerfilMaestro = Field(default_factory=PerfilMaestro)
    cv_raw_text: str = ""

    # Datos de la oferta
    oferta: OfertaTrabajo = Field(default_factory=OfertaTrabajo)
    job_url: str = ""

    # Output generado por los agentes
    documentos: DocumentosGenerados = Field(default_factory=DocumentosGenerados)

    # Control de flujo
    current_agent: str = ""
    next_step: str = ""
    error: str = ""
