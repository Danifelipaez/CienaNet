import hashlib
import hmac

from app.core import security


def test_hmac_roundtrip(monkeypatch):
    secret = "test-app-secret"
    monkeypatch.setattr(security.settings, "whatsapp_app_secret", secret)
    payload = b'{"entry":[{"id":"123"}]}'
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    assert security.verify_hmac_meta(payload, sig) is True
    # Mutar un byte del payload invalida la firma.
    assert security.verify_hmac_meta(payload + b"x", sig) is False


def test_hmac_falla_cerrado_sin_secreto(monkeypatch):
    # Con WHATSAPP_APP_SECRET vacío (default), cualquier firma debe rechazarse —
    # sin esta guarda, hmac.new firma con clave vacía y una firma calculada así pasa.
    monkeypatch.setattr(security.settings, "whatsapp_app_secret", "")
    payload = b'{"entry":[{"id":"123"}]}'
    sig = "sha256=" + hmac.new(b"", payload, hashlib.sha256).hexdigest()

    assert security.verify_hmac_meta(payload, sig) is False
    assert security.verify_hmac_meta(payload, "") is False


def test_hash_api_key_deterministic(monkeypatch):
    monkeypatch.setattr(security.settings, "sensor_api_key_secret", "salt")
    assert security.hash_api_key("device-key") == security.hash_api_key("device-key")
    assert security.hash_api_key("a") != security.hash_api_key("b")
