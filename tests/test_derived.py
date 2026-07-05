"""Tests de las variables derivadas del instrumento (§10)."""

from app.services.derived import ec25, salinity_psu, tds_mgl


def test_salinity_pss78_reference():
    """Punto de definición PSS-78: C=42.914 mS/cm, t=15°C, p=0 → SP=35.0."""
    assert salinity_psu(42.914, 15.0) == 35.0


def test_salinity_brackish_ok():
    """Agua salobre típica de la ciénaga da un valor físico > 0."""
    sal = salinity_psu(40.0, 28.0)
    assert sal is not None and 0 < sal < 40


def test_ec25_compensation():
    """A >25°C la EC compensada baja; a 25°C es idéntica."""
    assert ec25(50.0, 25.0) == 50.0
    assert ec25(50.0, 30.0) < 50.0


def test_tds_positive():
    assert tds_mgl(40.0, 28.0) > 0


def test_none_when_missing_inputs():
    assert salinity_psu(None, 25.0) is None
    assert salinity_psu(40.0, None) is None
    assert tds_mgl(None, None) is None
    assert ec25(None, 25.0) is None
