"""Genera tests/fixtures/rrqpe_cgsm_2026-09-27_10-26.csv, el fixture del test de
replay de la alerta de lluvia (tests/test_rain_nowcast.py::test_replay_*).

Cada fila es un scan GOES-19 ABI-L2-RRQPEF de 10 min entre el 27-sep y el 26-oct
de 2026 (4220 scans, 29.3 días) con las features que usa la regla en producción.
Se calculan con `rain_nowcast.features_from_raw`, la MISMA función que corre en
vivo, sobre la ventana cruda (uint16) que se bajó del bucket `noaa-goes19`.

NO es parte de pytest. La ventana cruda no se versiona (~25 MB comprimidos): vive
en npz diarios `rrqpe_<doy>.npz` con `t` (inicio de scan, epoch s) y `raw`
(n, 174, 178) uint16, generados bajando por rango de bytes la ventana de cada
archivo (investigación del backtest, docs/ALERTAS_LLUVIA.md).

Uso (necesita las env vars de Settings o un .env, como los demás scripts):
    python scripts/gen_rrqpe_fixture.py DIR_NPZ [salida.csv]
"""

import csv
import glob
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.services.ingestion.rain_nowcast import features_from_raw

_SALIDA_DEFAULT = Path(__file__).resolve().parent.parent / "tests/fixtures/rrqpe_cgsm_2026-09-27_10-26.csv"


def main(directorio: str, salida: Path) -> None:
    archivos = sorted(
        glob.glob(f"{directorio}/rrqpe_*.npz"), key=lambda p: int(re.findall(r"(\d+)\.npz$", p)[0])
    )
    filas = []
    for archivo in archivos:
        d = np.load(archivo)
        for t, raw in zip(d["t"], d["raw"], strict=True):
            f = features_from_raw(raw)
            filas.append(
                (
                    datetime.fromtimestamp(float(t), timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
                    f"{f['frac_caja_1mm']:.5f}",
                    f"{f['frac_anillo_5mm']:.5f}",
                    f"{f['frac_nan']:.5f}",
                )
            )
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(("timestamp", "frac_caja_1mm", "frac_anillo_5mm", "frac_nan"))
        w.writerows(filas)
    print(f"{len(filas)} scans de {len(archivos)} archivos -> {salida}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], Path(sys.argv[2]) if len(sys.argv) > 2 else _SALIDA_DEFAULT)
