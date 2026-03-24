"""Interactive onboarding agent for completing the master profile."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from jober.core.config import get_llm
from jober.core.logging import logger
from jober.core.models import PerfilMaestro
from jober.core.prompts import get_prompt
from jober.core.state import JoberState, view_state
from jober.utils.llm_helpers import ainvoke_with_retry, strip_markdown_fences


async def onboarding_interview_node(state: JoberState) -> dict:
    """Generate the next onboarding question."""
    state = view_state(state)
    llm = get_llm(temperature=0.5)

    system = SystemMessage(content=get_prompt("onboarding_interview"))
    perfil_context = HumanMessage(
        content=f"Perfil extraido del CV:\n{state.perfil.model_dump_json(indent=2)}"
    )
    messages = [system, perfil_context] + state.messages

    try:
        response = await ainvoke_with_retry(
            llm,
            messages,
            operation="profile onboarding interview",
        )
    except Exception as exc:
        logger.exception("Profile onboarding question generation failed")
        return {"error": f"No se pudo continuar el onboarding: {exc}"}

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
    """Merge onboarding answers into the extracted profile."""
    state = view_state(state)
    llm = get_llm(temperature=0.1)

    conversation = "\n".join(
        f"{'AI' if isinstance(message, AIMessage) else 'User'}: {message.content}"
        for message in state.messages
    )

    try:
        response = await ainvoke_with_retry(
            llm,
            [
                SystemMessage(content=get_prompt("onboarding_merge_profile")),
                HumanMessage(
                    content=(
                        f"PERFIL ACTUAL:\n{state.perfil.model_dump_json(indent=2)}\n\n"
                        f"ENTREVISTA:\n{conversation}"
                    )
                ),
            ],
            operation="merge onboarding profile",
        )
    except Exception as exc:
        logger.exception("Profile merge after onboarding failed")
        return {"error": f"No se pudo fusionar el perfil: {exc}"}

    try:
        clean_json = strip_markdown_fences(response.content)
        perfil = PerfilMaestro.model_validate_json(clean_json)
    except Exception:
        logger.exception("Could not parse merged profile payload")
        return {"error": "No se pudo parsear el perfil actualizado."}

    return {
        "perfil": perfil,
        "current_agent": "onboarding",
        "next_step": "save_profile",
    }
