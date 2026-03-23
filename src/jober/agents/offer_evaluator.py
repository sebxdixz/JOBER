"""Agente de evaluacion inicial de ofertas.

Hace un filtro barato y explicable antes de gastar LLM en CV/cover letter.
"""

from __future__ import annotations

from jober.core.state import JoberState


def _normalize_many(values: list[str]) -> list[str]:
    return [value.strip().lower() for value in values if value and value.strip()]


async def offer_evaluator_node(state: JoberState) -> dict:
    """Evalua si vale la pena continuar con la oferta."""
    perfil = state.perfil
    oferta = state.oferta
    prefs = perfil.preferencias
    notes: list[str] = []
    should_apply = True

    modalidad = (oferta.modalidad or "").strip().lower()
    modalidades = _normalize_many(prefs.modalidad)
    if modalidades and modalidad and modalidad not in modalidades:
        should_apply = False
        notes.append(f"Modalidad descartada: {oferta.modalidad}")

    ubicacion = (oferta.ubicacion or "").strip().lower()
    ubicaciones = _normalize_many(prefs.ubicaciones)
    if should_apply and ubicaciones and ubicacion:
        ubicacion_match = any(
            allowed in ubicacion or ubicacion in allowed
            for allowed in ubicaciones
        )
        if not ubicacion_match:
            should_apply = False
            notes.append(f"Ubicacion fuera de preferencia: {oferta.ubicacion}")

    titulo = (oferta.titulo or "").strip().lower()
    roles = _normalize_many(prefs.roles_deseados)
    if should_apply and roles and titulo:
        role_match = any(role in titulo for role in roles)
        if role_match:
            notes.append("Titulo alineado con roles deseados.")
        elif prefs.abierto_a_roles_similares and any(
            keyword in titulo
            for keyword in ["engineer", "developer", "analyst", "designer", "manager", "specialist"]
        ):
            notes.append("Titulo no exacto, pero parece rol similar.")
        else:
            should_apply = False
            notes.append(f"Titulo no alineado: {oferta.titulo}")

    desc_lower = (oferta.descripcion + " " + " ".join(oferta.requisitos)).lower()
    must_have = _normalize_many(prefs.habilidades_must_have)
    if should_apply and must_have:
        matched = [skill for skill in must_have if skill in desc_lower]
        if matched:
            notes.append(f"Must-have detectadas: {', '.join(matched[:5])}")
        else:
            should_apply = False
            notes.append("No aparecen habilidades must-have en la oferta.")

    return {
        "should_apply": should_apply,
        "screening_notes": notes or ["Oferta paso el filtro inicial."],
        "current_agent": "offer_evaluator",
        "next_step": "cv_writer" if should_apply else "end_filtered",
    }
