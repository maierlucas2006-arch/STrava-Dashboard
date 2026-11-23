"""Sichert alle Konto-Datenbanken (konsistent über die SQLite-Backup-Funktion) und behält 14 Tage.

Täglich per cron, z. B. um 3 Uhr:
    0 3 * * * TRI_DATA_DIR=/var/lib/triathlon-dashboard /opt/triathlon-dashboard/.venv/bin/python \
        /opt/triathlon-dashboard/deploy/backup.py /var/backups/triathlon-dashboard
"""
import os
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

KEEP_DAYS = 14


def main() -> None:
    source = Path(os.environ.get("TRI_DATA_DIR", Path(__file__).resolve().parent.parent / "data")) / "users"
    target_root = Path(sys.argv[1] if len(sys.argv) > 1 else "backups")
    target = target_root / f"{date.today():%Y-%m-%d}"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for db_file in sorted(source.glob("*.db")):
        with sqlite3.connect(db_file) as src, sqlite3.connect(target / db_file.name) as dst:
            src.backup(dst)
        count += 1
    for old in sorted(p for p in target_root.iterdir() if p.is_dir())[:-KEEP_DAYS]:
        shutil.rmtree(old)
    print(f"{count} Datenbanken gesichert nach {target}")


if __name__ == "__main__":
    main()
