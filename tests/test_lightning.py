"""Tests de la ingesta de rayos GOES-19 GLM. Mockea httpx (listado S3 +
descarga) — sin red. Mismo patrón que tests/test_weather.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import h5py

from app.core.config import settings
from app.services.ingestion import lightning


def _build_glm_bytes(flashes: list[tuple[float, float, float]], epoch: str) -> bytes:
    """HDF5 mínimo con la forma real de GLM-L2-LCFA: flash_lat/flash_lon planos
    + flash_time_offset_of_first_event empaquetado (CF scale/offset + _Unsigned),
    confirmada contra un archivo real en scripts/verify_glm_lead_29ago.py."""
    scale, add_offset = 0.0003814756, -5.0
    raw = [round((s - add_offset) / scale) for _, _, s in flashes]
    with h5py.File("mem.h5", "w", driver="core", backing_store=False) as f:
        f.create_dataset("flash_lat", data=[lat for lat, _, _ in flashes], dtype="float32")
        f.create_dataset("flash_lon", data=[lon for _, lon, _ in flashes], dtype="float32")
        ds = f.create_dataset("flash_time_offset_of_first_event", data=raw, dtype="int16")
        ds.attrs["_Unsigned"] = "true"
        ds.attrs["scale_factor"] = [scale]
        ds.attrs["add_offset"] = [add_offset]
        ds.attrs["units"] = f"seconds since {epoch}"
        f.flush()
        return f.id.get_file_image()


_LISTING_XML = "".join(f"<Key>GLM-L2-LCFA/2026/241/20/file{i}.nc</Key>" for i in range(3))


def _fake_client(*, file_bytes: bytes | None, download_falla: bool = False):
    async def _get(url, params=None, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if params is not None:
            resp.text = _LISTING_XML
        elif download_falla:
            raise Exception("boom")
        else:
            resp.content = file_bytes
        return resp

    client = MagicMock()
    client.get = AsyncMock(side_effect=_get)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)
    return factory, client


def setup_function():
    lightning._cache = None
    lightning._cache_ts = 0.0


def test_get_lightning_flashes_filtra_al_corredor():
    dentro = (settings.corredor_lat_min + 0.1, settings.corredor_lon_min + 0.1, 1.0)
    fuera = (0.0, 0.0, 2.0)  # fuera de la caja del corredor
    data = _build_glm_bytes([dentro, fuera], "2026-08-29 20:00:00.000")
    factory, _ = _fake_client(file_bytes=data)

    with patch.object(lightning.httpx, "AsyncClient", factory):
        out = asyncio.run(lightning.get_lightning_flashes())

    assert out["origen"] == "medido"
    # 3 archivos listados, cada uno con el mismo destello dentro del corredor
    assert len(out["flashes"]) == 3
    assert all(abs(f["lat"] - dentro[0]) < 0.01 for f in out["flashes"])


def test_get_lightning_flashes_sin_cache_no_inventa_dato():
    with (
        patch.object(lightning.httpx, "AsyncClient", _fake_client(file_bytes=None, download_falla=True)[0]),
        patch.object(lightning.asyncio, "sleep", AsyncMock()),
    ):
        out = asyncio.run(lightning.get_lightning_flashes())

    assert out == {"flashes": [], "origen": "sin_dato"}


def test_get_lightning_flashes_fallback_a_cache():
    dentro = (settings.corredor_lat_min + 0.1, settings.corredor_lon_min + 0.1, 1.0)
    data = _build_glm_bytes([dentro], "2026-08-29 20:00:00.000")
    ok_factory, _ = _fake_client(file_bytes=data)
    with patch.object(lightning.httpx, "AsyncClient", ok_factory):
        asyncio.run(lightning.get_lightning_flashes())

    with (
        patch.object(lightning, "_TTL", -1.0),
        patch.object(lightning.httpx, "AsyncClient", _fake_client(file_bytes=None, download_falla=True)[0]),
        patch.object(lightning.asyncio, "sleep", AsyncMock()),
    ):
        out = asyncio.run(lightning.get_lightning_flashes())

    assert out["origen"] == "cache"
    assert len(out["flashes"]) == 3


def test_get_lightning_flashes_dentro_del_ttl_no_llama_red():
    dentro = (settings.corredor_lat_min + 0.1, settings.corredor_lon_min + 0.1, 1.0)
    data = _build_glm_bytes([dentro], "2026-08-29 20:00:00.000")
    factory, client = _fake_client(file_bytes=data)
    with patch.object(lightning.httpx, "AsyncClient", factory):
        asyncio.run(lightning.get_lightning_flashes())
        asyncio.run(lightning.get_lightning_flashes())

    # 1 listado + 3 descargas = 4 llamadas en el primer ciclo; el segundo no
    # debería agregar ninguna (sirve desde cache en memoria, dentro del TTL).
    assert client.get.await_count == 4
