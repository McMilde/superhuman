"""Tester for funnene fra sluttgjennomgangen."""
from datetime import date, datetime
from pathlib import Path

import pytest

import app as app_modul
import coach
import livsstil
import varsler

OSLO = livsstil.OSLO
ROT = Path(__file__).resolve().parent.parent


def _feiler(*a, **k):
    raise coach.CoachUtilgjengelig("test")


# Funn 1: gunicorn sin 30-sekundersgrense dreper Claude-kall

def test_procfile_gir_tid_og_flere_traader():
    procfile = (ROT / "Procfile").read_text()
    assert "--timeout 180" in procfile and "--threads" in procfile


def test_claude_klient_har_kort_timeout(monkeypatch):
    fanget = {}

    class FalskKlient:
        def __init__(self, **kw):
            fanget.update(kw)
            raise RuntimeError("stopp her")

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", FalskKlient)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    with pytest.raises(coach.CoachUtilgjengelig):
        coach.sporr_claude("s", "m", None, "low")
    assert fanget["timeout"] <= 40 and fanget["max_retries"] <= 1


def test_i_dag_venter_ikke_paa_ukemeny(client, monkeypatch):
    monkeypatch.setattr(coach, "sporr_claude", _feiler)
    kalt = []
    monkeypatch.setattr(coach, "lag_ukeplan_med_claude", lambda *a, **k: kalt.append("synkron"))
    startet = []
    monkeypatch.setattr(app_modul, "_start_oppgradering", lambda uke_start: startet.append(uke_start))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    r = client.get("/api/i-dag")
    assert r.status_code == 200 and kalt == []
    assert startet == [livsstil.mandag_for(livsstil.i_dag_oslo())]
    assert client.get("/api/mat").json["kilde"] == "reserve"


def test_oppgrader_reserveplan_beholder_treningsdager(db, monkeypatch):
    man = date(2026, 11, 16)
    plan = livsstil.hent_eller_lag_ukeplan(db, man)
    m = coach.Middag(navn="Ny", minutter=20, beskrivelse="b", ingredienser=["Løk"])
    meny = coach.Ukemeny(middager=[m.model_copy(update={"navn": f"Ny {i}"}) for i in range(5)],
                         lunsj=m, brodtips=["Egg"], antall_trening=5)
    monkeypatch.setattr(coach, "sporr_claude", lambda *a, **k: meny)
    ny = coach.oppgrader_ukeplan(db, man)
    assert ny["kilde"] == "claude" and ny["treningsdager"] == plan["treningsdager"]
    assert ny["middager"][0]["navn"] == "Ny 0"


def test_oppgrader_lar_planen_staa_naar_claude_feiler(db, monkeypatch):
    man = date(2026, 11, 16)
    livsstil.hent_eller_lag_ukeplan(db, man)
    monkeypatch.setattr(coach, "sporr_claude", _feiler)
    assert coach.oppgrader_ukeplan(db, man) is None
    assert livsstil.hent_ukeplan(db, man)["kilde"] == "reserve"


# Funn 2: tidlig åpning låser dagen før Oura-data finnes

def test_tidlig_aapning_uten_oura_lagres_ikke(db, monkeypatch):
    monkeypatch.setattr(coach, "sporr_claude", _feiler)
    ons = date(2026, 11, 18)
    livsstil.hent_eller_lag_ukeplan(db, livsstil.mandag_for(ons))
    m = coach.hent_eller_lag_dagsmelding(db, ons, naa=datetime(2026, 11, 18, 6, 30, tzinfo=OSLO))
    assert m["treningsdag"] == 1
    assert db.execute("SELECT COUNT(*) FROM dagsmelding").fetchone()[0] == 0


def test_morgenjobb_flytter_trening_ved_lav_restitusjon_etter_tidlig_aapning(db, monkeypatch):
    monkeypatch.setattr(coach, "sporr_claude", _feiler)
    ons = date(2026, 11, 18)
    livsstil.hent_eller_lag_ukeplan(db, livsstil.mandag_for(ons))
    coach.hent_eller_lag_dagsmelding(db, ons, naa=datetime(2026, 11, 18, 6, 30, tzinfo=OSLO))
    db.execute("INSERT INTO oura_malinger (dato, type, verdi) VALUES ('2026-11-18', 'restitusjon_score', 55)")
    db.commit()
    m = coach.hent_eller_lag_dagsmelding(db, ons, naa=datetime(2026, 11, 18, 7, 5, tzinfo=OSLO))
    assert m["treningsdag"] == 0 and m["flyttet_fra"]


def test_for_fristen_uten_oura_lagres_ikke(db, monkeypatch):
    monkeypatch.setattr(coach, "sporr_claude", _feiler)
    coach.hent_eller_lag_dagsmelding(db, date(2026, 11, 18), naa=datetime(2026, 11, 18, 9, 0, tzinfo=OSLO))
    assert db.execute("SELECT COUNT(*) FROM dagsmelding").fetchone()[0] == 0


def test_etter_fristen_uten_oura_lagres(db, monkeypatch):
    monkeypatch.setattr(coach, "sporr_claude", _feiler)
    coach.hent_eller_lag_dagsmelding(db, date(2026, 11, 18), naa=datetime(2026, 11, 18, 10, 5, tzinfo=OSLO))
    assert db.execute("SELECT COUNT(*) FROM dagsmelding").fetchone()[0] == 1


# Funn 4 (oppgradert): push uten nettverkstidsavbrudd kan henge planleggeren

def test_webpush_har_timeout(db, monkeypatch):
    fanget = {}
    import pywebpush
    monkeypatch.setattr(pywebpush, "webpush", lambda **kw: fanget.update(kw))
    varsler.lagre_abonnement(db, {"endpoint": "https://push.example/x", "keys": {"p256dh": "p", "auth": "a"}})
    varsler.send_til_alle(db, "t", "x")
    assert fanget.get("timeout") == 15
