"""Initial offer evaluation agent.

Runs a cheap and explainable filter before spending LLM tokens.
"""

from __future__ import annotations

import re

from jober.core.models import OfertaTrabajo, PerfilMaestro
from jober.core.state import JoberState, view_state


def _normalize_many(values: list[str]) -> list[str]:
    return [value.strip().lower() for value in values if value and value.strip()]


def _contains_exact_term(text: str, term: str) -> bool:
    blob = (text or "").lower()
    target = (term or "").strip().lower()
    if not blob.strip() or not target:
        return False
    pattern = rf"(?<!\w){re.escape(target)}(?!\w)"
    return re.search(pattern, blob, flags=re.IGNORECASE) is not None


def _ai_intent(prefs_roles: list[str]) -> bool:
    markers = ["ai", "llm", "ml", "machine learning", "mlops", "mlo"]
    return any(marker in role.lower() for role in prefs_roles for marker in markers)


def _has_ai_keywords(text: str) -> bool:
    blob = text.lower()
    if not blob.strip():
        return False

    keyword_phrases = [
        "machine learning",
        "mlops",
        "mlo",
        "llm",
        "generative ai",
        "genai",
        "artificial intelligence",
        "data science",
        "data scientist",
        "ai engineer",
        "ml engineer",
        "nlp",
        "rag",
    ]
    if any(phrase in blob for phrase in keyword_phrases):
        return True

    if re.search(r"\bai\b", blob) or re.search(r"\bml\b", blob):
        return True

    return False


def _remote_only_required(modalidades: list[str]) -> bool:
    normalized = [value.strip().lower() for value in modalidades if value and value.strip()]
    if not normalized:
        return False
    remote_markers = {"remoto", "remote", "work from home"}
    has_remote = any(marker in modality for modality in normalized for marker in remote_markers)
    has_onsite = any(marker in modality for modality in normalized for marker in ["presencial", "onsite"])
    has_hybrid = any(marker in modality for modality in normalized for marker in ["hibrido", "hybrid"])
    return has_remote and not (has_onsite or has_hybrid)


def _seniority_level_from_text(text: str) -> int:
    """Heuristic seniority scale: 0=intern,1=junior,2=mid,3=senior,4=lead/staff,5=director."""
    blob = text.lower()
    if not blob.strip():
        return -1
    if any(tok in blob for tok in ["intern", "trainee", "practicante", "pasante"]):
        return 0
    if any(tok in blob for tok in ["junior", "jr", "jr.", "entry level", "entry-level"]):
        return 1
    if any(tok in blob for tok in ["semi senior", "semi-senior", "ssr", "mid", "mid-level", "associate"]):
        return 2
    if any(tok in blob for tok in ["senior", "sr", "sr."]):
        return 3
    if any(tok in blob for tok in ["lead", "staff", "principal", "tech lead", "architect", "arquitecto"]):
        return 4
    if any(tok in blob for tok in ["head", "director", "vp", "chief"]):
        return 5
    return -1


def _seniority_level_from_pref(level: str) -> int:
    blob = (level or "").lower()
    if any(tok in blob for tok in ["intern", "trainee", "practicante", "pasante"]):
        return 0
    if any(tok in blob for tok in ["junior", "jr", "entry"]):
        return 1
    if any(tok in blob for tok in ["mid", "semi", "ssr", "associate"]):
        return 2
    if "senior" in blob or "sr" in blob:
        return 3
    if any(tok in blob for tok in ["lead", "staff", "principal"]):
        return 4
    if any(tok in blob for tok in ["head", "director", "vp", "chief"]):
        return 5
    return -1


def _extract_years_required(text: str) -> int | None:
    blob = text.lower()
    if not blob.strip():
        return None
    patterns = [
        r"(\d{1,2})\s*\+?\s*(?:years|year)",
        r"(\d{1,2})\s*\+?\s*(?:anos|años)",
    ]
    years = []
    for pattern in patterns:
        for match in re.findall(pattern, blob):
            try:
                value = int(match)
            except Exception:
                continue
            if 0 < value < 30:
                years.append(value)
    return max(years) if years else None


def _build_role_keywords(roles: list[str]) -> list[str]:
    base = [role.strip() for role in roles if role and role.strip()]
    expanded: list[str] = []

    role_map = {
        "ai engineer": ["ai engineer", "artificial intelligence", "ai"],
        "llm engineer": ["llm engineer", "llm", "generative ai", "genai"],
        "ml engineer": ["ml engineer", "machine learning engineer", "machine learning"],
        "mlops engineer": ["mlops", "ml ops", "ml platform"],
        "ai ops": ["ai ops", "aiops", "mlops"],
        "llm ops": ["llm ops", "llmops", "mlops"],
        "data scientist": ["data scientist", "data science", "applied scientist", "ml scientist"],
        "data analyst": ["data analyst", "analytics", "bi analyst", "business analyst"],
        "data engineer": ["data engineer", "data engineering"],
    }

    for role in base:
        role_lower = role.lower()
        if role_lower in role_map:
            expanded.extend(role_map[role_lower])
        else:
            expanded.append(role_lower)

    seen: set[str] = set()
    keywords: list[str] = []
    for kw in expanded:
        key = kw.lower()
        if key not in seen:
            seen.add(key)
            keywords.append(key)
    return keywords


