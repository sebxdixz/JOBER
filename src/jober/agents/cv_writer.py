"""Agente escritor de CV — genera CV adaptado y cover letter para una oferta."""

from __future__ import annotations

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from jober.core.config import get_llm
from jober.core.models import DocumentosGenerados
from jober.core.state import JoberState
from jober.utils.llm_helpers import strip_markdown_fences


CV_SYSTEM_PROMPT = """Eres un experto en redacción de CVs profesionales.
Recibirás:
1. El perfil maestro del candidato (JSON)
2. La oferta de trabajo con sus requisitos

Genera un CV en Markdown con esta estructura EXACTA:

# [Nombre Completo]
**[Título Profesional adaptado al cargo]**

[Email] | [Teléfono] | [LinkedIn] | [GitHub]

---

## Resumen Profesional
[3-4 líneas adaptadas a la oferta, usando keywords del puesto]

## Experiencia Profesional

### [Cargo] | [Empresa]
*[Fecha inicio] - [Fecha fin]*
- [Logro cuantificable relevante para la oferta]
- [Logro cuantificable relevante]
- [Responsabilidad clave]

## Habilidades Técnicas
**[Categoría]:** skill1, skill2, skill3

## Educación
### [Título] | [Institución]
*[Años]*

## Idiomas
- [Idioma]: [Nivel]

Reglas:
- Resalta experiencias y habilidades MÁS relevantes para ESTA oferta
- Reorganiza secciones para que lo más relevante aparezca primero
- Usa keywords de la oferta de forma natural
- Máximo 2 páginas
- NO inventes información que no esté en el perfil
- Si el candidato tiene habilidades parciales, resalta lo que SÍ tiene

Responde SOLO con el CV en Markdown limpio."""


COVER_LETTER_PROMPT = """Eres un experto en redacción de cartas de presentación.
Recibirás:
1. El perfil maestro del candidato (JSON)
2. La oferta de trabajo

Genera una carta de presentación en Markdown con esta estructura:

# Carta de Presentación

**[Nombre del candidato]**
[Fecha]

---

Estimado equipo de [Empresa],

[Párrafo 1: Gancho - Por qué te interesa este puesto específico y qué aportas]

[Párrafo 2: Conexión directa entre TUS experiencias concretas y los requisitos del puesto. Menciona proyectos, tecnologías y logros específicos.]

[Párrafo 3: Valor diferencial - Qué te hace único para este rol. Habilidades blandas + técnicas complementarias.]

[Párrafo 4: Cierre - Disponibilidad, entusiasmo, llamada a la acción]

Atentamente,
**[Nombre]**

Reglas:
- Personalizada para la empresa Y el cargo (no genérica)
- Conecta experiencias concretas del perfil con requisitos de la oferta
- Profesional pero con personalidad
- NO inventes experiencias o habilidades que no estén en el perfil
- Si no cumple 100% de requisitos, enfatiza lo que SÍ cumple y la capacidad de aprender

Responde SOLO con la carta en Markdown."""


MATCH_ANALYSIS_PROMPT = """Eres un analista de fit laboral.
Recibirás:
1. El perfil maestro del candidato
2. La oferta de trabajo

Analiza el match entre candidato y oferta:
1. match_score: número entre 0.0 y 1.0
2. analisis_fit: texto breve (3-5 oraciones) explicando fortalezas y gaps

Responde en JSON exacto:
{{"match_score": 0.85, "analisis_fit": "..."}}"""


async def cv_writer_node(state: JoberState) -> dict:
    """Nodo LangGraph: genera CV adaptado, cover letter y análisis de fit."""
    llm = get_llm()

    perfil_json = state.perfil.model_dump_json(indent=2)
    oferta_json = state.oferta.model_dump_json(indent=2)
    context = f"PERFIL:\n{perfil_json}\n\nOFERTA:\n{oferta_json}"

    cv_resp, cl_resp, match_resp = await _generate_all(llm, context)

    docs = DocumentosGenerados(
        cv_adaptado_md=cv_resp,
        cover_letter_md=cl_resp,
    )

    try:
        import json
        clean_match = strip_markdown_fences(match_resp)
        match_data = json.loads(clean_match)
        docs.match_score = float(match_data.get("match_score", 0))
        docs.analisis_fit = match_data.get("analisis_fit", "")
    except Exception:
        docs.analisis_fit = match_resp

    return {
        "documentos": docs,
        "current_agent": "cv_writer",
        "next_step": "save_output",
    }


async def _generate_all(llm: ChatOpenAI, context: str) -> tuple[str, str, str]:
    """Genera CV, cover letter y match analysis secuencialmente (evita rate limits)."""
    import asyncio

    async def _call_with_retry(system: str, max_retries: int = 3) -> str:
        for attempt in range(max_retries):
            try:
                resp = await llm.ainvoke([
                    SystemMessage(content=system),
                    HumanMessage(content=context),
                ])
                return resp.content
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    wait = 5 * (attempt + 1)
                    await asyncio.sleep(wait)
                else:
                    raise
        raise RuntimeError("Max retries exceeded for LLM call")

    # Sequential to avoid rate limits
    cv_resp = await _call_with_retry(CV_SYSTEM_PROMPT)
    cl_resp = await _call_with_retry(COVER_LETTER_PROMPT)
    match_resp = await _call_with_retry(MATCH_ANALYSIS_PROMPT)

    return cv_resp, cl_resp, match_resp
