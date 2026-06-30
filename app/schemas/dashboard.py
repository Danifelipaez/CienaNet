"""Pydantic schemas para los endpoints del dashboard interno."""

from pydantic import BaseModel


class AskRequest(BaseModel):
    pregunta: str


class AskResponse(BaseModel):
    respuesta: str
