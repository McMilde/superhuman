"""Pakke 3: søndagssjekk med ukemål og tilgivende rekker."""
from datetime import date, datetime

import pytest

import coach
import livsstil
import varsler

OSLO = livsstil.OSLO
MAN = date(2026, 11, 16)


@pytest.fixture(autouse=True)
def ingen_claude(monkeypatch):
    def feiler(*a, **k):
        raise coach.CoachUtilgjengelig("test")
    monkeypatch.setattr(coach, "sporr_claude", feiler)


def _sett(db, dato, alkohol=False, fastet=False, trent=False, enheter=None):
    livsstil.lagre_dagssjekk(db, dato, fastet, alkohol, enheter, trent, False, "")


# ---- Tilgivende rekke ----

def test_en_alkoholdag_tilgis(db):
    for d in ("2026-11-16", "2026-11-17"):
        _sett(db, d)
    _sett(db, "2026-11-18", alkohol=True)
    _sett(db, "2026-11-19")
    s = livsstil.rekke_status(db, date(2026, 11, 19))
    assert s["naa"] == 3 and s["frikort_brukt"] is True


def test_to_glipper_innen_en_uke_bryter(db):
    _sett(db, "2026-11-16")
    _sett(db, "2026-11-17", alkohol=True)
    _sett(db, "2026-11-18")
    _sett(db, "2026-11-19", alkohol=True)
    s = livsstil.rekke_status(db, date(2026, 11, 19))
    assert s["naa"] == 0 and s["frikort_brukt"] is False


def test_frikort_fornyes_etter_en_uke(db):
    _sett(db, "2026-11-02")
    _sett(db, "2026-11-03", alkohol=True)  # frikort 1
    for d in ("2026-11-04", "2026-11-05", "2026-11-09", "2026-11-10"):
        _sett(db, d)
    _sett(db, "2026-11-11", alkohol=True)  # mer enn 7 dager senere – nytt frikort
    _sett(db, "2026-11-12")
    assert livsstil.rekke_status(db, date(2026, 11, 12))["naa"] == 6


def test_glipp_uten_rekke_tilgis_ikke(db):
    _sett(db, "2026-11-16", alkohol=True)
    _sett(db, "2026-11-17")
    s = livsstil.rekke_status(db, date(2026, 11, 17))
    assert s["naa"] == 1 and s["frikort_brukt"] is False


def test_rekke_status_har_beste(db):
    for d in ("2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"):
        _sett(db, d)
    _sett(db, "2026-11-09", alkohol=True)
    _sett(db, "2026-11-10", alkohol=True)
    _sett(db, "2026-11-11")
    s = livsstil.rekke_status(db, date(2026, 11, 11))
    assert s["beste"] == 4 and s["naa"] == 1


# ---- Ukestatistikk ----

def test_ukestatistikk(db):
    livsstil.lagre_ukeplan(db, MAN, ["2026-11-16", "2026-11-18", "2026-11-20"],
                           livsstil.RESERVE_MIDDAGER[:5], livsstil.RESERVE_LUNSJ, "reserve")
    _sett(db, "2026-11-16", fastet=True, trent=True)
    _sett(db, "2026-11-17", fastet=True)
    _sett(db, "2026-11-18", alkohol=True, enheter=2, trent=True)
    _sett(db, "2026-11-21", alkohol=True, enheter=4)
    db.execute("INSERT INTO vektlogg (dato, vekt_kg) VALUES ('2026-11-16', 100.4), ('2026-11-22', 99.8)")
    db.commit()
    st = livsstil.ukestatistikk(db, MAN)
    assert st["alkoholfrie_hverdager"] == 2 and st["registrerte_hverdager"] == 3
    assert st["fastedager"] == 2 and st["treningsdager"] == 2 and st["planlagte_treningsdager"] == 3
    assert st["helg_enheter"] == 4 and st["vekt_endring"] == pytest.approx(-0.6)


def test_ukestatistikk_uten_vekt(db):
    assert livsstil.ukestatistikk(db, MAN)["vekt_endring"] is None


# ---- Ukemål ----

def test_forslag_reserve_peker_paa_svakheter(db):
    _sett(db, "2026-11-17", alkohol=True, enheter=2)
    forslag = coach.ukemal_forslag(db, date(2026, 11, 23))
    assert len(forslag) == 3
    assert any("alkoholfri" in f.lower() for f in forslag)


def test_aktivt_ukemal_lager_forslag_ved_behov(db):
    m = livsstil.aktivt_ukemal(db, date(2026, 11, 18), lag_forslag=lambda c, u: ["A", "B", "C"])
    assert m["uke_start"] == "2026-11-16" and m["gjelder"] == "denne" and m["mal"] is None
    assert m["forslag"] == ["A", "B", "C"]


def test_aktivt_ukemal_sondag_viser_neste_uke_hvis_klar(db):
    livsstil.lagre_ukemal_forslag(db, date(2026, 11, 23), ["X", "Y", "Z"])
    m = livsstil.aktivt_ukemal(db, date(2026, 11, 22), lag_forslag=lambda c, u: ["A", "B", "C"])
    assert m["uke_start"] == "2026-11-23" and m["gjelder"] == "neste"
    assert m["statistikk"]["uke_start"] == "2026-11-16"


def test_velg_ukemal(db):
    livsstil.lagre_ukemal_forslag(db, MAN, ["A", "B", "C"])
    livsstil.velg_ukemal(db, MAN, "  Fast 5 dager  ")
    assert livsstil.aktivt_ukemal(db, date(2026, 11, 18))["mal"] == "Fast 5 dager"


def test_api_ukemal(client):
    data = client.get("/api/i-dag").json["ukemal"]
    assert len(data["forslag"]) == 3 and data["mal"] is None
    r = client.post("/api/ukemal", json={"uke_start": data["uke_start"], "mal": data["forslag"][0]})
    assert r.status_code == 200
    assert client.get("/api/i-dag").json["ukemal"]["mal"] == data["forslag"][0]


@pytest.mark.parametrize("data", [
    {"uke_start": "2020-01-06", "mal": "x"}, {"uke_start": None, "mal": "x"}, {"mal": "   "},
])
def test_api_ukemal_ugyldig(client, data):
    if "uke_start" not in data:
        data["uke_start"] = livsstil.mandag_for(livsstil.i_dag_oslo()).isoformat()
    assert client.post("/api/ukemal", json=data).status_code == 400


def test_coach_kjenner_ukemalet(db):
    livsstil.lagre_ukemal_forslag(db, MAN, ["A"])
    livsstil.velg_ukemal(db, MAN, "Fast minst 5 dager")
    assert "Fast minst 5 dager" in coach.lag_sammendrag(db, date(2026, 11, 18))


def test_sondagsjobb_lager_forslag_for_neste_uke(db):
    varsler.lagre_abonnement(db, {"endpoint": "https://push.example/ok", "keys": {"p256dh": "p", "auth": "a"}})
    sendt = []
    varsler.kjor_planlagte_jobber(db, datetime(2026, 11, 22, 18, 5, tzinfo=OSLO),
                                  synk=lambda: None, sender=lambda s, d: sendt.append(d))
    m = livsstil.aktivt_ukemal(db, date(2026, 11, 22))
    assert m["uke_start"] == "2026-11-23" and len(m["forslag"]) == 3
    assert "ukemål" in sendt[-1].lower()
