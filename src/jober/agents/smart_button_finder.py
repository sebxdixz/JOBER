"""Smart button finder usando análisis de DOM y LLM.

Cuando los selectores estáticos fallan, este módulo analiza todos los botones
visibles en la página y usa el LLM para identificar cuál es el correcto.
"""

from __future__ import annotations

from playwright.async_api import Page
from langchain_core.messages import SystemMessage, HumanMessage

from jober.core.config import get_llm
from jober.core.logging import logger


BUTTON_FINDER_PROMPT = """Eres un experto en identificar botones de aplicación en páginas web de empleo.

Recibirás una lista de botones visibles en una página de LinkedIn/Indeed/etc.
Tu tarea es identificar cuál es el botón para APLICAR a la oferta de trabajo.

Botones comunes de aplicación:
- "Apply", "Easy Apply", "Solicitar", "Postular", "Postularme"
- Clases CSS: "jobs-apply-button", "apply-button", "easy-apply"
- ARIA labels con "Apply", "Solicitar", "Postular"

IMPORTANTE:
- Ignora botones de navegación ("Empleos", "Buscar", "Inicio")
- Ignora botones de login/registro si hay un botón de aplicación directo
- Si hay "Easy Apply" o "Solicitar", ese es el correcto
- Si solo hay botón de login/registro, indica que requiere autenticación

Responde SOLO con un JSON:
{
  "button_index": 5,  // índice del botón correcto (1-indexed)
  "confidence": 0.95,  // confianza 0-1
  "reason": "Botón 'Solicitar' con clases de aplicación",
  "requires_auth": false  // true si requiere login primero
}

Si NO encuentras un botón de aplicación claro:
{
  "button_index": null,
  "confidence": 0.0,
  "reason": "No hay botón de aplicación visible",
  "requires_auth": true
}"""


async def find_apply_button_smart(page: Page) -> dict[str, any]:
    """Encuentra el botón de aplicación usando análisis de DOM + LLM.
    
    Returns:
        dict con:
            - selector: str | None - Selector CSS del botón encontrado
            - index: int | None - Índice del botón en la lista
            - confidence: float - Confianza 0-1
            - requires_auth: bool - Si requiere autenticación
            - reason: str - Explicación
    """
    logger.info("Analizando DOM para encontrar botón de aplicación...")
    
    # 1. Extraer todos los botones visibles
    all_buttons = await page.locator("button").all()
    button_info = []
    
    for i, btn in enumerate(all_buttons, 1):
        try:
            is_visible = await btn.is_visible()
            if not is_visible:
                continue
            
            text = await btn.inner_text()
            aria_label = await btn.get_attribute("aria-label")
            classes = await btn.get_attribute("class")
            data_control = await btn.get_attribute("data-control-name")
            
            button_info.append({
                "index": i,
                "text": text.strip()[:100] if text else "",
                "aria_label": aria_label[:100] if aria_label else None,
                "classes": classes[:150] if classes else None,
                "data_control": data_control[:100] if data_control else None,
            })
            
            # Limitar a 30 botones para no saturar el LLM
            if len(button_info) >= 30:
                break
                
        except Exception as e:
            logger.debug(f"Error analizando botón {i}: {e}")
            continue
    
    if not button_info:
        logger.warning("No se encontraron botones visibles en la página")
        return {
            "selector": None,
            "index": None,
            "confidence": 0.0,
            "requires_auth": True,
            "reason": "No hay botones visibles en la página"
        }
    
    logger.info(f"Encontrados {len(button_info)} botones visibles, consultando LLM...")
    
    # 2. Consultar al LLM
    llm = get_llm(temperature=0.0)
    
    buttons_text = "\n".join([
        f"Botón {b['index']}:\n"
        f"  Texto: '{b['text']}'\n"
        f"  ARIA: '{b['aria_label']}'\n"
        f"  Clases: '{b['classes']}'\n"
        f"  Data-control: '{b['data_control']}'\n"
        for b in button_info
    ])
    
    try:
        response = await llm.ainvoke([
            SystemMessage(content=BUTTON_FINDER_PROMPT),
            HumanMessage(content=f"Analiza estos botones:\n\n{buttons_text}")
        ])
        
        # Parse JSON response
        import json
        from jober.utils.llm_helpers import strip_markdown_fences
        
        result = json.loads(strip_markdown_fences(response.content))
        
        button_index = result.get("button_index")
        confidence = result.get("confidence", 0.0)
        reason = result.get("reason", "")
        requires_auth = result.get("requires_auth", False)
        
        logger.info(f"LLM identificó botón {button_index} con confianza {confidence:.2f}: {reason}")
        
        # 3. Si encontró un botón, obtener su selector y guardarlo como locator
        selector = None
        target_locator = None
        if button_index and button_index <= len(all_buttons):
            try:
                # Obtener el botón por índice (ajustar a 0-indexed)
                target_btn = all_buttons[button_index - 1]
                target_locator = target_btn  # Guardar el locator directo
                
                # Intentar obtener un selector único para logging
                # Prioridad: ID > data-control > clases + texto
                btn_id = await target_btn.get_attribute("id")
                btn_text = await target_btn.inner_text()
                btn_classes = await target_btn.get_attribute("class")
                
                if btn_id:
                    selector = f"button#{btn_id}"
                else:
                    data_control = await target_btn.get_attribute("data-control-name")
                    if data_control:
                        selector = f"button[data-control-name='{data_control}']"
                    elif btn_text and len(btn_text.strip()) > 0:
                        # Usar texto + clases principales
                        main_classes = " ".join([c for c in (btn_classes or "").split() if "btn" in c or "apply" in c][:2])
                        if main_classes:
                            selector = f"button.{main_classes.replace(' ', '.')}:has-text('{btn_text.strip()[:20]}')"
                        else:
                            selector = f"button:has-text('{btn_text.strip()[:20]}')"
                    else:
                        # Último recurso: usar el locator directo sin selector
                        selector = f"<direct_locator_index_{button_index}>"
                
                logger.info(f"Selector generado: {selector}")
                
            except Exception as e:
                logger.error(f"Error generando selector para botón {button_index}: {e}")
        
        return {
            "selector": selector,
            "locator": target_locator,  # Agregar locator directo
            "index": button_index,
            "confidence": confidence,
            "requires_auth": requires_auth,
            "reason": reason
        }
        
    except Exception as e:
        logger.error(f"Error consultando LLM para identificar botón: {e}")
        return {
            "selector": None,
            "index": None,
            "confidence": 0.0,
            "requires_auth": True,
            "reason": f"Error en análisis LLM: {str(e)[:100]}"
        }


