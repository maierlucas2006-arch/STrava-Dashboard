"""Startet das Dashboard mit erfundenen Beispieldaten (eigene Datenbank data/demo.db).

Gut zum Ausprobieren, bevor Strava und Garmin verbunden sind.
In PyCharm: Rechtsklick auf diese Datei → Run 'start_demo'.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEMO_DB = ROOT / "data" / "demo.db"
os.environ["TRI_DB_PATH"] = str(DEMO_DB)

if __name__ == "__main__":
    if not DEMO_DB.exists():
        from triathlon.demo import build_demo

        print("Erzeuge Demo-Daten …")
        build_demo()

    from streamlit.web import cli

    sys.argv = ["streamlit", "run", str(ROOT / "app.py"), "--server.port", "8501"]
    sys.exit(cli.main())
