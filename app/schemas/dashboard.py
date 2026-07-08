"""Pydantic schemas para los endpoints del dashboard interno."""

import uuid

from pydantic import BaseModel


class AskRequest(BaseModel):
    pregunta: str
    contexto: dict | None = None  # punto de pesca seleccionado en el mapa, si aplica
    # Hilo al que pertenece la pregunta. None = conversación nueva (el backend
    # mintea un conversation_id y lo devuelve en AskResponse).
    conversation_id: uuid.UUID | None = None


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
    conversation_id: str  # hilo al que quedó asociada la respuesta


class AITurn(BaseModel):
    """Un turno (pregunta + respuesta) dentro de una conversación."""

    id: str
    pregunta: str
    respuesta: list[AIParrafo]
    sugerencia: str | None = None
    created_at: str


class AIConversationItem(BaseModel):
    """Una conversación completa del historial: un hilo con sus turnos en orden."""

    id: str  # conversation_id
    titulo: str  # primera pregunta del hilo
    created_at: str  # primera actividad
    updated_at: str  # última actividad (para ordenar el historial)
    turnos: list[AITurn]
