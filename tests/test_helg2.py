"""Pakke 2: Helgeplan 2.0 – teller, sluttidspunkt, hvis–så-planer, risikodag, mandagsnullstilling."""
from datetime import date, datetime

import pytest

import coach
import livsstil
import varsler

OSLO = livsstil.OSLO
SUB = {"endpoint": "https://push.example/ok", "keys": {"p256dh": "p", "auth": "a"}}


@pytest.fixture(autouse=True)
def ingen_claude(monkeypatch):
    def feiler(*a, **k):
        raise coach.CoachUtilgjengelig("test")
    monkeypatch.setattr(coach, "sporr_claude", feiler)


def _helg(db, uke_start, enheter=4, sluttid="22:00"):
    livsstil.lagre_helgeplan(db, uke_start, enheter, ["tips"], sluttid)


# ---- Teller ----

def test_pluss_en_lager_avkrysning(db):
    rad = livsstil.endre_enheter(db, "2026-11-20", 1)
    assert rad["alkohol"] == 1 and rad["alkohol_enheter"] == 1


def test_pluss_beholder_andre_felt(db):
    livsstil.lagre_dagssjekk(db, "2026-11-20", True, False, None, True, False, "notat")
    livsstil.endre_enheter(db, "2026-11-20", 1)
    rad = livsstil.endre_enheter(db, "2026-11-20", 1)
    assert rad["alkohol_enheter"] == 2 and rad["fastet"] == 1 and rad["trent"] == 1 and rad["notat"] == "notat"


def test_minus_til_null_fjerner_alkohol(db):
    livsstil.endre_enheter(db, "2026-11-20", 1)
    rad = livsstil.endre_enheter(db, "2026-11-20", -1)
    assert rad["alkohol"] == 0 and rad["alkohol_enheter"] is None


def test_minus_uten_rad_gjor_ingenting(db):
    assert livsstil.endre_enheter(db, "2026-11-20", -1) is None


def test_brukt_i_helgen_summerer_fre_til_son(db):
    livsstil.endre_enheter(db, "2026-11-19", 1)  # torsdag teller ikke
    livsstil.lagre_dagssjekk(db, "2026-11-20", False, True, 3, False, False, "")
    livsstil.lagre_dagssjekk(db, "2026-11-21", False, True, 2.5, False, False, "")
    assert livsstil.brukt_i_helgen(db, date(2026, 11, 16)) == 5.5


def test_api_enhet(client):
    dato = livsstil.i_dag_oslo().isoformat()
    r = client.post("/api/dagssjekk/enhet", json={"endring": 1})
    assert r.status_code == 200 and r.json["dagssjekk"]["alkohol_enheter"] == 1 and r.json["dagssjekk"]["dato"] == dato
    assert "brukt_i_helgen" in r.json


@pytest.mark.parametrize("endring", [0, 2, "x", None])
def test_api_enhet_ugyldig(client, endring):
    assert client.post("/api/dagssjekk/enhet", json={"endring": endring}).status_code == 400


# ---- Helgeplan med sluttid og hvis–så ----

def test_api_helg_lagrer_sluttid_og_gir_planforslag(client):
    r = client.post("/api/helg", json={"planlagte_enheter": 4, "sluttid": "21:30"})
    assert r.status_code == 200 and r.json["sluttid"] == "21:30"
    assert len(r.json["planforslag"]) == 3
    helg = client.get("/api/i-dag").json["helg"]
    assert helg["sluttid"] == "21:30" and helg["planer"] == [] and "brukt" in helg


def test_api_helg_standard_sluttid(client):
    assert client.post("/api/helg", json={"planlagte_enheter": 4}).json["sluttid"] == "22:00"


def test_api_helg_ugyldig_sluttid(client):
    assert client.post("/api/helg", json={"planlagte_enheter": 4, "sluttid": "kl 10"}).status_code == 400


def test_api_lagre_planer(client):
    client.post("/api/helg", json={"planlagte_enheter": 4})
    r = client.post("/api/helg/planer", json={"planer": ["Hvis A, så B", "  ", "Hvis C, så D"]})
    assert r.status_code == 200 and r.json["planer"] == ["Hvis A, så B", "Hvis C, så D"]
    assert client.get("/api/i-dag").json["helg"]["planer"] == ["Hvis A, så B", "Hvis C, så D"]


def test_api_lagre_planer_uten_helgeplan_400(client):
    assert client.post("/api/helg/planer", json={"planer": ["x"]}).status_code == 400


def test_hvis_saa_reserve_har_tre():
    assert len(coach.hvis_saa_forslag(None, 4)) == 3


# ---- Varsel på sluttidspunktet ----

