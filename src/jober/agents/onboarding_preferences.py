"""Agente de onboarding conversacional — entrevista profunda sobre preferencias laborales.

Diseñado para ser usado por CUALQUIER persona, no solo un perfil técnico.
Hace muchas preguntas en lenguaje natural antes de arrancar la búsqueda autónoma.
"""

from __future__ import annotations

import asyncio

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from jober.core.config import get_llm
from jober.core.models import PreferenciasLaborales
from jober.core.state import JoberState
from jober.utils.llm_helpers import strip_markdown_fences


# ──────────────────────────────────────────────────────────────────────────────
# Prompt principal de entrevista
# ──────────────────────────────────────────────────────────────────────────────

ONBOARDING_SYSTEM_PROMPT = """Eres un coach de carrera amigable y empático. Tu trabajo es hacer una
entrevista profunda al usuario para entender EXACTAMENTE qué trabajo busca, qué sabe hacer,
qué le falta, y qué condiciones necesita. Esta información se usará para buscar y aplicar a
trabajos automáticamente, así que necesitas ser MUY detallado.

El usuario puede ser CUALQUIER persona: un ingeniero senior, un recién egresado, un diseñador,
un contador, un chef, un vendedor. Adapta tu lenguaje y preguntas a su perfil.

REGLAS:
- Haz UNA pregunta a la vez. No hagas listas de preguntas.
- Sé conversacional, no suenes como un formulario. Reacciona a lo que dice.
- Si da respuestas cortas, profundiza con follow-ups.
- Si da respuestas largas, resume lo que entendiste y confirma.
- NO juzgues ni corrijas. Si dice "sé un poco de Python", no digas "deberías saber más".
- Normaliza que la gente aplica a trabajos donde no cumple el 100% de requisitos.
- Habla en español. Sé cálido pero profesional.

TEMAS QUE DEBES CUBRIR (en orden natural, no rígido):

1. CARGO Y DIRECCIÓN PROFESIONAL
   - ¿Qué cargo o tipo de trabajo está buscando?
   - ¿Tiene un título específico en mente o está abierto a roles similares?
   - ¿Hay algún cargo que le interese aunque no tenga toda la experiencia?

2. EXPERIENCIA Y NIVEL
   - ¿Cuántos años de experiencia tiene en este área?
   - ¿Se considera junior, mid-level, senior, o no sabe?
   - ¿Ha tenido alguna experiencia laboral relevante? (aunque sea informal, freelance, prácticas)
   - ¿Qué es lo más destacado que ha logrado profesionalmente?

3. HABILIDADES TÉCNICAS (adaptar al rubro)
   - ¿Qué herramientas/tecnologías/software domina bien?
   - ¿Qué está aprendiendo o conoce a nivel básico?
   - ¿Hay alguna habilidad que SIEMPRE le piden y no tiene?
   - ¿Qué habilidades cree que son su fuerte?

4. HABILIDADES BLANDAS Y DIFERENCIAL
   - ¿Qué cree que lo hace diferente de otros candidatos?
   - ¿Cómo trabaja en equipo? ¿Lidera, colabora, prefiere autonomía?
   - ¿Hay algo que siempre le destacan en evaluaciones o feedback?

5. IDIOMAS
   - ¿Qué idiomas habla y a qué nivel?
   - ¿Podría trabajar en inglés? (reuniones, documentación, etc.)

6. CONDICIONES DE TRABAJO
   - ¿Remoto, híbrido o presencial? ¿Hay flexibilidad?
   - ¿Dónde vive? ¿Está dispuesto a reubicarse?
   - ¿Full-time, part-time, freelance, contrato?
   - ¿Disponibilidad inmediata o necesita tiempo?

7. EXPECTATIVAS SALARIALES
   - ¿Tiene un rango salarial en mente? (mínimo y ideal)
   - ¿En qué moneda?
   - ¿Es negociable si el proyecto es interesante?

8. TIPO DE EMPRESA E INDUSTRIA
   - ¿Startup, corporativo, pyme, gobierno?
   - ¿Alguna industria que le interese especialmente?
   - ¿Alguna industria que DESCARTE?

9. DEAL BREAKERS
   - ¿Hay algo que sea inaceptable para él? (ej: "no presencial", "no sin sueldo", "no más de X horas")
   - ¿Algo que haya rechazado en trabajos anteriores?

10. MOTIVACIÓN Y CONTEXTO
    - ¿Por qué está buscando trabajo ahora? (primer empleo, cambio, crecimiento, despido, etc.)
    - ¿Hay algo que quiera que el sistema sepa sobre su situación?

11. ESTRATEGIA DE APLICACIÓN
    - ¿Prefiere aplicar a muchos trabajos (volumen) o solo a los que calzan perfecto?
    - ¿Aplicaría a un trabajo donde cumple 60-70% de requisitos? ¿O solo 80%+?
    - ¿Cuántas aplicaciones por día le parecen razonables?

CUANDO HAYAS CUBIERTO TODOS LOS TEMAS (no antes), haz un RESUMEN de todo lo que
entendiste y pide confirmación. Si el usuario confirma, termina con exactamente:
[ONBOARDING_COMPLETO]

NO termines antes de cubrir todos los temas. Si el usuario quiere saltarse algo, respeta
su decisión pero al menos pregunta por los temas críticos (cargo, habilidades, experiencia,
condiciones, salario)."""


