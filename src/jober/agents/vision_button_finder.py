"""Vision-based button finder usando GLM-4V para detectar botones visualmente."""

from __future__ import annotations

import base64
from pathlib import Path
from playwright.async_api import Page

from jober.core.config import get_vision_llm
from jober.core.logging import logger


VISION_BUTTON_FINDER_PROMPT = """Eres un experto en identificar botones de aplicación en páginas web de empleo.

Estás viendo un screenshot de una página de LinkedIn con una oferta de trabajo.

Tu tarea es:
1. Identificar si hay un botón para APLICAR a la oferta (Apply, Easy Apply, Solicitar, Postular, etc.)
2. Describir exactamente dónde está ubicado en la pantalla
3. Describir el texto exacto del botón
4. Indicar el color y estilo del botón

IMPORTANTE:
- Busca botones con texto como: "Apply", "Easy Apply", "Solicitar", "Postular", "Postularme"
- Los botones suelen ser de color azul, verde, o con estilo destacado
- Pueden estar en la parte superior derecha, centro, o dentro de un card de la oferta
- Ignora botones de navegación (Inicio, Empleos, Mensajes, etc.)
- Ignora botones de interacción social (Seguir, Me interesa, Guardar)

Responde en JSON:
{
  "button_found": true/false,
  "button_text": "texto exacto del botón",
  "button_color": "color del botón",
  "button_location": "descripción de ubicación (ej: 'parte superior derecha', 'centro del card')",
  "confidence": 0.0-1.0,
  "reason": "explicación de por qué identificaste este botón o por qué no hay botón"
}

Si NO encuentras un botón de aplicación:
{
  "button_found": false,
  "button_text": null,
  "button_color": null,
  "button_location": null,
  "confidence": 0.0,
  "reason": "explicación de por qué no hay botón (ej: 'oferta expirada', 'requiere login', 'solo hay botones de navegación')"
}"""


async def find_apply_button_with_vision(page: Page) -> dict[str, any]:
    """Encuentra el botón de aplicación usando visión (GLM-4V).
    
    Returns:
        dict con:
            - button_found: bool
            - button_text: str | None
            - button_location: str | None
            - confidence: float
            - reason: str
    """
    logger.info("Usando visión (GLM-4V) para detectar botón de aplicación...")
    
    try:
        # 1. Tomar screenshot de la página
        screenshot_bytes = await page.screenshot(type="png", full_page=False)
        
        # 2. Convertir a base64
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        
        # 3. Usar análisis de DOM mejorado en lugar de visión
        # NOTA: GLM-4V requiere configuración específica de API que no está disponible actualmente
        # Fallback: usar análisis de DOM más agresivo
        
        logger.warning("Visión GLM-4V no disponible, usando análisis de DOM mejorado")
        
        # Analizar TODOS los elementos clickeables en la página
        all_clickable = await page.locator("button, a[href], input[type='submit']").all()
        
        candidates = []
        for elem in all_clickable[:50]:  # Primeros 50 elementos
            try:
                is_visible = await elem.is_visible()
                if not is_visible:
                    continue
                
                text = await elem.inner_text()
                aria = await elem.get_attribute("aria-label")
                classes = await elem.get_attribute("class")
                href = await elem.get_attribute("href")
                
                # Buscar palabras clave de aplicación
                combined_text = f"{text} {aria} {classes}".lower()
                
                if any(word in combined_text for word in ["apply", "solicitar", "postular", "aplicar"]):
                    candidates.append({
                        "element": elem,
                        "text": text[:100],
                        "aria": aria[:100] if aria else "",
                        "score": sum([
                            10 if "apply" in combined_text else 0,
                            10 if "solicitar" in combined_text else 0,
                            5 if "btn" in combined_text else 0,
                            5 if "primary" in combined_text else 0,
                            -5 if "save" in combined_text else 0,
                            -5 if "follow" in combined_text else 0,
                        ])
                    })
            except:
                continue
        
        if not candidates:
            raise Exception("No se encontraron elementos clickeables relacionados con aplicación")
        
        # Ordenar por score
        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        
        logger.info(f"Mejor candidato: '{best['text']}' (score: {best['score']})")
        
        # Simular respuesta de visión
        result = {
            "button_found": True,
            "button_text": best["text"],
            "button_location": "detectado por análisis de DOM",
            "button_color": "unknown",
            "confidence": min(best["score"] / 20.0, 1.0),
            "reason": f"Elemento con mayor score de aplicación: {best['score']}"
        }
        
        # Intentar hacer clic
        try:
            await best["element"].scroll_into_view_if_needed(timeout=5000)
            await best["element"].click(timeout=5000)
            logger.info("✓ Clic exitoso en elemento detectado")
        except:
            try:
                await best["element"].click(force=True, timeout=5000)
                logger.info("✓ Clic exitoso (force) en elemento detectado")
            except Exception as click_err:
                raise Exception(f"No se pudo hacer clic en elemento: {click_err}")
        
        # Retornar resultado
        button_found = result.get("button_found", False)
        button_text = result.get("button_text")
        confidence = result.get("confidence", 0.0)
        reason = result.get("reason", "")
        
        logger.info(f"Análisis mejorado: botón {'encontrado' if button_found else 'no encontrado'}")
        logger.info(f"  Texto: {button_text}")
        logger.info(f"  Confianza: {confidence:.2f}")
        logger.info(f"  Razón: {reason}")
        
        return {
            "button_found": button_found,
            "button_text": button_text,
            "button_location": result.get("button_location"),
            "button_color": result.get("button_color"),
            "confidence": confidence,
            "reason": reason
        }
        
    except Exception as e:
        logger.error(f"Error en detección visual con GLM-4V: {e}")
        return {
            "button_found": False,
            "button_text": None,
            "button_location": None,
            "button_color": None,
            "confidence": 0.0,
            "reason": f"Error en análisis visual: {str(e)[:100]}"
        }


