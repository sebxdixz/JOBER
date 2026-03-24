"""Conversational onboarding agent for job-search preferences."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from jober.core.config import get_llm
from jober.core.logging import logger
from jober.core.models import PreferenciasLaborales
from jober.core.prompts import get_prompt
from jober.core.state import JoberState, view_state
from jober.utils.llm_helpers import ainvoke_with_retry, strip_markdown_fences


async def onboarding_preferences_node(state: JoberState) -> dict:
    """Generate the next onboarding question."""
    state = view_state(state)
    llm = get_llm(temperature=0.7)
    messages = [SystemMessage(content=get_prompt("onboarding_preferences_interview")), *list(state.messages)]

    try:
        response = await ainvoke_with_retry(
            llm,
            messages,
            operation="onboarding interview question",
        )
    except Exception as exc:
        logger.exception("Onboarding interview generation failed")
        return {"error": f"No se pudo conectar con el LLM: {exc}"}

    if "[ONBOARDING_COMPLETO]" in response.content:
        response.content = response.content.replace("[ONBOARDING_COMPLETO]", "").strip()
        return {
            "messages": list(state.messages) + [response],
            "next_step": "extract_preferences",
        }

    return {
        "messages": list(state.messages) + [response],
        "current_agent": "onboarding_preferences",
        "next_step": "wait_user_input",
    }


async def extract_preferences_node(state: JoberState) -> dict:
    """Extract structured preferences from the onboarding transcript."""
    state = view_state(state)
    llm = get_llm(temperature=0.1)

    conversation = "\n".join(
        f"{'Jober' if isinstance(message, AIMessage) else 'Usuario'}: {message.content}"
        for message in state.messages
        if isinstance(message, (AIMessage, HumanMessage))
    )

    try:
        response = await ainvoke_with_retry(
            llm,
            [
                SystemMessage(content=get_prompt("onboarding_preferences_extract")),
                HumanMessage(content=f"Conversacion de onboarding:\n\n{conversation}"),
            ],
            operation="extract onboarding preferences",
        )
    except Exception as exc:
        logger.exception("Onboarding preference extraction failed")
        return {"error": f"No se pudo conectar con el LLM para extraer preferencias: {exc}"}

    try:
        clean_json = strip_markdown_fences(response.content)
        preferencias = PreferenciasLaborales.model_validate_json(clean_json)
    except Exception:
        logger.exception("Could not parse onboarding preference payload")
        return {"error": "No se pudieron extraer las preferencias de la conversacion."}

    perfil_raw = state.perfil
    if perfil_raw is not None:
        perfil_raw.preferencias = preferencias

    return {
        "perfil": perfil_raw,
        "preferencias": preferencias,
        "current_agent": "onboarding_preferences",
        "next_step": "save_profile",
    }
