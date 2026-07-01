"""Pydantic schemas para los endpoints del dashboard interno."""

from pydantic import BaseModel


class AskRequest(BaseModel):
    pregunta: str
    contexto: dict | None = None  # punto de pesca seleccionado en el mapa, si aplica


class AIDato(BaseModel):
    v: str
    d: str
    fuente: str


class AIParrafo(BaseModel):
    tipo: str  # "texto" | "datos" | "limitaciones"
    titulo: str | None = None
    html: str | None = None
    items: list[AIDato] | None = None


class AskResponse(BaseModel):
    parrafos: list[AIParrafo]
    sugerencia: str | None = None


class AIHistoryItem(BaseModel):
    id: str
    pregunta: str
    respuesta: list[AIParrafo]
    sugerencia: str | None = None
    contexto: dict | None = None
    created_at: str
