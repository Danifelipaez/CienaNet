"""Interfaz abstracta de IA para NLU y generación de respuestas.

Para cambiar de proveedor: implementar AIProvider y actualizar get_ai_provider().
El resto del código (WhatsApp service, alert service) nunca importa un SDK concreto.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class AIProvider(Protocol):
    async def complete(self, system: str, user: str) -> str:
        """Genera una respuesta dado un prompt de sistema y uno de usuario."""
        ...


class _StubProvider:
    """Sin proveedor configurado: retorna string vacío sin lanzar errores."""

    async def complete(self, system: str, user: str) -> str:
        return ""


def get_ai_provider() -> AIProvider:
    """Retorna el proveedor de IA activo.

    Para conectar un proveedor real:
    1. Instalar su SDK en requirements.txt
    2. Implementar una clase que cumpla el protocolo AIProvider
    3. Instanciarla aquí en lugar de _StubProvider
    """
    from app.core.config import settings  # import local evita ciclos

    if not settings.ai_api_key:
        return _StubProvider()

    # ponytail: stub hasta que se decida el proveedor. Reemplazar este bloque.
    return _StubProvider()
