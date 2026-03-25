"""Universal form filler - rellena CUALQUIER formulario de aplicación usando LLM."""

from __future__ import annotations

from playwright.async_api import Page, Locator
from langchain_core.messages import SystemMessage, HumanMessage

from jober.core.config import get_llm
from jober.core.models import PerfilMaestro
from jober.core.logging import logger


FORM_ANALYZER_PROMPT = """Eres un experto en analizar formularios de aplicación de empleo.

Recibirás información sobre todos los campos de un formulario (inputs, textareas, selects, checkboxes).
Tu tarea es identificar qué información del perfil del candidato debe ir en cada campo.

INFORMACIÓN DEL CANDIDATO:
{perfil_info}

CAMPOS DEL FORMULARIO:
{campos_info}

Responde con un JSON que mapee cada campo a su valor:
{{
  "campo_1_name": "valor del perfil",
  "campo_2_name": "otro valor",
  ...
}}

REGLAS:
- Si un campo es "first name" o "nombre", usa solo el primer nombre
- Si es "last name" o "apellido", usa el resto del nombre
- Si es "email", usa el email del perfil
- Si es "phone" o "teléfono", usa el teléfono
- Si es "resume" o "cv", indica "FILE_UPLOAD"
- Si es "cover letter" o "carta", usa un resumen breve de experiencia
- Si es una pregunta específica (ej: "Why do you want to work here?"), genera una respuesta relevante basada en el perfil
- Si es un checkbox de términos/condiciones, indica "CHECKBOX_ACCEPT"
- Si no sabes qué poner, indica "SKIP"

Responde SOLO con el JSON, sin explicaciones."""


