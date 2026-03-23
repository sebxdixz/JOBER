# 🚀 Jober CLI

**Agente multiagente LangGraph open source que gestiona, adapta y trackea tus postulaciones laborales desde la terminal.**

Jober es una herramienta CLI que automatiza el ciclo de vida de tus postulaciones. Utiliza un sistema multiagente (LangGraph) con RAG para analizar ofertas de trabajo, cruzar requisitos con tu perfil maestro, y generar un CV adaptado, carta de presentación y respuestas a preguntas de filtrado — todo local y privado.

---

## ✨ Características Principales

- 🧠 **Onboarding Interactivo (RAG):** Sube tus CVs y Jober te hará una "entrevista" en la terminal para extraer habilidades, cubrir vacíos y crear un `perfil_maestro` hiperdetallado.
- 🔒 **Privacidad Local by Design:** Tus datos nunca tocan la nube. Todo vive en `~/.jober/`.
- 🎯 **Adaptación Inteligente:** Resalta exactamente lo que pide cada oferta, aumentando tu tasa de éxito.
- 🕸️ **Scraping Multiplataforma (Playwright):** Extrae datos de ofertas de LinkedIn, GetOnBrd y MeetFrank.
- 📊 **Tracking Automático:** CSV actualizado con empresas, cargos, fechas y estados.
- 🤖 **Multiagente LangGraph:** Orquestador central con agentes especializados (lector de CV, escritor de CV, scraper, analista).

---

## 🛠️ Instalación

```bash
git clone https://github.com/tu-usuario/jober-cli.git
cd jober-cli
pip install -e .
playwright install chromium
```

---

## 💻 Uso

```bash
# Configurar perfil (onboarding + API keys)
jober init

# Postular a una oferta
jober apply "https://www.getonbrd.com/empleos/..."

# Ver estadísticas
jober stats
```

---

## 📂 Arquitectura

### Sistema Multiagente (LangGraph)

```text
                    ┌──────────────┐
                    │ Orchestrator │
                    └──────┬───────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
   ┌───────────┐   ┌─────────────┐  ┌───────────┐
   │ CV Reader │   │ Job Scraper │  │ CV Writer │
   │  Agent    │   │   Agent     │  │  Agent    │
   └───────────┘   └─────────────┘  └───────────┘
           │               │               │
           ▼               ▼               ▼
   ┌───────────┐   ┌─────────────┐  ┌───────────┐
   │  Profile  │   │  Job Offer  │  │ Adapted   │
   │  Master   │   │  Analysis   │  │ CV + CL   │
   └───────────┘   └─────────────┘  └───────────┘
```

### Datos Locales (`~/.jober/`)

```text
~/.jober/
├── .env                       # API Keys
├── perfil_maestro.json        # Perfil generado por IA
├── cv_base/                   # PDFs originales
├── tracking_postulaciones.csv # Historial de postulaciones
└── postulaciones/
    └── 20260323_GetOnBrd_DataScientist/
        ├── cv_adaptado.pdf
        ├── cover_letter.md
        └── qa_respuestas.json
```

---

## 🗺️ Roadmap

- [ ] **Fase 1:** Setup CLI global + estructura base
- [ ] **Fase 2:** `jober init` — Agente entrevistador + RAG → Perfil Maestro
- [ ] **Fase 3:** `jober apply` — Multiagente LangGraph (análisis, adaptación CV, cover letter)
- [ ] **Fase 4:** Scrapers Playwright (GetOnBrd, MeetFrank, LinkedIn)
- [ ] **Fase 5:** Exportación Markdown → PDF

---

## 🤝 Contribuciones

Pull requests bienvenidos. Para cambios mayores, abre un issue primero.