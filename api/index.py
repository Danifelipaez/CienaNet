"""Entry point del deployment serverless en Vercel.

El runtime de Python de Vercel sirve aplicaciones ASGI directamente: detecta la
variable `app` de este módulo y la ejecuta. No hace falta Mangum (el wrapper que
usaba la versión anterior de este archivo, borrada en 90942c0): ese adaptador
traduce ASGI al protocolo handler de AWS Lambda, que no es el que Vercel espera.

Acá solo se re-exporta la app de app/main.py — el mismo código que corre el
servidor universitario, sin ramas por plataforma. Lo que cambia entre los dos
deployments son variables de entorno (RUN_SCHEDULER) y el pool de conexiones
(ver app/core/database.py), no el árbol de routers.

Ver docs/DEPLOYMENT.md.
"""

from app.main import app

__all__ = ["app"]