async def analyze_and_fill_form(page: Page, perfil: PerfilMaestro, cv_path = None) -> dict[str, any]:
    """Analiza y rellena CUALQUIER formulario usando LLM.
    
    Returns:
        dict con resultados del llenado
    """
    logger.info("Analizando formulario con LLM...")
    
    # 1. Extraer todos los campos del formulario
    campos = []
    
    # Inputs de texto
    text_inputs = await page.locator("input[type='text'], input[type='email'], input[type='tel'], input:not([type])").all()
    for inp in text_inputs:
        try:
            is_visible = await inp.is_visible()
            if not is_visible:
                continue
            
            name = await inp.get_attribute("name") or ""
            placeholder = await inp.get_attribute("placeholder") or ""
            label_text = ""
            
            # Intentar encontrar label asociado
            input_id = await inp.get_attribute("id")
            if input_id:
                label = page.locator(f"label[for='{input_id}']").first
                try:
                    label_text = await label.inner_text()
                except:
                    pass
            
            campos.append({
                "type": "text",
                "name": name,
                "placeholder": placeholder,
                "label": label_text,
                "locator": inp
            })
        except:
            continue
    
    # Textareas
    textareas = await page.locator("textarea").all()
    for ta in textareas:
        try:
            is_visible = await ta.is_visible()
            if not is_visible:
                continue
            
            name = await ta.get_attribute("name") or ""
            placeholder = await ta.get_attribute("placeholder") or ""
            
            campos.append({
                "type": "textarea",
                "name": name,
                "placeholder": placeholder,
                "label": "",
                "locator": ta
            })
        except:
            continue
    
    # Selects
    selects = await page.locator("select").all()
    for sel in selects:
        try:
            is_visible = await sel.is_visible()
            if not is_visible:
                continue
            
            name = await sel.get_attribute("name") or ""
            options = await sel.locator("option").all()
            option_texts = []
            for opt in options[:10]:  # Primeras 10 opciones
                text = await opt.inner_text()
                option_texts.append(text)
            
            campos.append({
                "type": "select",
                "name": name,
                "options": option_texts,
                "label": "",
                "locator": sel
            })
        except:
            continue
    
    # Checkboxes
    checkboxes = await page.locator("input[type='checkbox']").all()
    for cb in checkboxes:
        try:
            is_visible = await cb.is_visible()
            if not is_visible:
                continue
            
            name = await cb.get_attribute("name") or ""
            label_text = ""
            
            # Buscar label
            input_id = await cb.get_attribute("id")
            if input_id:
                label = page.locator(f"label[for='{input_id}']").first
                try:
                    label_text = await label.inner_text()
                except:
                    pass
            
            campos.append({
                "type": "checkbox",
                "name": name,
                "label": label_text,
                "locator": cb
            })
        except:
            continue
    
    # File inputs
    file_inputs = await page.locator("input[type='file']").all()
    for fi in file_inputs:
        try:
            name = await fi.get_attribute("name") or ""
            accept = await fi.get_attribute("accept") or ""
            
            campos.append({
                "type": "file",
                "name": name,
                "accept": accept,
                "label": "",
                "locator": fi
            })
        except:
            continue
    
    if not campos:
        logger.warning("No se encontraron campos en el formulario")
        return {"filled": 0, "total": 0}
    
    logger.info(f"Encontrados {len(campos)} campos en el formulario")
    
    # 2. Preparar información del perfil
    perfil_info = f"""
Nombre completo: {perfil.nombre}
Email: {perfil.email}
Teléfono: {perfil.telefono}
Título profesional: {perfil.titulo_profesional}
Ubicación: {perfil.ubicacion_actual}
Resumen: {perfil.resumen[:200]}
Habilidades principales: {', '.join(perfil.habilidades_tecnicas[:5])}
Experiencia reciente: {perfil.experiencias[0].cargo if perfil.experiencias else 'N/A'} en {perfil.experiencias[0].empresa if perfil.experiencias else 'N/A'}
"""
    
    # 3. Preparar información de campos
    campos_info = "\n".join([
        f"Campo {i+1}:\n"
        f"  Tipo: {c['type']}\n"
        f"  Name: '{c['name']}'\n"
        f"  Label: '{c.get('label', '')}'\n"
        f"  Placeholder: '{c.get('placeholder', '')}'\n"
        f"  Options: {c.get('options', [])}[:3] if 'options' in c else ''\n"
        for i, c in enumerate(campos[:20])  # Limitar a 20 campos
    ])
    
    # 4. Consultar LLM
    llm = get_llm(temperature=0.3)
    
    try:
        response = await llm.ainvoke([
            SystemMessage(content=FORM_ANALYZER_PROMPT.format(
                perfil_info=perfil_info,
                campos_info=campos_info
            )),
            HumanMessage(content="Analiza el formulario y genera el JSON con los valores.")
        ])
        
        import json
        from jober.utils.llm_helpers import strip_markdown_fences
        
        mapping = json.loads(strip_markdown_fences(response.content))
        
        logger.info(f"LLM generó mapeo para {len(mapping)} campos")
        
        # 5. Rellenar campos
        filled_count = 0
        
        for campo in campos:
            name = campo['name']
            value = mapping.get(name)
            
            if not value or value == "SKIP":
                continue
            
            try:
                locator = campo['locator']
                
                if campo['type'] == 'text':
                    await locator.fill(value)
                    filled_count += 1
                    logger.debug(f"Rellenado campo '{name}' con '{value[:50]}'")
                
                elif campo['type'] == 'textarea':
                    await locator.fill(value)
                    filled_count += 1
                    logger.debug(f"Rellenado textarea '{name}'")
                
                elif campo['type'] == 'select':
                    await locator.select_option(label=value)
                    filled_count += 1
                    logger.debug(f"Seleccionado '{value}' en select '{name}'")
                
                elif campo['type'] == 'checkbox' and value == "CHECKBOX_ACCEPT":
                    await locator.check()
                    filled_count += 1
                    logger.debug(f"Marcado checkbox '{name}'")
                
                elif campo['type'] == 'file' and value == "FILE_UPLOAD" and cv_path:
                    await locator.set_input_files(str(cv_path))
                    filled_count += 1
                    logger.debug(f"Subido archivo a '{name}'")
            
            except Exception as e:
                logger.warning(f"Error rellenando campo '{name}': {e}")
                continue
        
        logger.info(f"Rellenados {filled_count}/{len(campos)} campos")
        
        return {
            "filled": filled_count,
            "total": len(campos),
            "success": filled_count > 0
        }
    
    except Exception as e:
        logger.error(f"Error en análisis de formulario con LLM: {e}")
        return {"filled": 0, "total": len(campos), "success": False}


async def find_and_click_submit(page: Page) -> bool:
    """Encuentra y hace clic en el botón de submit del formulario."""
    
    submit_selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Submit')",
        "button:has-text('Send')",
        "button:has-text('Apply')",
        "button:has-text('Enviar')",
        "button:has-text('Solicitar')",
        "button:has-text('Postular')",
        "button:has-text('Continue')",
        "button:has-text('Next')",
        "button:has-text('Siguiente')",
    ]
    
    for selector in submit_selectors:
        try:
            button = page.locator(selector).first
            if await button.is_visible():
                await button.click(timeout=5000)
                logger.info(f"Clic en botón submit: {selector}")
                return True
        except:
            continue
    
    logger.warning("No se encontró botón de submit")
    return False
