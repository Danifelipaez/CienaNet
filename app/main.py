"""App FastAPI de CienaNet Bot."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Placeholder para V-07 (refresco periódico de datos).
    # OJO: un loop persistente (while True: sleep) NO corre en Vercel
    # serverless. Cuando se implemente V-07, usar Vercel Cron o un
    # scheduler externo que pegue a un endpoint de refresco.
    yield


app = FastAPI(title="CienaNet Bot", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # ponytail: abierto para el MVP; restringir al dominio del dashboard antes de prod
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
