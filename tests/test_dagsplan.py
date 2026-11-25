"""Morgenflyt: påminnelse kl. 07, dagsplan når Oura har levert natta (senest kl. 10)."""
from datetime import datetime

import pytest

import app as app_modul
import coach
import livsstil
import varsler

OSLO = livsstil.OSLO
SUB = {"endpoint": "https://push.example/ok", "keys": {"p256dh": "p", "auth": "a"}}
DAG = "2026-11-18"


@pytest.fixture(autouse=True)
def nullstill(monkeypatch):
    def feiler(*a, **k):
        raise coach.CoachUtilgjengelig("test")
    monkeypatch.setattr(coach, "sporr_claude", feiler)
    varsler._SISTE_MORGENSYNK.clear()


def _kjor(db, t, synk=None):
    sendt = []
    varsler.lagre_abonnement(db, SUB)
    fyrt = varsler.kjor_planlagte_jobber(db, t, synk=synk or (lambda: None), sender=lambda s, d: sendt.append(d))
    return fyrt, sendt


def _oura_kom(db):
    db.execute("INSERT OR REPLACE INTO oura_malinger (dato, type, verdi) VALUES (?, 'restitusjon_score', 82)", (DAG,))
    db.commit()


def test_kl_sju_kommer_paaminnelse_ikke_plan(db):
    fyrt, sendt = _kjor(db, datetime(2026, 11, 18, 7, 2, tzinfo=OSLO))
    assert "morgen" in fyrt and "dagsplan" not in fyrt
    assert "Oura" in sendt[0]
    assert db.execute("SELECT COUNT(*) FROM dagsmelding").fetchone()[0] == 0


def test_dagsplan_sendes_naar_oura_har_levert(db):
    _kjor(db, datetime(2026, 11, 18, 7, 2, tzinfo=OSLO))
    fyrt, sendt = _kjor(db, datetime(2026, 11, 18, 7, 15, tzinfo=OSLO), synk=lambda: _oura_kom(db))
    assert "dagsplan" in fyrt
    assert db.execute("SELECT COUNT(*) FROM dagsmelding").fetchone()[0] == 1


def test_dagsplan_venter_uten_oura(db):
    fyrt, _ = _kjor(db, datetime(2026, 11, 18, 8, 0, tzinfo=OSLO))
    assert "dagsplan" not in fyrt


def test_synk_maks_hvert_tiende_minutt(db):
    kall = []
    _kjor(db, datetime(2026, 11, 18, 7, 20, tzinfo=OSLO), synk=lambda: kall.append(1))
    _kjor(db, datetime(2026, 11, 18, 7, 25, tzinfo=OSLO), synk=lambda: kall.append(1))
    _kjor(db, datetime(2026, 11, 18, 7, 31, tzinfo=OSLO), synk=lambda: kall.append(1))
    assert len(kall) == 2


def test_dagsplan_senest_ved_fristen(db):
    fyrt, sendt = _kjor(db, datetime(2026, 11, 18, 10, 1, tzinfo=OSLO))
    assert "dagsplan" in fyrt
    assert db.execute("SELECT COUNT(*) FROM dagsmelding").fetchone()[0] == 1


def test_dagsplan_bare_en_gang(db):
    _oura_kom(db)
    assert "dagsplan" in _kjor(db, datetime(2026, 11, 18, 7, 30, tzinfo=OSLO))[0]
    assert "dagsplan" not in _kjor(db, datetime(2026, 11, 18, 7, 45, tzinfo=OSLO))[0]
    assert "dagsplan" not in _kjor(db, datetime(2026, 11, 18, 10, 5, tzinfo=OSLO))[0]


def test_ingenting_for_morgen(db):
    _oura_kom(db)
    assert _kjor(db, datetime(2026, 11, 18, 6, 40, tzinfo=OSLO))[0] == []


def test_dagsplan_ikke_sendt_hvis_appen_allerede_laget_den(db):
    """Åpnet han appen etter Oura-synk, er planen alt laget – da trengs ingen push."""
    _oura_kom(db)
    coach.hent_eller_lag_dagsmelding(db, datetime(2026, 11, 18).date(), naa=datetime(2026, 11, 18, 7, 10, tzinfo=OSLO))
    fyrt, _ = _kjor(db, datetime(2026, 11, 18, 7, 20, tzinfo=OSLO))
    assert "dagsplan" not in fyrt


def test_fristen_kan_endres(client):
    r = client.post("/api/innstillinger/varsler", json={"frist": "09:30"})
    assert r.status_code == 200 and r.json["frist"] == "09:30"
    client.post("/api/innstillinger/varsler", json=varsler.STANDARD_TIDER)


def test_i_dag_synker_oura_naar_dagens_tall_mangler(client, monkeypatch):
    kall = []
    monkeypatch.setattr(app_modul, "_synk_oura_hvis_mangler", lambda db, dato: kall.append(dato))
    client.get("/api/i-dag")
    assert kall == [livsstil.i_dag_oslo().isoformat()]
