"""Startet das Dashboard. In PyCharm: Rechtsklick auf diese Datei → Run 'start'.

Danach öffnet sich der Browser auf http://localhost:8501.
"""
import sys
from pathlib import Path

from streamlit.web import cli

if __name__ == "__main__":
    app = Path(__file__).resolve().parent / "app.py"
    sys.argv = ["streamlit", "run", str(app), "--server.port", "8501"]
    sys.exit(cli.main())
