"""Agente de evaluacion inicial de ofertas.

Hace un filtro barato y explicable antes de gastar LLM en CV/cover letter.
"""

from __future__ import annotations

from jober.core.models import OfertaTrabajo, PerfilMaestro
from jober.core.state import JoberState


def _normalize_many(values: list[str]) -> list[str]:
    return [value.strip().lower() for value in values if value and value.strip()]


async def offer_evaluator_node(state: JoberState) -> dict:
    """Evalua si vale la pena continuar con la oferta."""
    should_apply, notes, quick_score = evaluate_offer(state.oferta, state.perfil)

    return {
        "should_apply": should_apply,
        "screening_notes": notes or ["Oferta paso el filtro inicial."],
        "current_agent": "offer_evaluator",
        "next_step": "cv_writer" if should_apply else "end_filtered",
        "documentos": {
            **state.documentos.model_dump(),
            "match_score": quick_score if not state.documentos.match_score else state.documentos.match_score,
        },
    }


def evaluate_offer(oferta: OfertaTrabajo, perfil: PerfilMaestro) -> tuple[bool, list[str], float]:
    """Evalua una oferta sin usar LLM y devuelve decision, notas y score rapido."""
    prefs = perfil.preferencias
    notes: list[str] = []
    should_apply = True
    score = 0.0

    modalidad = (oferta.modalidad or "").strip().lower()
    remote_markers = " ".join(
        [
            oferta.modalidad or "",
            oferta.ubicacion or "",
            oferta.titulo or "",
            oferta.descripcion or "",
        ]
    ).lower()
    is_remote_offer = any(marker in remote_markers for marker in ["remote", "remoto", "work from home", "anywhere"])
    modalidades = _normalize_many(prefs.modalidad)
    if modalidades and modalidad and modalidad not in modalidades:
        should_apply = False
        notes.append(f"Modalidad descartada: {oferta.modalidad}")
    elif modalidad:
        score += 0.15

    ubicacion = (oferta.ubicacion or "").strip().lower()
    ubicaciones = _normalize_many(prefs.ubicaciones)
    if should_apply and ubicaciones and ubicacion and not is_remote_offer:
        ubicacion_match = any(
            allowed in ubicacion or ubicacion in allowed
            for allowed in ubicaciones
        )
        if not ubicacion_match:
            should_apply = False
            notes.append(f"Ubicacion fuera de preferencia: {oferta.ubicacion}")
    elif should_apply and is_remote_offer:
        notes.append("Oferta detectada como remota.")
        score += 0.2
    
    # Filtrado por países (permitidos/excluidos)
    ubicacion_completa = f"{oferta.ubicacion or ''} {oferta.empresa or ''}".lower()
    
    # Verificar países excluidos
    paises_excluidos = _normalize_many(prefs.paises_excluidos)
    if should_apply and paises_excluidos:
        for pais in paises_excluidos:
            if pais in ubicacion_completa:
                should_apply = False
                notes.append(f"Pais excluido detectado: {pais}")
                break
    
    # Verificar países permitidos (solo si se especificaron)
    paises_permitidos = _normalize_many(prefs.paises_permitidos)
    if should_apply and paises_permitidos:
        pais_match = any(pais in ubicacion_completa for pais in paises_permitidos)
        tiene_remote_permitido = any(p in ["remote", "remoto"] for p in paises_permitidos)

        if is_remote_offer and tiene_remote_permitido:
            notes.append("Remote permitido aunque la ubicacion tenga pais.")
            score += 0.1
        elif not pais_match:
            should_apply = False
            notes.append(f"Pais no permitido. Ubicacion: {oferta.ubicacion}")
        else:
            score += 0.1

    titulo = (oferta.titulo or "").strip().lower()
    roles = _normalize_many(prefs.roles_deseados)
    if should_apply and roles and titulo:
        role_match = any(role in titulo for role in roles)
        if role_match:
            notes.append("Titulo alineado con roles deseados.")
            score += 0.25
        elif prefs.abierto_a_roles_similares and any(
            keyword in titulo
            for keyword in ["engineer", "developer", "analyst", "designer", "manager", "specialist"]
        ):
            notes.append("Titulo no exacto, pero parece rol similar.")
            score += 0.15
        else:
            should_apply = False
            notes.append(f"Titulo no alineado: {oferta.titulo}")

    desc_lower = (oferta.descripcion + " " + " ".join(oferta.requisitos)).lower()
    must_have = _normalize_many(prefs.habilidades_must_have)
    if should_apply and must_have:
        matched = [skill for skill in must_have if skill in desc_lower]
        if matched:
            notes.append(f"Must-have detectadas: {', '.join(matched[:5])}")
            score += min(0.3, 0.1 * len(matched))
        else:
            should_apply = False
            notes.append("No aparecen habilidades must-have en la oferta.")

    score = max(0.0, min(1.0, score))
    return should_apply, notes or ["Oferta paso el filtro inicial."], score
