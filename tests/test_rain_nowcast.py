"""Tests de la ingesta de lluvia GOES-19 RRQPE (app/services/ingestion/rain_nowcast.py)
y del replay de la regla contra 29 días de scans reales (docs/ALERTAS_LLUVIA.md).
Mockea httpx — sin red.
"""

import asyncio
import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import h5py
import numpy as np

from app.services.ingestion import rain_nowcast as rn
from app.services.rain_signals import lluvia_nowcast

_SCALE = 0.00152602  # mm/h por unidad uint16, el scale_factor real del producto


def _raw(caja_mm_h: float = 0.0, caja_frac: float = 0.0, anillo_mm_h: float = 0.0, anillo_frac: float = 0.0):
    """Ventana cruda uint16 sin lluvia, con la fracción pedida de píxeles de la
    caja/anillo puesta a la tasa pedida (mm/h)."""
    raw = np.zeros(rn.VENTANA_SHAPE, dtype=np.uint16)
    for mask, mm_h, frac in (
        (rn._MASK_CAJA, caja_mm_h, caja_frac),
        (rn._MASK_ANILLO, anillo_mm_h, anillo_frac),
    ):
        idx = np.flatnonzero(mask)[: round(frac * mask.sum())]
        raw.flat[idx] = round(mm_h / _SCALE)
    return raw


def _estado(raw: np.ndarray, edad_min: int = 10) -> str:
    ahora = datetime(2026, 10, 24, 14, 0, tzinfo=UTC)
    f = {"scan": ahora - timedelta(minutes=edad_min), **rn.features_from_raw(raw)}
    return lluvia_nowcast(f, ahora)["estado"]


def test_mascaras_tienen_el_tamano_del_backtest():
    assert rn._MASK_CAJA.sum() == 520
    assert rn._MASK_ANILLO.sum() == 2204
    assert not (rn._MASK_CAJA & rn._MASK_ANILLO).any()
    assert rn.VENTANA_SHAPE == (174, 178)


def test_sin_lluvia_en_ningun_lado():
    f = rn.features_from_raw(_raw())
    assert f == {"frac_caja_1mm": 0.0, "frac_anillo_5mm": 0.0, "frac_nan": 0.0}
    assert _estado(_raw()) == "sin_lluvia"


def test_lluvia_debil_en_todo_el_anillo_no_es_inminente():
    # Falso positivo a evitar: 100 % del anillo con 3 mm/h (llovizna) < 5 mm/h.
    assert _estado(_raw(anillo_mm_h=3.0, anillo_frac=1.0)) == "sin_lluvia"


def test_lluvia_fuerte_en_el_anillo_con_caja_seca_es_inminente():
    assert _estado(_raw(anillo_mm_h=12.0, anillo_frac=0.03)) == "inminente"


def test_lluvia_fuerte_en_poco_anillo_no_es_inminente():
    # 1 % del anillo (22 px ≈ 90 km²): una celda aislada, bajo el 2 % del backtest.
    assert _estado(_raw(anillo_mm_h=40.0, anillo_frac=0.01)) == "sin_lluvia"


def test_lluvia_en_la_caja_es_lloviendo_aunque_el_anillo_este_fuerte():
    assert _estado(_raw(caja_mm_h=2.0, caja_frac=0.20, anillo_mm_h=12.0, anillo_frac=0.30)) == "lloviendo"


def test_llovizna_dispersa_en_la_caja_no_apaga_el_aviso():
    # Falso negativo a evitar: 3 % de la caja con 1.5 mm/h (< 5 %) no es "lloviendo".
    assert _estado(_raw(caja_mm_h=1.5, caja_frac=0.03, anillo_mm_h=12.0, anillo_frac=0.05)) == "inminente"


