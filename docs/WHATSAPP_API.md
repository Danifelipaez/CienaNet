# Integración WhatsApp Business API — Meta Cloud API

## Configuración Inicial

### Prerequisitos
1. Cuenta Meta Business Suite verificada
2. App en Meta Developer Dashboard con producto "WhatsApp"
3. Número de teléfono registrado (eSIM o número dedicado)
4. Sistema User Token permanente (no el token de 60 días del usuario)

### Flujo de Configuración
```
Meta Developer Dashboard
  └── App → WhatsApp → Configuration
       ├── Phone Number: [número de la eSIM]
       ├── Webhook URL: https://[tu-dominio].vercel.app/api/v1/webhook/whatsapp
       ├── Verify Token: [WHATSAPP_VERIFY_TOKEN del .env]
       └── Subscribed fields: messages, messaging_postbacks
```

---

## Webhook — Verificación Inicial

Meta hace un GET al webhook para verificarlo:

```python
@router.get("/webhook/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403)
```

---

## Webhook — Recepción de Mensajes

### Validación HMAC (OBLIGATORIA)

```python
import hmac
import hashlib

def validate_whatsapp_signature(payload: bytes, signature: str, app_secret: str) -> bool:
    """
    Valida que el webhook viene de Meta y no de un tercero.
    signature viene en el header X-Hub-Signature-256 como "sha256=<hash>"
    """
    expected = hmac.new(
        app_secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    received = signature.replace("sha256=", "")
    return hmac.compare_digest(expected, received)
```

### Estructura del Payload (mensaje de texto)

```json
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
    "changes": [{
      "value": {
        "messaging_product": "whatsapp",
        "metadata": {
          "display_phone_number": "PHONE_NUMBER",
          "phone_number_id": "PHONE_NUMBER_ID"
        },
        "contacts": [{
          "profile": { "name": "Nombre Pescador" },
          "wa_id": "573001234567"
        }],
        "messages": [{
          "from": "573001234567",
          "id": "wamid.xxx",
          "timestamp": "1234567890",
          "type": "text",
          "text": { "body": "cómo está el agua hoy?" }
        }]
      },
      "field": "messages"
    }]
  }]
}
```

---

## Envío de Mensajes

### Texto simple

```python
import httpx

async def send_text_message(to: str, message: str, phone_number_id: str, token: str):
    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": message}
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        return response.json()
```

### Mensaje con botones interactivos

```python
async def send_button_message(to: str, body: str, buttons: list[dict], ...):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"]}}
                    for btn in buttons[:3]  # máximo 3 botones
                ]
            }
        }
    }
```

---

## Tipos de Mensajes Soportados

| Tipo | Caso de uso en CienaNet |
|------|------------------------|
| `text` | Respuestas informativas, alertas |
| `interactive/button` | Menú de opciones (consultar agua, suscribirse a alertas) |
| `interactive/list` | Lista de zonas de la Ciénaga |
| `template` | Mensajes proactivos (alertas fuera de ventana de 24h) |
| `audio` | Responder mensajes de voz (fase futura) |

---

## Ventana de 24 Horas

Meta solo permite enviar mensajes `text` o `interactive` dentro de las **24 horas** después del último mensaje del usuario. Fuera de ese período, se debe usar una **plantilla aprobada** (template).

**Implicación para alertas:** Las alertas proactivas de sensores deben enviarse como templates pre-aprobados por Meta.

### Templates necesarios para solicitar a Meta:
- `alerta_ph_alto` — cuando el pH supera X
- `alerta_salinidad` — cuando conductividad supera X
- `alerta_temperatura` — cuando temperatura supera X
- `bienvenida` — cuando un nuevo pescador escribe por primera vez

---

## Costos (referencia junio 2025)

| Tipo | Costo aprox. |
|------|--------------|
| Mensajes de servicio (respuesta a usuario) | Gratis las primeras 1,000/mes |
| Templates de marketing | ~$0.06 USD por conversación |
| Templates de utilidad | ~$0.02 USD por conversación |

Los costos varían por país. Colombia está en la categoría de tarifas de Latam.

---

## Debugging

### Probar webhook localmente
```bash
# Usar ngrok para exponer localhost
ngrok http 8000

# La URL de ngrok va temporalmente en Meta Developer Dashboard
# Recuerda actualizarla con la URL de Vercel para producción
```

### Verificar entrega de mensajes
- Meta Developer Dashboard → WhatsApp → Logs
- El campo `status` en los webhooks de estado indica: `sent`, `delivered`, `read`, `failed`

### Errores comunes

| Error | Causa | Solución |
|-------|-------|----------|
| `190` Invalid token | Token expirado | Usar System User Token permanente |
| `131030` Recipient not in allowlist | Número no verificado en sandbox | Agregar número al test allowlist |
| `130472` Message failed to send | Ventana de 24h cerrada | Usar template |
| `368` Account blocked | Muchos mensajes rechazados | Mejorar calidad de mensajes |
