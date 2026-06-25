# Guardrails para Desarrollo con IA — CienaNet Bot

Este documento define las reglas que la IA debe seguir al generar código para este proyecto. Es vinculante para cualquier asistente de IA que trabaje en este repositorio.

---

## LO QUE LA IA DEBE HACER

### Código
- **Usar tipado estático siempre**: Pydantic models para request/response, type hints en todas las funciones
- **Manejar errores explícitamente**: nunca ignorar excepciones silenciosamente; siempre loggear y responder con status HTTP apropiado
- **Validar inputs en el borde**: toda data externa (webhooks Meta, datos de sensores) se valida con Pydantic antes de tocar lógica de negocio
- **Escribir tests para funcionalidades críticas**: webhook handler, ingesta de sensores, formateo de respuestas WhatsApp
- **Código en inglés, comentarios técnicos en inglés**: las respuestas al pescador sí van en español
- **Un archivo = una responsabilidad**: routers, services, models y schemas en módulos separados

### Seguridad (obligatorio, nunca negociar)
- **Validar firma HMAC en cada webhook de Meta** antes de procesar cualquier payload
- **Nunca loggear** tokens, API keys, números de teléfono completos, ni contenido de mensajes de usuarios
- **Variables sensibles solo en `.env`**, nunca hardcodeadas, nunca en comentarios de código
- **Hashear API keys de sensores** antes de guardar en DB (usar bcrypt o PBKDF2)
- **Sanitizar** cualquier input antes de insertar en queries SQL
- **Principio de mínimo privilegio** en credenciales de Supabase: usar service role solo donde necesario

### Respuestas a pescadores
- **Lenguaje simple**: máximo nivel de escolaridad primaria en los mensajes
- **Mensajes cortos**: WhatsApp no es un ensayo; máximo 3-4 oraciones por mensaje
- **Sin jerga técnica**: "el agua está salada" no "la conductividad eléctrica supera 35 mS/cm"
- **Siempre ofrecer acción concreta**: al final de cada respuesta informativa, dar una recomendación de qué hacer
- **No dar información sin base en datos reales**: no inventar lecturas de sensores

---

## LO QUE LA IA NO DEBE HACER

### Código
- ❌ Generar código sin manejo de errores ("happy path only")
- ❌ Usar `print()` para debugging — usar `logging` con niveles apropiados
- ❌ Crear endpoints sin validación de autenticación
- ❌ Instalar dependencias no listadas en `STACK.md` sin justificarlo
- ❌ Usar `*` en imports de SQLAlchemy o cualquier módulo
- ❌ Crear archivos de más de 300 líneas — si pasa, refactorizar en módulos
- ❌ Generar migraciones de DB sin revisar el schema existente primero
- ❌ Usar `eval()`, `exec()`, o ejecución dinámica de código

### Arquitectura
- ❌ Mezclar lógica de negocio en los routers de FastAPI — eso va en services
- ❌ Hacer llamadas directas a DB desde los routers
- ❌ Crear dependencias circulares entre módulos
- ❌ Romper el flujo de validación HMAC de Meta bajo ningún pretexto

### Respuestas a usuarios
- ❌ Inventar datos ambientales si los sensores no están disponibles
- ❌ Prometer funcionalidades que el sistema no tiene aún
- ❌ Generar respuestas en inglés para los pescadores
- ❌ Usar emojis técnicos (📊, 🔬) — sí usar emojis simples y familiares (🐟, ☀️, 🌊)

---

## GUÍA DE REVISIÓN DE CÓDIGO GENERADO POR IA

Antes de hacer commit de código generado por IA, verificar:

```
[ ] ¿Todos los inputs externos están validados con Pydantic?
[ ] ¿El webhook de Meta valida la firma HMAC antes de procesar?
[ ] ¿Hay manejo de errores para cada llamada externa (Meta API, Supabase, Claude)?
[ ] ¿No hay credenciales hardcodeadas?
[ ] ¿El código tiene type hints?
[ ] ¿Los tests cubren el happy path Y los casos de error?
[ ] ¿Los logs no exponen datos de usuarios?
[ ] ¿El código sigue la estructura de carpetas del proyecto?
```

---

## CONTEXTO SENSIBLE

Este proyecto trabaja con una comunidad vulnerable. La IA debe tener en cuenta:

- **Los pescadores dependen de información correcta** para su seguridad en el agua — una alerta falsa o datos incorrectos tiene consecuencias reales
- **La privacidad de números de teléfono** es crítica — son personas, no datos
- **El sistema puede fallar** en zonas con mala conectividad — diseñar para degradación elegante, no para condiciones ideales
- **No somos el experto final** en las condiciones de la Ciénaga — los datos deben siempre poder ser cuestionados por el pescador
