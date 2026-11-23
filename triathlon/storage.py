"""Sicherung der Konto-Datenbanken in einem S3-kompatiblen Speicher (z. B. Backblaze B2).

Nötig bei Hostern ohne dauerhaften Speicher wie Streamlit Community Cloud: Dort gehen lokale
Dateien bei jedem Neustart verloren. Ablauf:

* Beim Anmelden lädt ``restore`` die Datei des Kontos aus dem Speicher, falls sie lokal fehlt.
* Nach jedem Seitenaufruf lädt ``flush`` sie wieder hoch – aber nur, wenn sie sich geändert hat.
  Hochgeladen wird eine konsistente Kopie (SQLite-Backup), auch wenn gerade geschrieben wird.
* ``delete`` entfernt sie beim Löschen des Kontos.

Eingerichtet wird das über ``[storage]`` in secrets.toml (endpoint_url, bucket, key_id,
application_key, optional region und prefix). Ohne diesen Abschnitt tut das Modul nichts.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

REQUIRED = ("endpoint_url", "bucket", "key_id", "application_key")

_config: dict = {}
_client = None
_lock = threading.Lock()
_path_locks: dict[Path, threading.Lock] = {}
_synced: dict[Path, tuple[int, int]] = {}   # Datei → (mtime_ns, Größe) beim letzten Abgleich
_ready: set[Path] = set()                    # Dateien, deren Stand mit dem Speicher abgeglichen ist


class StorageError(Exception):
    pass


def configure(section: dict | None, client=None) -> None:
    """Liest die Einstellungen (``[storage]``). ``client`` nur für Tests."""
    global _config, _client
    section = dict(section or {})
    new = section if all(section.get(k) for k in REQUIRED) else {}
    if client is not None or new != _config:   # gleiche Einstellungen → Verbindung weiterverwenden
        _client = client
    _config = new


def enabled() -> bool:
    return bool(_config)


def region_from_endpoint(endpoint: str) -> str:
    """Backblaze: https://s3.eu-central-003.backblazeb2.com → eu-central-003."""
    host = urlparse(endpoint).hostname or ""
    parts = host.split(".")
    return parts[1] if len(parts) > 2 and parts[0] == "s3" else "us-east-1"


def _s3():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        endpoint = _config["endpoint_url"]
        _client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=_config.get("region") or region_from_endpoint(endpoint),
            aws_access_key_id=_config["key_id"],
            aws_secret_access_key=_config["application_key"],
            config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=60,
                          retries={"max_attempts": 3}),
        )
    return _client


def _key(path: Path) -> str:
    return f"{_config.get('prefix', 'users/')}{path.name}"


def _is_missing(exc: Exception) -> bool:
    code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
    return code in ("404", "NoSuchKey", "NotFound")


def _path_lock(path: Path) -> threading.Lock:
    with _lock:
        return _path_locks.setdefault(path, threading.Lock())


def _stat(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return st.st_mtime_ns, st.st_size


def restore(path: Path) -> None:
    """Holt die Datei aus dem Speicher, falls sie lokal fehlt. Wirft ``StorageError``, wenn der
    Speicher nicht erreichbar ist – dann darf das Konto nicht leer weiterlaufen (sonst würde die
    leere Datei später die gesicherte überschreiben)."""
    if not enabled():
        return
    path = Path(path)
    with _path_lock(path):
        if path in _ready and path.exists():
            return
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".download")
            try:
                _s3().download_file(_config["bucket"], _key(path), str(tmp))
            except Exception as exc:  # noqa: BLE001 – boto3 wirft verschiedene Fehlerarten
                tmp.unlink(missing_ok=True)
                if not _is_missing(exc):
                    raise StorageError(f"Deine Daten konnten nicht geladen werden ({exc}).") from exc
            else:
                os.replace(tmp, path)
        _synced[path] = _stat(path) or (0, 0)
        _ready.add(path)


def flush(path: Path) -> bool:
    """Lädt die Datei hoch, wenn sie sich seit dem letzten Abgleich geändert hat. True = hochgeladen."""
    if not enabled():
        return False
    path = Path(path)
    if path not in _ready:          # nie erfolgreich abgeglichen → nichts überschreiben
        return False
    with _path_lock(path):
        current = _stat(path)
        if current is None or current == _synced.get(path):
            return False
        fd, tmp_name = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            with sqlite3.connect(path) as src, sqlite3.connect(tmp_name) as dst:
                src.backup(dst)
            src.close()
            dst.close()
            _s3().upload_file(tmp_name, _config["bucket"], _key(path))
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"Sichern fehlgeschlagen ({exc}).") from exc
        finally:
            Path(tmp_name).unlink(missing_ok=True)
        _synced[path] = current
        return True


def delete(path: Path) -> None:
    """Entfernt die gesicherte Datei (beim Löschen des Kontos)."""
    if not enabled():
        return
    path = Path(path)
    with _path_lock(path):
        try:
            _s3().delete_object(Bucket=_config["bucket"], Key=_key(path))
        except Exception as exc:  # noqa: BLE001
            if not _is_missing(exc):
                raise StorageError(f"Gesicherte Daten konnten nicht gelöscht werden ({exc}).") from exc
        _synced.pop(path, None)
        _ready.discard(path)
