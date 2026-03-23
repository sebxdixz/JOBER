"""Test PDF export functionality."""

import asyncio
import sys
import os
from pathlib import Path

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from jober.utils.pdf_export import export_cv_to_pdf, export_cover_letter_to_pdf


SAMPLE_CV = """# Sebastián Díaz de la Fuente
**Ingeniero Civil en Informática — Especialista en IA y LLMs**

sdiazdelafuente9@gmail.com | (569) 3590 0264 | LinkedIn | GitHub

---

## Resumen Profesional

Ingeniero Civil en Informática especializado en Ingeniería de Agentes de IA y Orquestación de LLMs.
Experto en arquitecturas multi-agente cíclicas (Stateful) con LangGraph y validación estricta con Pydantic.
Enfocado en resolver problemas de indeterminación en IA mediante pipelines de evaluación (RAGs)
y despliegue escalable en Kubernetes.

## Experiencia Profesional

### Ingeniero de IA & Automatización | Grupo Axo
*Agosto 2024 - Presente*
- Diseñé sistema multi-agente con LangGraph que redujo tiempo de procesamiento documental en 40%
- Implementé pipelines RAG con ChromaDB para análisis de documentos internos
- Automatización de OCR con validación Pydantic para facturas y documentos legales
- **Stack:** Python, LangGraph, LangChain, Kubernetes, Docker, PostgreSQL

### Analista de Automatización | Walmart
*Enero 2024 - Julio 2024*
- Desarrollé scripts de automatización que ahorraron 200+ horas mensuales
- Implementé dashboards de monitoreo con React y datos en tiempo real
- **Stack:** Python, React, Power Automate, SQL Server

## Habilidades Técnicas

**IA & LLMs:** LangGraph, LangChain, RAG, Pydantic, OpenAI API, ChromaDB
**Backend:** Python, FastAPI, Django, Node.js
**DevOps:** Docker, Kubernetes, CI/CD, GitHub Actions
**Frontend:** React, TypeScript, TailwindCSS

## Educación

### Ingeniería Civil en Informática | Universidad Adolfo Ibáñez
*2020 - 2024*

## Idiomas
- Español: Nativo
- Inglés: Avanzado
"""


SAMPLE_COVER_LETTER = """# Carta de Presentación

**Sebastián Díaz de la Fuente**
23 de Marzo, 2026

---

Estimado equipo de TechCorp,

Me dirijo a ustedes con gran interés por la posición de **Ingeniero de Machine Learning** publicada
en su plataforma. Mi experiencia diseñando sistemas multi-agente con LangGraph y pipelines RAG
se alinea directamente con los desafíos técnicos que describen en la oferta.

Durante mi rol actual en Grupo Axo, he liderado la implementación de un sistema multi-agente
que redujo el tiempo de procesamiento documental en un 40%. Esto involucró arquitecturas
cíclicas con LangGraph, validación estricta con Pydantic, y despliegue en Kubernetes —
tecnologías que ustedes mencionan como core de su stack.

Lo que me diferencia es mi enfoque en resolver la indeterminación inherente a los LLMs mediante
pipelines de evaluación robustos. No solo escribo código que funciona, sino que construyo
sistemas que manejan edge cases y escalan. Además, mi experiencia tanto en backend como en
DevOps me permite entregar soluciones end-to-end.

Me encantaría conversar sobre cómo puedo aportar a los objetivos de TechCorp. Estoy disponible
para una entrevista en el momento que les resulte conveniente.

Atentamente,
**Sebastián Díaz de la Fuente**
"""


async def main():
    output_dir = Path("test_output")
    output_dir.mkdir(exist_ok=True)

    print("=== Test PDF Export ===\n")

    print("[1/2] Generando CV PDF...")
    cv_path = await export_cv_to_pdf(SAMPLE_CV, output_dir / "cv_test.pdf")
    print(f"  OK -> {cv_path} ({cv_path.stat().st_size:,} bytes)\n")

    print("[2/2] Generando Cover Letter PDF...")
    cl_path = await export_cover_letter_to_pdf(SAMPLE_COVER_LETTER, output_dir / "cover_letter_test.pdf")
    print(f"  OK -> {cl_path} ({cl_path.stat().st_size:,} bytes)\n")

    print("=== PDFs generados exitosamente ===")


if __name__ == "__main__":
    asyncio.run(main())