def _kjor(db, t):
    sendt = []
    varsler.lagre_abonnement(db, SUB)
    fyrt = varsler.kjor_planlagte_jobber(db, t, synk=lambda: None, sender=lambda s, d: sendt.append(d))
    return fyrt, sendt


def test_sluttid_varsel_fredag(db):
    _helg(db, date(2026, 11, 16), 4, "22:00")
    livsstil.lagre_dagssjekk(db, "2026-11-20", False, True, 3, False, False, "")
    fyrt, sendt = _kjor(db, datetime(2026, 11, 20, 22, 5, tzinfo=OSLO))
    assert "sluttid" in fyrt and "3 av 4" in sendt[-1]


def test_sluttid_ikke_uten_helgeplan(db):
    fyrt, _ = _kjor(db, datetime(2026, 11, 20, 22, 5, tzinfo=OSLO))
    assert "sluttid" not in fyrt


def test_sluttid_ikke_paa_sondag(db):
    _helg(db, date(2026, 11, 16), 4, "22:00")
    fyrt, _ = _kjor(db, datetime(2026, 11, 22, 22, 5, tzinfo=OSLO))
    assert "sluttid" not in fyrt


def test_sluttid_etter_midnatt_regnes_ikke(db):
    _helg(db, date(2026, 11, 16), 4, "23:30")
    fyrt, _ = _kjor(db, datetime(2026, 11, 21, 0, 30, tzinfo=OSLO))
    assert "sluttid" not in fyrt


# ---- Risikodag ----

def test_risikodag_trenger_to_ganger(db):
    livsstil.lagre_dagssjekk(db, "2026-11-12", False, True, 2, False, False, "")  # torsdag
    assert livsstil.risikodag(db, date(2026, 11, 23)) is None
    livsstil.lagre_dagssjekk(db, "2026-11-05", False, True, 2, False, False, "")  # torsdag
    assert livsstil.risikodag(db, date(2026, 11, 23)) == 4


def test_risikodag_ignorerer_helg_og_gamle_data(db):
    for d in ("2026-11-14", "2026-11-15", "2026-11-21"):  # helg
        livsstil.lagre_dagssjekk(db, d, False, True, 2, False, False, "")
    for d in ("2026-08-03", "2026-08-10"):  # mandager for lenge siden
        livsstil.lagre_dagssjekk(db, d, False, True, 2, False, False, "")
    assert livsstil.risikodag(db, date(2026, 11, 23)) is None


def test_risikovarsel_paa_risikodag(db):
    for d in ("2026-11-05", "2026-11-12"):
        livsstil.lagre_dagssjekk(db, d, False, True, 2, False, False, "")
    fyrt, sendt = _kjor(db, datetime(2026, 11, 19, 16, 40, tzinfo=OSLO))
    assert "risiko" in fyrt and "torsdag" in sendt[-1].lower()
    fyrt2, _ = _kjor(db, datetime(2026, 11, 18, 16, 40, tzinfo=OSLO))
    assert "risiko" not in fyrt2


def test_risikovarsel_ikke_naar_allerede_krysset_av(db):
    for d in ("2026-11-05", "2026-11-12"):
        livsstil.lagre_dagssjekk(db, d, False, True, 2, False, False, "")
    livsstil.lagre_dagssjekk(db, "2026-11-19", False, False, None, False, False, "")
    fyrt, _ = _kjor(db, datetime(2026, 11, 19, 16, 40, tzinfo=OSLO))
    assert "risiko" in fyrt  # dytten handler om kvelden, ikke om avkrysning


# ---- Mandag etter tung helg ----

def test_helg_over_plan(db):
    _helg(db, date(2026, 11, 16), 4)
    livsstil.lagre_dagssjekk(db, "2026-11-21", False, True, 7, False, False, "")
    assert livsstil.helg_over_plan(db, date(2026, 11, 23)) == (4, 7)
    assert livsstil.helg_over_plan(db, date(2026, 11, 24)) is None  # bare mandag


def test_helg_innenfor_plan_gir_none(db):
    _helg(db, date(2026, 11, 16), 4)
    livsstil.lagre_dagssjekk(db, "2026-11-21", False, True, 3, False, False, "")
    assert livsstil.helg_over_plan(db, date(2026, 11, 23)) is None


def test_mandag_reserve_nullstiller_uten_skam(db):
    _helg(db, date(2026, 11, 16), 4)
    livsstil.lagre_dagssjekk(db, "2026-11-21", False, True, 7, False, False, "")
    m = coach.lag_dagsmelding(db, date(2026, 11, 23), False, None, None)
    assert "ny uke" in m["tekst"].lower()
