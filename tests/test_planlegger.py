from datetime import datetime, timedelta

import livsstil
import varsler

OSLO = livsstil.OSLO
SUB = {"endpoint": "https://push.example/ok", "keys": {"p256dh": "p", "auth": "a"}}


class Fake:
    def __init__(self):
        self.sendt = []

    def __call__(self, sub_info, data):
        self.sendt.append(data)


def _kjor(db, t, synk=None):
    fake = Fake()
    varsler.lagre_abonnement(db, SUB)
    fyrt = varsler.kjor_planlagte_jobber(db, t, synk=synk or (lambda: None), sender=fake)
    return fyrt, fake


def test_morgen_sendes_en_gang_i_vinduet(db):
    t = datetime(2026, 11, 18, 7, 20, tzinfo=OSLO)
    fyrt, fake = _kjor(db, t)
    assert "morgen" in fyrt and len(fake.sendt) == 1
    fyrt2, _ = _kjor(db, t + timedelta(minutes=1))
    assert "morgen" not in fyrt2


def test_morgen_sendes_ikke_for_sent(db):
    fyrt, _ = _kjor(db, datetime(2026, 11, 18, 23, 0, tzinfo=OSLO))
    assert "morgen" not in fyrt


def test_morgen_ikke_for_tidspunktet(db):
    fyrt, _ = _kjor(db, datetime(2026, 11, 18, 6, 59, tzinfo=OSLO))
    assert fyrt == []


def test_kveld_hoppes_over_nar_dagen_er_krysset_av(db):
    livsstil.lagre_dagssjekk(db, "2026-11-18", True, False, None, True, False, "")
    fyrt, fake = _kjor(db, datetime(2026, 11, 18, 21, 5, tzinfo=OSLO))
    assert "kveld" not in fyrt and fake.sendt == []


def test_kveld_sendes_nar_ikke_krysset_av(db):
    fyrt, fake = _kjor(db, datetime(2026, 11, 18, 21, 5, tzinfo=OSLO))
    assert "kveld" in fyrt and "Kryss av dagen" in fake.sendt[0]


def test_helg_bare_fredag(db):
    assert "helg" not in _kjor(db, datetime(2026, 11, 19, 15, 10, tzinfo=OSLO))[0]
    assert "helg" in _kjor(db, datetime(2026, 11, 20, 15, 10, tzinfo=OSLO))[0]


def test_middag_ikke_i_helgen(db):
    assert "middag" in _kjor(db, datetime(2026, 11, 18, 15, 40, tzinfo=OSLO))[0]
    assert "middag" not in _kjor(db, datetime(2026, 11, 21, 15, 40, tzinfo=OSLO))[0]


def test_sondag_lager_neste_ukeplan_og_oppsummering(db):
    fyrt, _ = _kjor(db, datetime(2026, 11, 22, 18, 5, tzinfo=OSLO))
    assert "sondag" in fyrt
    assert db.execute("SELECT 1 FROM ukeplan WHERE uke_start = '2026-11-23'").fetchone()
    assert db.execute("SELECT oppsummering FROM helgeplan WHERE uke_start = '2026-11-16'").fetchone()[0]


def test_synk_feil_stopper_ikke_morgen(db):
    def synk():
        raise RuntimeError("Withings nede")
    fyrt, _ = _kjor(db, datetime(2026, 11, 18, 7, 1, tzinfo=OSLO), synk=synk)
    assert "morgen" in fyrt


def test_egne_tider_brukes(db):
    varsler.lagre_tider(db, {"morgen": "06:15"})
    try:
        assert "morgen" in _kjor(db, datetime(2026, 11, 18, 6, 20, tzinfo=OSLO))[0]
    finally:
        varsler.lagre_tider(db, varsler.STANDARD_TIDER)


def test_tider_standard_og_lagring(client):
    assert client.get("/api/innstillinger/varsler").json == varsler.STANDARD_TIDER
    r = client.post("/api/innstillinger/varsler", json={"kveld": "22:00", "ukjent": "01:00"})
    assert r.json["kveld"] == "22:00" and "ukjent" not in r.json
    client.post("/api/innstillinger/varsler", json=varsler.STANDARD_TIDER)


def test_ugyldig_tid_400(client):
    assert client.post("/api/innstillinger/varsler", json={"morgen": "25:00"}).status_code == 400
