# 🚀 Jober CLI

**Sistema autónomo multiagente LangGraph que busca, filtra y aplica a ofertas laborales 24/7 desde la terminal.**

Jober es un agente autónomo que trabaja por ti mientras duermes. Configuras tus preferencias una vez en lenguaje natural, y Jober recorre plataformas de empleo, filtra ofertas relevantes, genera CVs adaptados y aplica automáticamente — todo local, privado y sin intervención humana.

---

## ✨ Características Principales

- **Búsqueda Autónoma 24/7:** Loop continuo que recorre GetOnBrd, LinkedIn y MeetFrank buscando ofertas relevantes.
- **Entrevista de Onboarding Profunda:** El agente te hace +10 preguntas en lenguaje natural sobre cargo, habilidades, experiencia, salario, deal breakers, motivación y más.
- **Filtrado Inteligente:** Solo aplica a ofertas que cumplan tus criterios (modalidad, ubicación, habilidades must-have).
- **Tolerancia a Match Incompleto:** Entiende que puedes aplicar a trabajos donde no cumples 100% de requisitos.
- **CV y Cover Letter en PDF:** Genera documentos profesionales adaptados a cada oferta, listos para enviar.
- **Privacidad Local:** Tus datos nunca salen de `~/.jober/`. Sin cloud, sin tracking.
- **Rate Limiting Inteligente:** Controla aplicaciones/día y delays para no saturar plataformas.
- **Tracking Automático:** CSV con historial completo de todas las aplicaciones.

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

### 1. Configuración Inicial (una sola vez)

```bash
jober init
```

Esto te guiará por:
1. **Configuración de API Key** (Z.AI con GLM-4.7-flash por defecto)
2. **Análisis de tu CV** (extrae habilidades, experiencias, educación)
3. **Entrevista profunda de onboarding** — Jober te preguntará en lenguaje natural sobre:
   - ¿Qué cargo o tipo de trabajo buscas, y si estás abierto a roles similares?
   - ¿Cuántos años de experiencia tienes y a qué nivel te consideras?
   - ¿Qué herramientas/tecnologías dominas bien y cuáles estás aprendiendo?
   - ¿Qué te hace diferente de otros candidatos?
   - ¿Qué idiomas hablas y a qué nivel?
   - ¿Remoto, híbrido o presencial, y disponibilidad?
   - ¿Rango salarial mínimo e ideal?
   - ¿Tipo de empresa e industria preferida?
   - ¿Deal breakers (cosas que NO aceptas)?
   - ¿Por qué estás buscando trabajo ahora?
   - ¿Estrategia de aplicación (volumen vs precisión, match mínimo aceptable)?

### 2. Modo Autónomo (déjalo corriendo)

```bash
jober run
```

Jober entrará en un loop infinito que:
- Busca ofertas nuevas cada 5 minutos
- Filtra por tus preferencias
- Scrapea y analiza cada oferta
- Genera CV adaptado + cover letter
- Aplica automáticamente si match >= tu mínimo
- Respeta límites diarios y delays

**Presiona `Ctrl+C` para detener.**

### 3. Aplicación Manual (opcional)

```bash
jober apply "https://www.getonbrd.com/empleos/..."
```

### 4. Ver Estadísticas

```bash
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
    └── 20260323_getonbrd_Empresa_Cargo/
        ├── cv_adaptado.md         # Markdown fuente
        ├── cv_adaptado.pdf        # PDF profesional listo para enviar
        ├── cover_letter.md        # Markdown fuente
        ├── cover_letter.pdf       # PDF profesional
        ├── match_analysis.json    # Score + análisis de fit
        └── oferta_original.json   # Datos scrapeados de la oferta
```

---

## 🗺️ Roadmap

- [x] **Fase 1:** Setup CLI global + estructura base
- [x] **Fase 2:** `jober init` — Análisis de CV + onboarding conversacional de preferencias
- [x] **Fase 3:** `jober apply` — Multiagente LangGraph (scraping, análisis, adaptación CV)
- [x] **Fase 4:** `jober run` — Búsqueda autónoma continua con filtrado inteligente
- [x] **Fase 5:** Scrapers completos para LinkedIn y MeetFrank (+ GetOnBrd)
- [x] **Fase 6:** Exportación Markdown a PDF automática (via Playwright)
- [ ] **Fase 7:** Dashboard web para monitoreo en tiempo real
- [ ] **Fase 8:** Integración con email para envío automático de aplicaciones

---

## 🤝 Contribuciones

Pull requests bienvenidos. Para cambios mayores, abre un issue primero.