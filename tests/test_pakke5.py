"""Pakke 5 (Oura-økter → Trent, husk å veie deg) og registrering bakover i tid."""
from datetime import date, datetime, timedelta

import pytest

import app as app_modul
import livsstil
import varsler

OSLO = livsstil.OSLO


# ---- Oura-økter ----

OURA_SVAR = {"data": [
    {"id": "a1", "activity": "rowing", "day": "2026-11-20", "calories": 210, "intensity": "moderate",
     "start_datetime": "2026-11-20T17:00:00+01:00", "end_datetime": "2026-11-20T17:32:00+01:00"},
    {"id": "a2", "activity": "walking", "day": "2026-11-21", "calories": 40, "intensity": "easy",
     "start_datetime": "2026-11-21T08:00:00+01:00", "end_datetime": "2026-11-21T08:09:00+01:00"},
    {"id": "a3", "activity": "running", "day": None, "start_datetime": None, "end_datetime": None},
]}


def test_tolk_oura_okter():
    okter = livsstil.tolk_oura_okter(OURA_SVAR)
    assert okter == [
        {"id": "a1", "dato": "2026-11-20", "aktivitet": "rowing", "minutter": 32, "kalorier": 210, "intensitet": "moderate"},
        {"id": "a2", "dato": "2026-11-21", "aktivitet": "walking", "minutter": 9, "kalorier": 40, "intensitet": "easy"},
    ]


def test_okt_krysser_av_trent_paa_registrert_dag(db):
    livsstil.lagre_dagssjekk(db, "2026-11-20", True, False, None, False, False, "")
    livsstil.lagre_oura_okter(db, livsstil.tolk_oura_okter(OURA_SVAR))
    livsstil.bruk_oura_okter(db)
    assert livsstil.hent_dagssjekk(db, "2026-11-20")["trent"] == 1
    assert livsstil.hent_dagssjekk(db, "2026-11-20")["fastet"] == 1


def test_kort_okt_teller_ikke(db):
    livsstil.lagre_dagssjekk(db, "2026-11-21", False, False, None, False, False, "")
    livsstil.lagre_oura_okter(db, livsstil.tolk_oura_okter(OURA_SVAR))
    livsstil.bruk_oura_okter(db)
    assert livsstil.hent_dagssjekk(db, "2026-11-21")["trent"] == 0


def test_okt_lager_ikke_ny_dag(db):
    livsstil.lagre_oura_okter(db, livsstil.tolk_oura_okter(OURA_SVAR))
    livsstil.bruk_oura_okter(db)
    assert livsstil.hent_dagssjekk(db, "2026-11-20") is None


def test_okt_brukes_naar_dagen_registreres_senere(db):
    livsstil.lagre_oura_okter(db, livsstil.tolk_oura_okter(OURA_SVAR))
    livsstil.bruk_oura_okter(db)
    livsstil.lagre_dagssjekk(db, "2026-11-20", False, False, None, False, False, "")
    livsstil.bruk_oura_okter(db)
    assert livsstil.hent_dagssjekk(db, "2026-11-20")["trent"] == 1


def test_fjernet_kryss_settes_ikke_tilbake(db):
    livsstil.lagre_dagssjekk(db, "2026-11-20", False, False, None, False, False, "")
    livsstil.lagre_oura_okter(db, livsstil.tolk_oura_okter(OURA_SVAR))
    livsstil.bruk_oura_okter(db)
    livsstil.lagre_dagssjekk(db, "2026-11-20", False, False, None, False, False, "")  # han tar bort krysset
    livsstil.lagre_oura_okter(db, livsstil.tolk_oura_okter(OURA_SVAR))  # samme økt synkes igjen
    livsstil.bruk_oura_okter(db)
    assert livsstil.hent_dagssjekk(db, "2026-11-20")["trent"] == 0


def test_okter_for_dato(db):
    livsstil.lagre_oura_okter(db, livsstil.tolk_oura_okter(OURA_SVAR))
    assert livsstil.oura_okter_for_dato(db, "2026-11-20") == [
        {"aktivitet": "Roing", "minutter": 32, "teller": True}]


def test_oura_connect_ber_om_okt_tilgang(client, monkeypatch):
    monkeypatch.setattr(app_modul, "OURA_CLIENT_ID", "x")
    r = client.get("/oura/connect")
    assert "workout" in r.headers["Location"]


# ---- Husk å veie deg ----

SUB = {"endpoint": "https://push.example/ok", "keys": {"p256dh": "p", "auth": "a"}}


def _morgen(db):
    sendt = []
    varsler.lagre_abonnement(db, SUB)
    varsler.kjor_planlagte_jobber(db, datetime(2026, 11, 18, 7, 10, tzinfo=OSLO),
                                  synk=lambda: None, sender=lambda s, d: sendt.append(d))
    return sendt[-1]


def test_morgenvarsel_minner_om_veiing(db):
    assert "veie deg" in _morgen(db)


def test_morgenvarsel_uten_veiing_naar_veid(db):
    db.execute("INSERT INTO vektlogg (dato, vekt_kg) VALUES ('2026-11-18', 99.5)")
    db.commit()
    assert "veie deg" not in _morgen(db)


# ---- Registrering bakover i tid ----

def test_kan_ikke_registrere_fremtiden(client):
    i_morgen = (livsstil.i_dag_oslo() + timedelta(days=1)).isoformat()
    assert client.post("/api/dagssjekk", json={"dato": i_morgen, "trent": True}).status_code == 400


def test_kan_registrere_i_gaar(client):
    i_gaar = (livsstil.i_dag_oslo() - timedelta(days=1)).isoformat()
    r = client.post("/api/dagssjekk", json={"dato": i_gaar, "alkohol": True, "alkohol_enheter": 1})
    assert r.status_code == 200 and r.json["dato"] == i_gaar


def test_dag_detaljer(client, db):
    i_gaar = (livsstil.i_dag_oslo() - timedelta(days=1)).isoformat()
    livsstil.lagre_oura_okter(db, [{"id": "z", "dato": i_gaar, "aktivitet": "cycling", "minutter": 45,
                                    "kalorier": 300, "intensitet": "hard"}])
    data = client.get(f"/api/dag-detaljer?dato={i_gaar}").json
    assert data["dagssjekk"] is None and data["oura_okter"][0]["aktivitet"] == "Sykling"
    assert "oura_okt_tilgang" in data


def test_dag_detaljer_ugyldig_dato(client):
    assert client.get("/api/dag-detaljer?dato=tull").status_code == 400
