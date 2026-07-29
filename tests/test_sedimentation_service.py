"""Tests de app/services/sedimentation_service.py."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.services.sedimentation_service import get_sedimentation_zones


def test_mapea_zona_orm_a_dict_con_id_como_string():
    zone_id = uuid.uuid4()
    zone = MagicMock(id=zone_id, nombre="Caño X", polygon=[[10.0, -74.0]], nivel="alto", observacion="obs")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [zone]
    db = AsyncMock()
    db.execute.return_value = result

    zonas = asyncio.run(get_sedimentation_zones(db))

    assert zonas == [
        {"id": str(zone_id), "nombre": "Caño X", "polygon": [[10.0, -74.0]], "nivel": "alto", "observacion": "obs"}
    ]


def test_sin_zonas_retorna_lista_vacia():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.return_value = result

    assert asyncio.run(get_sedimentation_zones(db)) == []