# ──────────────────────────────────────────────────────────────────────────────
# Prompt de extracción
# ──────────────────────────────────────────────────────────────────────────────

EXTRACT_PREFERENCES_PROMPT = """Recibirás una conversación completa donde un usuario describió sus
preferencias laborales durante una entrevista de onboarding.

Extrae TODA la información y devuelve un JSON con este schema exacto:
{{
    "roles_deseados": ["rol1", "rol2"],
    "nivel_experiencia": "junior|mid|senior|lead",
    "anos_experiencia": 3,
    "resumen_candidato": "Frase que resume su perfil profesional",

    "habilidades_dominadas": ["skill que domina 1", "skill que domina 2"],
    "habilidades_en_aprendizaje": ["skill básico 1"],
    "habilidades_must_have": ["skill crítico para él"],
    "habilidades_nice_to_have": ["skill deseable"],
    "herramientas_y_tecnologias": ["herramienta1", "framework2"],

    "industrias_preferidas": ["industria1"],
    "tipo_empresa": ["startup", "corporativo"],
    "modalidad": ["remoto", "hibrido"],
    "ubicaciones": ["ciudad1", "Remote"],
    "disponibilidad": "inmediata",
    "jornada": "full-time",

    "salario_minimo": "$X",
    "salario_ideal": "$Y",
    "moneda_preferida": "USD|CLP|EUR|etc",
    "acepta_negociar_salario": true,

    "min_match_score": 0.55,
    "aplicar_sin_100_requisitos": true,
    "max_anos_experiencia_extra": 2,
    "abierto_a_roles_similares": true,

    "deal_breakers": ["cosa inaceptable 1"],
    "idiomas_requeridos": ["Español - Nativo", "Inglés - Avanzado"],

    "motivacion": "Por qué busca trabajo",
    "fortalezas_clave": ["fortaleza 1"],
    "areas_mejora": ["área de mejora 1"],

    "plataformas_activas": ["getonbrd", "linkedin", "meetfrank"],
    "max_aplicaciones_por_dia": 10,
    "delay_entre_aplicaciones_segundos": 60
}}

REGLAS:
- Extrae SOLO lo que el usuario mencionó explícitamente.
- Si algo no se mencionó, usa valores razonables por defecto basados en el contexto.
- Para nivel_experiencia, inférelo de los años y tipo de cargos mencionados.
- Para min_match_score, si dijo "aplico aunque no cumpla todo" usa 0.55; si dijo "solo los que calzo" usa 0.75.
- Responde SOLO con el JSON válido, sin texto adicional."""


# ──────────────────────────────────────────────────────────────────────────────
# Nodos LangGraph
# ──────────────────────────────────────────────────────────────────────────────

async def onboarding_preferences_node(state) -> dict:
    """Nodo LangGraph: genera la siguiente pregunta de la entrevista de onboarding."""
    llm = get_llm(temperature=0.7)

    # Construir mensajes: system + historial completo
    messages_raw = state.get("messages", []) if isinstance(state, dict) else state.messages
    system = SystemMessage(content=ONBOARDING_SYSTEM_PROMPT)
    messages = [system] + list(messages_raw)

    # Retry para rate limits
    for attempt in range(3):
        try:
            response = await llm.ainvoke(messages)
            break
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                await asyncio.sleep(5 * (attempt + 1))
            else:
                raise
    else:
        return {"error": "No se pudo conectar con el LLM."}

    if "[ONBOARDING_COMPLETO]" in response.content:
        # Limpiar el marcador del mensaje que se muestra al usuario
        clean_content = response.content.replace("[ONBOARDING_COMPLETO]", "").strip()
        response.content = clean_content
        return {
            "messages": list(messages_raw) + [response],
            "next_step": "extract_preferences",
        }

    return {
        "messages": list(messages_raw) + [response],
        "current_agent": "onboarding_preferences",
        "next_step": "wait_user_input",
    }


async def extract_preferences_node(state) -> dict:
    """Nodo LangGraph: extrae PreferenciasLaborales de toda la conversación."""
    llm = get_llm(temperature=0.1)

    messages_raw = state.get("messages", []) if isinstance(state, dict) else state.messages

    conversation = "\n".join(
        f"{'Jober' if isinstance(m, AIMessage) else 'Usuario'}: {m.content}"
        for m in messages_raw
        if isinstance(m, (AIMessage, HumanMessage))
    )

    # Retry para rate limits
    for attempt in range(3):
        try:
            response = await llm.ainvoke([
                SystemMessage(content=EXTRACT_PREFERENCES_PROMPT),
                HumanMessage(content=f"Conversación de onboarding:\n\n{conversation}"),
            ])
            break
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                await asyncio.sleep(5 * (attempt + 1))
            else:
                raise
    else:
        return {"error": "No se pudo conectar con el LLM para extraer preferencias."}

    try:
        clean_json = strip_markdown_fences(response.content)
        preferencias = PreferenciasLaborales.model_validate_json(clean_json)
    except Exception:
        return {"error": "No se pudieron extraer las preferencias de la conversación."}

    # Actualizar perfil con las preferencias
    perfil_raw = state.get("perfil") if isinstance(state, dict) else state.perfil
    if perfil_raw is not None:
        perfil_raw.preferencias = preferencias

    return {
        "perfil": perfil_raw,
        "preferencias": preferencias,
        "current_agent": "onboarding_preferences",
        "next_step": "save_profile",
    }