def _has_any_keyword(text: str, keywords: list[str]) -> bool:
    return any(_contains_exact_term(text, keyword) for keyword in keywords if keyword)


def _has_obviously_bad_title(title: str) -> bool:
    blob = (title or "").lower()
    blocked = [
        "recruiter",
        "talent acquisition",
        "sales",
        "account executive",
        "business development",
        "customer support",
        "customer success",
        "marketing",
        "seo",
        "designer",
        "ux/ui",
        "qa tester",
        "manual tester",
        "dispatcher",
        "call center",
    ]
    return any(term in blob for term in blocked)


def _has_conflicting_title_family(title: str, roles: list[str]) -> bool:
    blob = (title or "").lower()
    roles_blob = " ".join(role.lower() for role in roles)
    conflicts = [
        ("architect", "architect"),
        ("arquitecto", "architect"),
        ("manager", "manager"),
        ("director", "director"),
        ("head of", "head"),
        ("product owner", "product"),
        ("scrum master", "scrum"),
    ]
    for term, family in conflicts:
        if term in blob and family not in roles_blob:
            return True
    return False


def _build_title_role_keywords(roles: list[str]) -> list[str]:
    role_map = {
        "ai engineer": ["ai engineer", "agentic ai engineer", "generative ai engineer"],
        "llm engineer": ["llm engineer", "prompt engineer", "genai engineer"],
        "ml engineer": ["ml engineer", "machine learning engineer", "applied ml engineer"],
        "mlops engineer": ["mlops engineer", "ml platform engineer", "machine learning ops"],
        "ai ops": ["ai ops", "aiops", "ai platform engineer"],
        "llm ops": ["llm ops", "llmops", "llm platform engineer"],
        "ai automation engineer": ["ai automation engineer", "automation engineer", "intelligent automation engineer"],
        "machine learning engineer": ["machine learning engineer", "ml engineer", "applied ml engineer"],
        "data scientist": ["data scientist", "applied scientist", "ml scientist"],
        "data analyst": ["data analyst", "bi analyst", "business intelligence analyst", "analytics engineer"],
        "data engineer": ["data engineer", "data platform engineer", "analytics engineer"],
    }

    seen: set[str] = set()
    keywords: list[str] = []
    for role in roles:
        role_lower = role.lower().strip()
        variants = role_map.get(role_lower, [role_lower])
        for variant in variants:
            if variant not in seen:
                seen.add(variant)
                keywords.append(variant)
    return keywords


def _seniority_is_too_high(user_level: int, offer_level: int) -> bool:
    if user_level < 0 or offer_level < 0:
        return False
    return offer_level > user_level


def evaluate_offer_for_scout(oferta: OfertaTrabajo, perfil: PerfilMaestro) -> tuple[bool, list[str], float]:
    """Wide scouting filter: maximize coverage while enforcing hard constraints."""
    prefs = perfil.preferencias
    notes: list[str] = []
    score = 0.0

    title = (oferta.titulo or "").strip()
    description = (oferta.descripcion or "").strip()
    blob = f"{title} {description} {' '.join(oferta.requisitos or [])}".lower()

    if _has_obviously_bad_title(title):
        return False, ["Titulo descartado por irrelevancia obvia."], 0.0
    if _has_conflicting_title_family(title, prefs.roles_deseados):
        return False, ["Familia de cargo fuera de foco para tu perfil."], 0.0

    modalidades = _normalize_many(prefs.modalidad)
    remote_markers = " ".join(
        [oferta.modalidad or "", oferta.ubicacion or "", oferta.titulo or "", oferta.descripcion or ""]
    ).lower()
    is_remote_offer = any(marker in remote_markers for marker in ["remote", "remoto", "work from home", "anywhere"])

    if _remote_only_required(modalidades):
        if not is_remote_offer:
            return False, ["Solo remoto: la oferta no parece remota."], 0.0
        score += 0.3
        notes.append("Oferta remota.")
    elif is_remote_offer:
        score += 0.15
        notes.append("Oferta detectada como remota.")

    title_role_keywords = _build_title_role_keywords(prefs.roles_deseados)
    role_keywords = _build_role_keywords(prefs.roles_deseados)
    if title_role_keywords:
        title_match = _has_any_keyword(title, title_role_keywords)
        blob_match = _has_any_keyword(blob, role_keywords)
        if title_match:
            score += 0.45
            notes.append("Titulo relacionado con roles deseados.")
        elif blob_match and any(term in title.lower() for term in ["engineer", "scientist", "analyst", "mlops", "ai", "llm", "data"]):
            score += 0.2
            notes.append("Descripcion relacionada con roles deseados.")
        else:
            return False, ["No coincide con tus familias de cargo."], 0.0

    user_level = _seniority_level_from_pref(prefs.nivel_experiencia)
    offer_level = _seniority_level_from_text(title)
    if user_level >= 0 and offer_level >= 0:
        if _seniority_is_too_high(user_level, offer_level):
            return False, ["Seniority superior a tu nivel objetivo actual."], 0.0
        score += 0.1
        notes.append("Senioridad compatible.")

    if _ai_intent(prefs.roles_deseados) and _has_ai_keywords(blob):
        score += 0.15
        notes.append("Keywords AI/ML detectadas.")

    score = max(0.0, min(1.0, score))
    return True, notes or ["Oferta potencialmente relevante."], score


