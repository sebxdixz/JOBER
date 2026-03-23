"""Agente de onboarding conversacional — pregunta sobre preferencias laborales en lenguaje natural."""

from __future__ import annotations

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from jober.core.config import get_llm
from jober.core.models import PreferenciasLaborales
from jober.core.state import JoberState
from jober.utils.llm_helpers import strip_markdown_fences


ONBOARDING_PREFERENCES_PROMPT = """Eres un asistente de búsqueda de empleo amigable y conversacional.
Tu objetivo es entender las preferencias laborales del usuario para configurar un sistema de búsqueda automática.

IMPORTANTE: El usuario puede aplicar a trabajos donde NO cumple el 100% de los requisitos. Esto es normal y esperado.

Haz preguntas en lenguaje natural, una a la vez, sobre:
1. ¿Qué tipo de roles/cargos busca? (ej: "Data Scientist", "ML Engineer", "Backend Developer")
2. ¿Qué habilidades técnicas considera críticas/obligatorias para él? (must-have)
3. ¿Qué habilidades tiene pero no son obligatorias? (nice-to-have)
4. ¿Qué modalidad prefiere? (remoto, híbrido, presencial)
5. ¿Ubicaciones de interés? (ciudades, países, o "cualquier lugar remoto")
6. ¿Industrias o sectores de interés? (FinTech, HealthTech, E-commerce, etc.)
7. ¿Cuál es el match mínimo aceptable? (ej: "60% está bien", "prefiero 70%+")
8. ¿Cuántas aplicaciones por día como máximo? (para no saturar)

Sé conversacional, no hagas una entrevista formal. Adapta las preguntas según las respuestas previas.
Cuando tengas suficiente información, responde exactamente: [ONBOARDING_PREFERENCES_COMPLETO]

Habla en español, sé amigable y empático."""


EXTRACT_PREFERENCES_PROMPT = """Recibirás una conversación donde un usuario describió sus preferencias laborales.

Extrae la información y devuelve un JSON que siga el schema de PreferenciasLaborales:
{{
    "roles_deseados": ["rol1", "rol2"],
    "industrias_preferidas": ["industria1"],
    "modalidad": ["remoto", "hibrido"],
    "ubicaciones": ["ciudad1", "Remote"],
    "min_match_score": 0.6,
    "aplicar_sin_100_requisitos": true,
    "habilidades_must_have": ["skill1", "skill2"],
    "habilidades_nice_to_have": ["skill3"],
    "plataformas_activas": ["getonbrd", "linkedin", "meetfrank"],
    "max_aplicaciones_por_dia": 10,
    "delay_entre_aplicaciones_segundos": 60
}}

Si algo no se mencionó, usa valores razonables por defecto.
Responde SOLO con el JSON válido."""


async def onboarding_preferences_node(state: JoberState) -> dict:
    """Nodo LangGraph: genera la siguiente pregunta de onboarding de preferencias."""
    llm = get_llm(temperature=0.7)

    system = SystemMessage(content=ONBOARDING_PREFERENCES_PROMPT)
    messages = [system] + state.messages

    response = await llm.ainvoke(messages)

    if "[ONBOARDING_PREFERENCES_COMPLETO]" in response.content:
        return {
            "messages": [response],
            "next_step": "extract_preferences",
        }

    return {
        "messages": [response],
        "current_agent": "onboarding_preferences",
        "next_step": "wait_user_input",
    }


async def extract_preferences_node(state: JoberState) -> dict:
    """Nodo LangGraph: extrae PreferenciasLaborales de la conversación."""
    llm = get_llm(temperature=0.1)

    conversation = "\n".join(
        f"{'AI' if isinstance(m, AIMessage) else 'User'}: {m.content}"
        for m in state.messages
    )

    response = await llm.ainvoke([
        SystemMessage(content=EXTRACT_PREFERENCES_PROMPT),
        HumanMessage(content=f"Conversación:\n{conversation}"),
    ])

    try:
        clean_json = strip_markdown_fences(response.content)
        preferencias = PreferenciasLaborales.model_validate_json(clean_json)
    except Exception:
        return {"error": "No se pudieron extraer las preferencias de la conversación."}

    # Actualizar el perfil con las preferencias
    perfil = state.perfil
    perfil.preferencias = preferencias

    return {
        "perfil": perfil,
        "current_agent": "onboarding_preferences",
        "next_step": "save_profile",
    }