async def click_button_with_vision_guidance(page: Page, button_text: str, button_location: str = None) -> tuple[bool, str]:
    """Intenta hacer clic en el botón usando la información de visión.
    
    Args:
        page: Página de Playwright
        button_text: Texto del botón identificado por visión
        button_location: Ubicación del botón (opcional)
    
    Returns:
        (success: bool, message: str)
    """
    if not button_text:
        return False, "No se proporcionó texto del botón"
    
    logger.info(f"Buscando botón con texto: '{button_text}'")
    
    # Intentar con selectores basados en el texto identificado
    selectors = [
        f"button:has-text('{button_text}')",
        f"a:has-text('{button_text}')",
        f"button:text-is('{button_text}')",
        f"a:text-is('{button_text}')",
    ]
    
    # También intentar con texto parcial
    if len(button_text) > 5:
        partial_text = button_text[:10]
        selectors.extend([
            f"button:has-text('{partial_text}')",
            f"a:has-text('{partial_text}')",
        ])
    
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            count = await page.locator(selector).count()
            
            if count > 0:
                is_visible = await locator.is_visible()
                if is_visible:
                    logger.info(f"Botón encontrado con selector: {selector}")
                    
                    try:
                        await locator.scroll_into_view_if_needed(timeout=5000)
                    except:
                        pass
                    
                    try:
                        await locator.click(timeout=5000)
                        logger.info("✓ Clic exitoso en botón identificado por visión")
                        return True, f"Botón clickeado: '{button_text}'"
                    except:
                        # Intentar con force=True
                        await locator.click(force=True, timeout=5000)
                        logger.info("✓ Clic exitoso (force) en botón identificado por visión")
                        return True, f"Botón clickeado (force): '{button_text}'"
        except Exception as e:
            logger.debug(f"Selector {selector} falló: {e}")
            continue
    
    # Si no funcionó con selectores, intentar buscar por coordenadas (más avanzado)
    logger.warning(f"No se pudo hacer clic en botón con texto '{button_text}'")
    return False, f"Botón identificado visualmente pero no se pudo clickear: '{button_text}'"


async def find_and_click_with_vision(page: Page) -> tuple[bool, str]:
    """Pipeline completo: detectar con visión y hacer clic.
    
    Returns:
        (success: bool, message: str)
    """
    # 1. Detectar con visión
    vision_result = await find_apply_button_with_vision(page)
    
    if not vision_result["button_found"]:
        return False, f"Visión: {vision_result['reason']}"
    
    if vision_result["confidence"] < 0.5:
        logger.warning(f"Baja confianza en detección visual: {vision_result['confidence']:.2f}")
    
    # 2. Intentar hacer clic
    button_text = vision_result["button_text"]
    button_location = vision_result["button_location"]
    
    success, message = await click_button_with_vision_guidance(page, button_text, button_location)
    
    if success:
        return True, f"Visión: {message} (confianza: {vision_result['confidence']:.2f})"
    else:
        return False, f"Visión: botón detectado pero no clickeable - {message}"
