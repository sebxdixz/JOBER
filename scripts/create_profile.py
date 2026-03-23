"""Script para crear el perfil maestro sin interacción (bypass onboarding)."""

import asyncio
import sys
import os

# Fix Windows encoding
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

from jober.core.config import CV_BASE_DIR, get_llm
from jober.agents.cv_reader import extract_text_from_cvs, cv_reader_node
from jober.core.state import JoberState
from jober.utils.file_io import save_perfil_maestro


async def main():
    print("=== Jober: Creando Perfil Maestro ===\n")

    # 1. Extraer texto del CV
    print("[1/3] Extrayendo texto del CV...")
    cv_text = extract_text_from_cvs(CV_BASE_DIR)
    if not cv_text.strip():
        print("ERROR: No se pudo extraer texto del CV.")
        return
    print(f"  OK - {len(cv_text)} caracteres extraidos\n")
    print("--- Preview del CV ---")
    print(cv_text[:500])
    print("---\n")

    # 2. Analizar con LLM
    print("[2/3] Analizando CV con Z.AI (GLM-4.7-flash)...")

    from jober.core.config import get_llm
    from jober.utils.llm_helpers import strip_markdown_fences
    from jober.core.models import PerfilMaestro
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = get_llm()
    from jober.agents.cv_reader import SYSTEM_PROMPT
    response = await llm.ainvoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Analiza el siguiente CV:\n\n{cv_text}"),
    ])

    raw = response.content
    clean = strip_markdown_fences(raw)
    print(f"  Raw length: {len(raw)}, Clean length: {len(clean)}")
    print(f"  Clean JSON preview:\n{clean[:500]}\n...\n{clean[-200:]}\n")

    try:
        perfil = PerfilMaestro.model_validate_json(clean)
    except Exception as e:
        print(f"  PARSE ERROR: {e}")
        # Try with json.loads to see if it's valid JSON at all
        import json
        try:
            data = json.loads(clean)
            print(f"  JSON is valid! Keys: {list(data.keys())}")
            perfil = PerfilMaestro(**data)
        except json.JSONDecodeError as je:
            print(f"  JSON DECODE ERROR: {je}")
            return
        except Exception as pe:
            print(f"  PYDANTIC ERROR from dict: {pe}")
            return

    print(f"  OK - Perfil extraido\n")

    # 3. Guardar
    print("[3/3] Guardando perfil maestro...")
    path = save_perfil_maestro(perfil)
    print(f"  OK - Guardado en {path}\n")

    # Resumen
    print("=== Resumen del Perfil ===")
    print(f"  Nombre: {perfil.nombre}")
    print(f"  Titulo: {perfil.titulo_profesional}")
    print(f"  Habilidades tecnicas: {len(perfil.habilidades_tecnicas)}")
    print(f"  Habilidades blandas: {len(perfil.habilidades_blandas)}")
    print(f"  Experiencias: {len(perfil.experiencias)}")
    print(f"  Educacion: {len(perfil.educacion)}")
    print(f"  Idiomas: {perfil.idiomas}")


if __name__ == "__main__":
    asyncio.run(main())
