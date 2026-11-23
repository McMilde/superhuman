"""Pakke 1: hva alkoholen gjør med deg (effekt, beste rekke, penger/kalorier spart)."""
from datetime import date, timedelta

import pytest

import coach
import livsstil


def _sett(db, dato, alkohol, enheter=None):
    livsstil.lagre_dagssjekk(db, dato, False, alkohol, enheter, False, False, "")


def _oura(db, dato, restitusjon, sovn):
    db.execute("INSERT OR REPLACE INTO oura_malinger (dato, type, verdi) VALUES (?, 'restitusjon_score', ?)", (dato, restitusjon))
    db.execute("INSERT OR REPLACE INTO oura_malinger (dato, type, verdi) VALUES (?, 'sovn_score', ?)", (dato, sovn))
    db.commit()


# ---- Beste rekke ----

def test_beste_rekke_ingen_data(db):
    assert livsstil.beste_alkoholfrie_rekke(db, date(2026, 11, 23)) == 0


def test_beste_rekke_husker_lengste(db):
    for d in ("2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"):  # man-tor uke 1
        _sett(db, d, False)
    _sett(db, "2026-11-12", True)  # torsdag uke 2 bryter
    for d in ("2026-11-16", "2026-11-17"):
        _sett(db, d, False)
    assert livsstil.beste_alkoholfrie_rekke(db, date(2026, 11, 18)) == 4


def test_beste_rekke_hull_bryter(db):
    _sett(db, "2026-11-02", False)
    _sett(db, "2026-11-04", False)  # tirsdag mangler
    assert livsstil.beste_alkoholfrie_rekke(db, date(2026, 11, 5)) == 1


def test_beste_rekke_hopper_over_helg(db):
    for d in ("2026-11-05", "2026-11-09", "2026-11-10"):  # tor, (fre-søn ikke registrert), man, tir
        _sett(db, d, False)
    assert livsstil.beste_alkoholfrie_rekke(db, date(2026, 11, 11)) == 3


# ---- Effekt på kroppen (dagen etter) ----

def _bygg_effektdata(db, antall_med, antall_uten):
    start = date(2026, 9, 1)
    d = start
    for i in range(antall_med + antall_uten):
        alkohol = i < antall_med
        _sett(db, d.isoformat(), alkohol, 4 if alkohol else None)
        _oura(db, (d + timedelta(days=1)).isoformat(), 60 if alkohol else 80, 70 if alkohol else 82)
        d += timedelta(days=2)


def test_effekt_for_lite_data(db):
    _bygg_effektdata(db, 3, 6)
    e = livsstil.alkohol_effekt(db, date(2026, 11, 23))
    assert e["nok_data"] is False and e["trengs_med"] == 2 and e["trengs_uten"] == 0


def test_effekt_regner_ut_dagen_etter(db):
    _bygg_effektdata(db, 5, 6)
    e = livsstil.alkohol_effekt(db, date(2026, 11, 23))
    assert e["nok_data"] is True
    assert e["restitusjon_med"] == 60 and e["restitusjon_uten"] == 80
    assert e["sovn_med"] == 70 and e["sovn_uten"] == 82
    assert e["dager_med"] == 5 and e["dager_uten"] == 6


def test_effekt_hopper_over_dager_uten_oura(db):
    for i in range(6):
        _sett(db, (date(2026, 10, 1) + timedelta(days=i)).isoformat(), i % 2 == 0)
    e = livsstil.alkohol_effekt(db, date(2026, 11, 23))
    assert e["nok_data"] is False and e["trengs_med"] == 5 and e["trengs_uten"] == 5


# ---- Penger og kalorier spart ----

def test_spart_uten_utgangspunkt_er_none(db):
    assert livsstil.alkohol_spart(db) is None


def test_spart_regner_kroner_og_kalorier(db):
    livsstil.lagre_alkohol_utgangspunkt(db, 14, 40)
    for i in range(7):
        _sett(db, (date(2026, 11, 16) + timedelta(days=i)).isoformat(), i == 5, 2 if i == 5 else None)
    s = livsstil.alkohol_spart(db)
    assert s["enheter_spart"] == 12
    assert s["kr"] == 480 and s["kalorier"] == 1200
    assert s["kg"] == pytest.approx(0.16, abs=0.01)
    assert s["fra_dato"] == "2026-11-16"


def test_spart_alkohol_uten_antall_regnes_som_to(db):
    livsstil.lagre_alkohol_utgangspunkt(db, 7, 40)
    _sett(db, "2026-11-16", True)
    assert livsstil.alkohol_spart(db)["enheter_spart"] == -1


# ---- API ----

def test_api_innsikt(client):
    data = client.get("/api/alkohol-innsikt").json
    for felt in ("rekke", "beste_rekke", "effekt", "spart", "utgangspunkt"):
        assert felt in data
    assert data["spart"] is None


def test_api_lagre_utgangspunkt(client):
    r = client.post("/api/alkohol-innsikt/utgangspunkt", json={"enheter_per_uke": "15", "kr_per_enhet": "45,5"})
    assert r.status_code == 200
    assert client.get("/api/alkohol-innsikt").json["utgangspunkt"] == {"enheter_per_uke": 15, "kr_per_enhet": 45.5}


@pytest.mark.parametrize("data", [
    {"enheter_per_uke": "mange"}, {"enheter_per_uke": -1}, {"enheter_per_uke": 500}, {"enheter_per_uke": 10, "kr_per_enhet": 0},
])
def test_api_ugyldig_utgangspunkt_400(client, data):
    assert client.post("/api/alkohol-innsikt/utgangspunkt", json=data).status_code == 400


# ---- Coachen får vite om effekten ----

def test_sammendrag_nevner_effekt(db):
    _bygg_effektdata(db, 5, 5)
    tekst = coach.lag_sammendrag(db, date(2026, 11, 23))
    assert "restitusjon dagen etter alkohol" in tekst.lower()