async def offer_evaluator_node(state: JoberState) -> dict:
    """Evaluate whether the offer should continue through the pipeline."""
    state = view_state(state)
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
    """Evaluate an offer without using the LLM."""
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
    if should_apply and _remote_only_required(modalidades) and not is_remote_offer:
        should_apply = False
        notes.append("Solo remoto: oferta no indica modalidad remota.")
    elif modalidades and modalidad and modalidad not in modalidades:
        should_apply = False
        notes.append(f"Modalidad descartada: {oferta.modalidad}")
    elif modalidad:
        score += 0.15

    ubicacion = (oferta.ubicacion or "").strip().lower()
    ubicaciones = _normalize_many(prefs.ubicaciones)
    if should_apply and ubicaciones and ubicacion and not is_remote_offer:
        ubicacion_match = any(allowed in ubicacion or ubicacion in allowed for allowed in ubicaciones)
        if not ubicacion_match:
            should_apply = False
            notes.append(f"Ubicacion fuera de preferencia: {oferta.ubicacion}")
    elif should_apply and is_remote_offer:
        notes.append("Oferta detectada como remota.")
        score += 0.2

    ubicacion_completa = f"{oferta.ubicacion or ''} {oferta.empresa or ''}".lower()
    paises_excluidos = _normalize_many(prefs.paises_excluidos)
    if should_apply and paises_excluidos:
        for pais in paises_excluidos:
            if pais in ubicacion_completa:
                should_apply = False
                notes.append(f"Pais excluido detectado: {pais}")
                break

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
        role_match = any(_contains_exact_term(titulo, role) for role in roles)
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
            if prefs.abierto_a_roles_similares:
                notes.append(f"Titulo no alineado, pero se permite explorar: {oferta.titulo}")
                score += 0.05
            else:
                should_apply = False
                notes.append(f"Titulo no alineado: {oferta.titulo}")

    desc_lower = (oferta.descripcion + " " + " ".join(oferta.requisitos)).lower()
    role_keywords = _build_role_keywords(prefs.roles_deseados)
    if should_apply and role_keywords:
        blob = f"{titulo} {desc_lower}"
        if not any(_contains_exact_term(blob, keyword) for keyword in role_keywords):
            should_apply = False
            notes.append("No coincide con roles deseados.")

    user_level = _seniority_level_from_pref(prefs.nivel_experiencia)
    offer_level = _seniority_level_from_text(f"{oferta.titulo} {desc_lower}")
    if should_apply and offer_level >= 0 and user_level >= 0:
        if _seniority_is_too_high(user_level, offer_level):
            should_apply = False
            notes.append("Oferta por encima de tu seniority objetivo actual.")
        else:
            score += 0.1
            notes.append("Senioridad compatible con tu nivel.")

    years_required = _extract_years_required(f"{oferta.titulo} {desc_lower}")
    if should_apply and years_required is not None and prefs.anos_experiencia:
        max_allowed = prefs.anos_experiencia + max(prefs.max_anos_experiencia_extra, 0)
        if years_required > max_allowed:
            should_apply = False
            notes.append(
                f"Requiere {years_required} anos (tu max permitido: {max_allowed})."
            )
        else:
            score += 0.05
            notes.append("Requisito de experiencia dentro del rango permitido.")

    if should_apply and _ai_intent(prefs.roles_deseados):
        if not _has_ai_keywords(titulo + " " + desc_lower):
            should_apply = False
            notes.append("Oferta sin keywords AI/ML relevantes para tu perfil.")

    must_have = _normalize_many(prefs.habilidades_must_have)
    if should_apply and must_have:
        if not desc_lower.strip():
            notes.append("Oferta sin descripcion clara; no se valida must-have.")
        else:
            matched = []
            for skill in must_have:
                pattern = r"\b" + re.escape(skill) + r"\b"
                if re.search(pattern, desc_lower, flags=re.IGNORECASE):
                    matched.append(skill)
            if matched:
                notes.append(f"Must-have detectadas: {', '.join(matched[:5])}")
                score += min(0.3, 0.1 * len(matched))
            else:
                if prefs.aplicar_sin_100_requisitos:
                    notes.append("No aparecen must-have, pero se permite explorar.")
                    score = max(0.0, score - 0.05)
                else:
                    should_apply = False
                    notes.append("No aparecen habilidades must-have en la oferta.")

    score = max(0.0, min(1.0, score))
    return should_apply, notes or ["Oferta paso el filtro inicial."], score