def test_muchos_nan_es_sin_dato_aunque_el_resto_parezca_lluvia():
    raw = _raw(anillo_mm_h=12.0, anillo_frac=0.05)
    region = np.flatnonzero(rn._MASK_CAJA | rn._MASK_ANILLO)
    raw.flat[region[: len(region) // 5]] = 65535  # 20 % de caja+anillo sin dato
    assert rn.features_from_raw(raw)["frac_nan"] > 0.10
    assert _estado(raw) == "sin_dato"


def test_todo_nan_es_sin_dato_no_sin_lluvia():
    raw = np.full(rn.VENTANA_SHAPE, 65535, dtype=np.uint16)
    f = rn.features_from_raw(raw)
    assert f["frac_caja_1mm"] is None and f["frac_anillo_5mm"] is None and f["frac_nan"] == 1.0
    assert _estado(raw) == "sin_dato"


def test_scan_viejo_es_sin_dato():
    assert _estado(_raw(anillo_mm_h=12.0, anillo_frac=0.05), edad_min=40) == "sin_dato"


def test_scan_time_sale_del_nombre_del_archivo():
    key = (
        "ABI-L2-RRQPEF/2026/299/08/OR_ABI-L2-RRQPEF-M6_G19_s20262990840218_e20262990849526_c20262990849589.nc"
    )
    assert rn._scan_time(key) == datetime(2026, 10, 26, 8, 40, tzinfo=UTC)


def _build_rrqpe_bytes(raw_window: np.ndarray) -> bytes:
    """HDF5 mínimo con la forma real de RRQPEF: RRQPE uint16 sobre la malla full
    disk (la ventana va en sus índices reales) + scale_factor como atributo."""
    full = np.zeros((rn._J1 + 5, rn._I1 + 5), dtype=np.uint16)
    full[rn._J0 : rn._J1, rn._I0 : rn._I1] = raw_window
    with h5py.File("mem.h5", "w", driver="core", backing_store=False) as f:
        ds = f.create_dataset("RRQPE", data=full, chunks=(256, 256), compression="gzip")
        ds.attrs["scale_factor"] = np.array([_SCALE], dtype="float32")
        f.flush()
        return f.id.get_file_image()


def test_features_from_bytes_lee_solo_la_ventana():
    data = _build_rrqpe_bytes(_raw(anillo_mm_h=12.0, anillo_frac=0.03, caja_mm_h=2.0, caja_frac=0.5))
    f = rn._features_from_bytes(data)
    assert abs(f["frac_caja_1mm"] - 0.5) < 0.01
    assert abs(f["frac_anillo_5mm"] - 0.03) < 0.01
    assert f["frac_nan"] == 0.0


def test_features_from_bytes_int16_con_unsigned_se_lee_como_uint16():
    # Variante int16 + _Unsigned (relleno -1 == 65535): 40000 (61 mm/h) en int16 sería negativo
    # y el relleno no se reconocería.
    raw = np.full(rn.VENTANA_SHAPE, 40000, dtype=np.uint16)
    raw.flat[np.flatnonzero(rn._MASK_CAJA)[:52]] = 65535  # 52 px de la caja sin dato
    full = np.zeros((rn._J1 + 5, rn._I1 + 5), dtype=np.uint16)
    full[rn._J0 : rn._J1, rn._I0 : rn._I1] = raw
    with h5py.File("mem.h5", "w", driver="core", backing_store=False) as f:
        ds = f.create_dataset("RRQPE", data=full.view(np.int16))
        ds.attrs["scale_factor"] = np.array([_SCALE], dtype="float32")
        ds.attrs["add_offset"] = np.array([0.0], dtype="float32")
        ds.attrs["_FillValue"] = np.array([-1], dtype="int16")
        ds.attrs["_Unsigned"] = "true"
        f.flush()
        data = f.id.get_file_image()
    f = rn._features_from_bytes(data)
    assert f["frac_caja_1mm"] == 1.0  # 40000 * scale = 61 mm/h, no negativo
    assert f["frac_anillo_5mm"] == 1.0
    assert abs(f["frac_nan"] - 52 / (rn._MASK_CAJA.sum() + rn._MASK_ANILLO.sum())) < 1e-6


_KEYS = [
    f"ABI-L2-RRQPEF/2026/299/07/OR_ABI-L2-RRQPEF-M6_G19_s202629907{m}0218_e0_c0.nc"
    for m in ("00", "10", "20")
]


def _fake_client(*, listados: list[str], file_bytes: bytes | None = None, falla_descarga: bool = False):
    """`listados`: XML que devuelve cada llamada de listado, en orden (hora actual, hora anterior)."""
    pendientes = list(listados)

    async def _get(url, params=None, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if params is not None:
            resp.text = pendientes.pop(0)
        elif falla_descarga:
            raise Exception("boom")
        else:
            resp.content = file_bytes
        return resp

    client = MagicMock()
    client.get = AsyncMock(side_effect=_get)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx), client


def _xml(keys: list[str]) -> str:
    return "<ListBucketResult>" + "".join(f"<Key>{k}</Key>" for k in keys) + "</ListBucketResult>"


def setup_function():
    rn._cache = None
    rn._cache_ts = 0.0
    rn.set_ultimo_lluvia(None)


def test_get_rain_features_toma_el_ultimo_archivo_de_la_hora_anterior_si_la_actual_esta_vacia():
    data = _build_rrqpe_bytes(_raw(anillo_mm_h=12.0, anillo_frac=0.03))
    factory, client = _fake_client(listados=[_xml([]), _xml(_KEYS)], file_bytes=data)
    with patch.object(rn.httpx, "AsyncClient", factory):
        out = asyncio.run(rn.get_rain_features())

    assert out["scan"] == datetime(2026, 10, 26, 7, 20, tzinfo=UTC)  # el último de _KEYS, no el primero
    assert abs(out["frac_anillo_5mm"] - 0.03) < 0.01
    assert client.get.call_args.args[0].endswith(_KEYS[-1])
    assert client.get.await_count == 3  # 2 listados + 1 descarga


def test_get_rain_features_usa_cache_dentro_del_ttl():
    data = _build_rrqpe_bytes(_raw())
    factory, client = _fake_client(listados=[_xml(_KEYS)], file_bytes=data)
    with patch.object(rn.httpx, "AsyncClient", factory):
        asyncio.run(rn.get_rain_features())
        asyncio.run(rn.get_rain_features())

    assert client.get.await_count == 2  # listado + descarga, una sola vez


def test_get_rain_features_sin_archivos_es_none():
    factory, _ = _fake_client(listados=[_xml([]), _xml([])])
    with patch.object(rn.httpx, "AsyncClient", factory):
        assert asyncio.run(rn.get_rain_features()) is None


def test_get_rain_features_si_la_descarga_falla_es_none_no_dato_inventado():
    factory, _ = _fake_client(listados=[_xml(_KEYS)] * 2, falla_descarga=True)
    with (
        patch.object(rn.httpx, "AsyncClient", factory),
        patch.object(rn.asyncio, "sleep", new_callable=AsyncMock),
    ):
        assert asyncio.run(rn.get_rain_features()) is None


def test_ultimo_lluvia_se_guarda_y_se_lee():
    assert rn.get_ultimo_lluvia() is None
    rn.set_ultimo_lluvia({"estado": "inminente"})
    assert rn.get_ultimo_lluvia() == {"estado": "inminente"}


# --- Replay con datos reales -------------------------------------------------
# Fixture: 4220 scans GOES-19 RRQPEF (27-sep..26-oct-2026) con las features de
# producción, generado por scripts/gen_rrqpe_fixture.py. La métrica replica
# del backtest de la investigación (docs/ALERTAS_LLUVIA.md): episodios de
# lluvia en la caja fusionando huecos < 60 min; alerta = estado "inminente";
# acierto = el episodio empieza dentro de los 90 min siguientes.

_FIXTURE = Path(__file__).parent / "fixtures" / "rrqpe_cgsm_2026-09-27_10-26.csv"
_LATENCIA_SCAN = timedelta(minutes=10)  # el archivo aparece ~10 min después de su inicio
_HORIZONTE_MIN = 90
_GAP_FUSION_MIN = 60


def _episodios(tiempos: list[datetime], mask: list[bool]) -> list[tuple[int, int]]:
    eps: list[list[int]] = []
    for i, activo in enumerate(mask):
        if not activo:
            continue
        if eps and (tiempos[i] - tiempos[eps[-1][1]]).total_seconds() / 60 <= _GAP_FUSION_MIN:
            eps[-1][1] = i
        else:
            eps.append([i, i])
    return [(a, b) for a, b in eps]


def _replay() -> dict:
    with _FIXTURE.open() as fh:
        filas = list(csv.DictReader(fh))
    tiempos = [datetime.strptime(r["timestamp"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC) for r in filas]
    estados = [
        lluvia_nowcast(
            {
                "scan": t,
                "frac_caja_1mm": float(r["frac_caja_1mm"]),
                "frac_anillo_5mm": float(r["frac_anillo_5mm"]),
                "frac_nan": float(r["frac_nan"]),
            },
            t + _LATENCIA_SCAN,
        )["estado"]
        for t, r in zip(tiempos, filas, strict=True)
    ]
    inicios = [tiempos[a] for a, _ in _episodios(tiempos, [e == "lloviendo" for e in estados])]
    alertas = _episodios(tiempos, [e == "inminente" for e in estados])

    aciertos: dict[datetime, list[float]] = {}
    falsas = 0
    for a, _ in alertas:
        siguientes = [
            o for o in inicios if o > tiempos[a] and (o - tiempos[a]).total_seconds() / 60 <= _HORIZONTE_MIN
        ]
        if siguientes:
            aciertos.setdefault(siguientes[0], []).append((siguientes[0] - tiempos[a]).total_seconds() / 60)
        else:
            falsas += 1
    n, h = len(inicios), len(aciertos)
    return {
        "scans": len(filas),
        "episodios": n,
        "aciertos": h,
        "falsas": falsas,
        "pod": h / n,
        "far": falsas / (falsas + h),
        "csi": h / (n + falsas),
        "antelacion_mediana": float(np.median([max(v) for v in aciertos.values()])),
    }


def test_replay_29_dias_reales_reproduce_pod_y_far_del_backtest():
    m = _replay()
    # Cobertura del fixture: 27-sep..26-oct, 10 min por scan (algunos scans faltan).
    assert m["scans"] == 4220
    assert m["episodios"] == 34
    # Backtest de la investigación: POD 0.71 (24/34), FAR por episodio 0.43 (18 falsas), CSI 0.46.
    assert m["pod"] >= 0.65, m
    assert m["far"] <= 0.50, m
    assert (m["aciertos"], m["falsas"]) == (24, 18)
    assert 20 <= m["antelacion_mediana"] <= 40  # mediana 30 min en el backtest
