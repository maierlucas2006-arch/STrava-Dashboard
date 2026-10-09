"""Rauchtest: Jede Seite läuft mit Demo-Daten und mit leerer Datenbank ohne Fehler."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from triathlon.demo import build_demo

APP = str(Path(__file__).resolve().parent.parent / "app.py")
PAGES = ["views/uebersicht.py", "views/trainingsplan.py", "views/ausdauer.py", "views/regeneration.py",
         "views/kraft.py", "views/ernaehrung.py", "views/ziele.py", "views/einstellungen.py"]


def run_page(page: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    if page != PAGES[0]:
        at.switch_page(page)
        at.run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_page_with_demo_data(tmp_db, page):
    build_demo()
    at = run_page(page)
    assert not at.exception, at.exception


@pytest.mark.parametrize("page", PAGES)
def test_page_with_empty_database(tmp_db, page):
    at = run_page(page)
    assert not at.exception, at.exception
