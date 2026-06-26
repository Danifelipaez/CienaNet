"""Entry point para Vercel: adapta la app ASGI de FastAPI a serverless."""

from mangum import Mangum

from app.main import app

handler = Mangum(app)