async def click_apply_button_smart(page: Page) -> tuple[bool, str]:
    """Intenta hacer clic en el botón de aplicación usando análisis inteligente.
    
    Returns:
        (success: bool, message: str)
    """
    result = await find_apply_button_smart(page)
    
    if not result["selector"]:
        if result["requires_auth"]:
            return False, "Requiere autenticación: " + result["reason"]
        return False, "No se encontró botón de aplicación: " + result["reason"]
    
    if result["confidence"] < 0.5:
        logger.warning(f"Baja confianza ({result['confidence']:.2f}) en botón identificado")
    
    # Intentar hacer clic usando el locator directo (más confiable que selector)
    try:
        locator = result.get("locator")
        
        if locator:
            # Usar el locator directo que ya tenemos
            logger.info(f"Usando locator directo para botón: {result['selector']}")
            
            try:
                await locator.scroll_into_view_if_needed(timeout=10000)
            except Exception as scroll_err:
                logger.debug(f"Scroll falló, intentando sin scroll: {scroll_err}")
            
            # Intentar clic normal primero
            try:
                await locator.click(timeout=5000)
            except Exception:
                # Si falla, intentar con force=True
                logger.debug("Clic normal falló, intentando con force=True")
                await locator.click(force=True, timeout=5000)
            
            logger.info(f"✓ Clic exitoso en botón de aplicación")
            return True, f"Botón clickeado: {result['reason']}"
        else:
            # Fallback: usar selector CSS
            logger.info(f"Intentando clic con selector CSS: {result['selector']}")
            locator = page.locator(result["selector"]).first
            
            await locator.scroll_into_view_if_needed(timeout=5000)
            await locator.click(timeout=5000)
            
            logger.info(f"✓ Clic exitoso en botón de aplicación")
            return True, f"Botón clickeado: {result['reason']}"
        
    except Exception as e:
        logger.error(f"Error haciendo clic en botón: {e}")
        return False, f"Error al hacer clic: {str(e)[:100]}"
