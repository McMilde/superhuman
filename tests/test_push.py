import json
from types import SimpleNamespace

import pytest

import app as app_modul
import varsler

SUB = {"endpoint": "https://push.example/ok", "keys": {"p256dh": "p", "auth": "a"}}
SUB_UTLOPT = {"endpoint": "https://push.example/borte", "keys": {"p256dh": "p", "auth": "a"}}


def test_vapid_lages_en_gang(db):
    a = varsler.hent_eller_lag_vapid(db)
    b = varsler.hent_eller_lag_vapid(db)
    assert a == b and a[0].startswith("-----BEGIN") and len(a[1]) > 80


def test_abonner_ugyldig_400(client):
    assert client.post("/api/push/abonner", json={"endpoint": "x"}).status_code == 400


def test_abonner_ok(client, db):
    assert client.post("/api/push/abonner", json=SUB).status_code == 201
    assert db.execute("SELECT COUNT(*) FROM push_abonnement").fetchone()[0] == 1


class Utlopt(Exception):
    def __init__(self):
        super().__init__("gone")
        self.response = SimpleNamespace(status_code=410)


def test_send_sletter_utlopt_abonnement(db):
    varsler.lagre_abonnement(db, SUB)
    varsler.lagre_abonnement(db, SUB_UTLOPT)
    sendt = []

    def sender(sub_info, data):
        if sub_info["endpoint"].endswith("borte"):
            raise Utlopt()
        sendt.append(json.loads(data))

    assert varsler.send_til_alle(db, "Hei", "Tekst", "/#mat", sender=sender) == 1
    assert sendt == [{"tittel": "Hei", "tekst": "Tekst", "url": "/#mat"}]
    igjen = [r[0] for r in db.execute("SELECT endpoint FROM push_abonnement")]
    assert igjen == [SUB["endpoint"]]


def test_annen_feil_beholder_abonnement(db):
    varsler.lagre_abonnement(db, SUB)

    def sender(sub_info, data):
        raise RuntimeError("nettverk")

    assert varsler.send_til_alle(db, "Hei", "Tekst", sender=sender) == 0
    assert db.execute("SELECT COUNT(*) FROM push_abonnement").fetchone()[0] == 1


def test_sw_js_uten_innlogging(client, monkeypatch):
    monkeypatch.setattr(app_modul, "APP_PASSORD", "hemmelig")
    r = client.get("/sw.js")
    assert r.status_code == 200 and "javascript" in r.content_type
    assert r.headers.get("Service-Worker-Allowed") == "/"
    assert client.get("/api/push/nokkel").status_code == 302


def test_nokkel_rute(client):
    assert len(client.get("/api/push/nokkel").json["offentlig"]) > 80
