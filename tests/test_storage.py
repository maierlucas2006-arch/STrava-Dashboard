"""Sicherung der Konto-Datenbanken in einem S3-kompatiblen Speicher (mit nachgebautem Speicher)."""
import shutil
import sqlite3
import threading

import pytest

from triathlon import storage

CFG = {"endpoint_url": "https://s3.eu-central-003.backblazeb2.com", "bucket": "tri", "key_id": "k",
       "application_key": "s"}


class Missing(Exception):
    response = {"Error": {"Code": "404"}}


class FakeS3:
    def __init__(self, fail=False):
        self.objects, self.uploads, self.fail = {}, 0, fail

    def download_file(self, bucket, key, filename):
        if self.fail:
            raise ConnectionError("offline")
        if key not in self.objects:
            raise Missing()
        with open(filename, "wb") as f:
            f.write(self.objects[key])

    def upload_file(self, filename, bucket, key):
        with open(filename, "rb") as f:
            self.objects[key] = f.read()
        self.uploads += 1

    def delete_object(self, Bucket, Key):  # noqa: N803 – boto3-Namen
        self.objects.pop(Key, None)


@pytest.fixture
def s3():
    fake = FakeS3()
    storage.configure(CFG, client=fake)
    storage._ready.clear()
    storage._synced.clear()
    yield fake
    storage.configure(None)


def write(path, value):
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE IF NOT EXISTS t (v)")
        con.execute("INSERT INTO t VALUES (?)", (value,))
    con.close()


def read(path):
    with sqlite3.connect(path) as con:
        rows = [r[0] for r in con.execute("SELECT v FROM t")]
    con.close()
    return rows


def test_disabled_without_complete_config():
    storage.configure({"bucket": "x"})
    assert not storage.enabled()
    storage.restore("egal.db")              # tut nichts
    assert storage.flush("egal.db") is False


def test_region_from_backblaze_endpoint():
    assert storage.region_from_endpoint("https://s3.eu-central-003.backblazeb2.com") == "eu-central-003"


def test_new_account_upload_and_restore_after_restart(s3, tmp_path):
    path = tmp_path / "users" / "abc.db"
    storage.restore(path)                   # neues Konto: nichts im Speicher
    assert not path.exists()
    write(path, 1)
    assert storage.flush(path) is True
    assert storage.flush(path) is False     # unverändert → kein erneutes Hochladen
    # Neustart beim Hoster: lokale Datei weg, Prozess frisch
    shutil.rmtree(tmp_path / "users")
    storage._ready.clear()
    storage._synced.clear()
    storage.restore(path)
    assert read(path) == [1]
    write(path, 2)
    assert storage.flush(path) is True
    assert s3.uploads == 2


def test_unreachable_storage_never_overwrites_backup(tmp_path):
    fake = FakeS3(fail=True)
    fake.objects["users/abc.db"] = b"gesichert"
    storage.configure(CFG, client=fake)
    storage._ready.clear()
    path = tmp_path / "abc.db"
    with pytest.raises(storage.StorageError):
        storage.restore(path)
    write(path, 1)                          # selbst wenn trotzdem etwas geschrieben würde …
    assert storage.flush(path) is False     # … wird nichts hochgeladen
    assert fake.objects["users/abc.db"] == b"gesichert"
    storage.configure(None)


def test_delete_removes_backup(s3, tmp_path):
    path = tmp_path / "abc.db"
    storage.restore(path)
    write(path, 1)
    storage.flush(path)
    storage.delete(path)
    assert "users/abc.db" not in s3.objects


def test_parallel_flushes_upload_consistent_copies(s3, tmp_path):
    path = tmp_path / "abc.db"
    storage.restore(path)
    write(path, 0)

    def worker(n):
        write(path, n)
        storage.flush(path)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(1, 6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    storage.flush(path)
    restored = tmp_path / "copy.db"
    restored.write_bytes(s3.objects["users/abc.db"])
    assert sorted(read(restored)) == [0, 1, 2, 3, 4, 5]
