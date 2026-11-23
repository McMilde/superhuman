"""Felles testoppsett. Peker DB_PATH til en midlertidig fil FØR app importeres,
slik at testene aldri rører den ekte trening.db."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="superhuman-test-"))
os.environ["DB_PATH"] = str(_tmp / "test.db")
os.environ["PLANLEGGER"] = "0"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("APP_PASSORD", None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as app_modul  # noqa: E402

RYDD_TABELLER = [
    "dagslogg", "vektlogg", "dagssjekk", "ukeplan", "helgeplan", "dagsmelding",
    "chat", "push_abonnement", "varsel_logg", "oura_malinger", "withings_malinger",
    "withings_konto", "oura_konto", "middag_vurdering", "ukemal", "oura_okter", "kurs_fremgang",
]


@pytest.fixture
def client():
    app_modul.app.config["TESTING"] = True
    return app_modul.app.test_client()


@pytest.fixture
def db():
    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def rydd():
    yield
    conn = sqlite3.connect(os.environ["DB_PATH"])
    finnes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in RYDD_TABELLER:
        if t in finnes:
            conn.execute(f"DELETE FROM {t}")
    conn.commit()
    conn.close()
