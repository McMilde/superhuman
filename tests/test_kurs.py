"""Pakke 6: minikurs – 30 leksjoner, én ny per dag."""
from datetime import date, timedelta

import pytest

import coach
import kurs

D1 = date(2026, 11, 23)


def test_kurset_har_30_hele_leksjoner():
    assert len(kurs.LEKSJONER) == 30
    for i, l in enumerate(kurs.LEKSJONER, start=1):
        assert l["nr"] == i and l["tittel"] and len(l["tekst"]) >= 2 and l["prov"]


def test_start_gir_leksjon_en(db):
    s = kurs.status(db, D1)
    assert s["dagens"]["nr"] == 1 and s["lest_i_dag"] is False and s["antall_lest"] == 0


def test_lese_samme_dag_laaser_neste(db):
    kurs.marker_lest(db, 1, D1)
    s = kurs.status(db, D1)
    assert s["lest_i_dag"] is True and s["dagens"]["nr"] == 1 and s["antall_lest"] == 1


def test_ny_dag_gir_neste(db):
    kurs.marker_lest(db, 1, D1)
    assert kurs.status(db, D1 + timedelta(days=1))["dagens"]["nr"] == 2


def test_hoppe_over_dager_gir_bare_neste(db):
    kurs.marker_lest(db, 1, D1)
    assert kurs.status(db, D1 + timedelta(days=5))["dagens"]["nr"] == 2


def test_kan_ikke_lese_frem_i_kurset(db):
    with pytest.raises(ValueError):
        kurs.marker_lest(db, 3, D1)
    kurs.marker_lest(db, 1, D1)
    with pytest.raises(ValueError):
        kurs.marker_lest(db, 2, D1)  # samme dag


def test_lese_samme_igjen_er_ok(db):
    kurs.marker_lest(db, 1, D1)
    kurs.marker_lest(db, 1, D1 + timedelta(days=1))
    assert kurs.status(db, D1 + timedelta(days=1))["antall_lest"] == 1


def test_fullfort_etter_30(db):
    for i in range(1, 31):
        kurs.marker_lest(db, i, D1 + timedelta(days=i))
    s = kurs.status(db, D1 + timedelta(days=40))
    assert s["fullfort"] is True and s["antall_lest"] == 30


def test_hent_leksjon_bare_lest_eller_dagens(db):
    assert kurs.hent_leksjon(db, 1, D1)["nr"] == 1
    assert kurs.hent_leksjon(db, 2, D1) is None
    kurs.marker_lest(db, 1, D1)
    assert kurs.hent_leksjon(db, 1, D1 + timedelta(days=3))["nr"] == 1


def test_api(client):
    s = client.get("/api/kurs").json
    assert s["dagens"]["nr"] == 1 and s["dagens"]["tekst"]
    assert client.post("/api/kurs/lest", json={"nr": 1}).status_code == 200
    assert client.get("/api/kurs").json["lest_i_dag"] is True
    assert client.post("/api/kurs/lest", json={"nr": 2}).status_code == 400
    assert client.get("/api/kurs/leksjon/1").status_code == 200
    assert client.get("/api/kurs/leksjon/5").status_code == 404
    assert [l["nr"] for l in client.get("/api/kurs").json["leste"]] == [1]


def test_coach_kjenner_dagens_leksjon(db):
    kurs.marker_lest(db, 1, D1)
    assert kurs.LEKSJONER[0]["tittel"] in coach.lag_sammendrag(db, D1)
