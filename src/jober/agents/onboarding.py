"""Agente de onboarding — entrevista interactiva para completar el perfil maestro."""

from __future__ import annotations

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from jober.core.config import get_llm
from jober.core.models import PerfilMaestro
from jober.core.state import JoberState
from jober.utils.llm_helpers import strip_markdown_fences


ONBOARDING_PROMPT = """Eres un entrevistador profesional de recursos humanos.
Tu objetivo es completar el perfil profesional del usuario haciendo preguntas específicas.

Ya tienes información extraída de su CV (se te proporcionará como JSON).
Tu trabajo es:
1. Identificar qué información falta o es débil
2. Hacer UNA pregunta a la vez, concreta y directa
3. Cubrir: habilidades no mencionadas, logros cuantificables, motivaciones, preferencias laborales
4. Cuando sientas que tienes suficiente información, responde exactamente: [ONBOARDING_COMPLETO]

Sé amigable pero profesional. Habla en español.
No hagas más de 8-10 preguntas en total."""


MERGE_PROMPT = """Recibirás:
1. Un perfil maestro existente (JSON)
2. La transcripción de una entrevista con información adicional

Actualiza el perfil maestro incorporando la nueva información.
Mantén toda la info existente y enriquécela con los nuevos datos.
Responde SOLO con el JSON actualizado del PerfilMaestro."""


async def onboarding_interview_node(state: JoberState) -> dict:
    """Nodo LangGraph: genera la siguiente pregunta de onboarding."""
    llm = get_llm(temperature=0.5)

    system = SystemMessage(content=ONBOARDING_PROMPT)
    perfil_context = HumanMessage(
        content=f"Perfil extraído del CV:\n{state.perfil.model_dump_json(indent=2)}"
    )

    messages = [system, perfil_context] + state.messages

    response = await llm.ainvoke(messages)

    if "[ONBOARDING_COMPLETO]" in response.content:
        return {
            "messages": [response],
            "next_step": "merge_profile",
        }

    return {
        "messages": [response],
        "current_agent": "onboarding",
        "next_step": "wait_user_input",
    }


async def merge_profile_node(state: JoberState) -> dict:
    """Nodo LangGraph: fusiona respuestas del onboarding con el perfil extraído."""
    llm = get_llm(temperature=0.1)

    conversation = "\n".join(
        f"{'AI' if isinstance(m, AIMessage) else 'User'}: {m.content}"
        for m in state.messages
    )

    response = await llm.ainvoke([
        SystemMessage(content=MERGE_PROMPT),
        HumanMessage(
            content=(
                f"PERFIL ACTUAL:\n{state.perfil.model_dump_json(indent=2)}\n\n"
                f"ENTREVISTA:\n{conversation}"
            )
        ),
    ])

    try:
        clean_json = strip_markdown_fences(response.content)
        perfil = PerfilMaestro.model_validate_json(clean_json)
    except Exception:
        return {"error": "No se pudo parsear el perfil actualizado."}

    return {
        "perfil": perfil,
        "current_agent": "onboarding",
        "next_step": "save_profile",
    }
