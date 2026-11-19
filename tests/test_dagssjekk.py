from datetime import date

import livsstil


def test_lagre_og_hent_dagssjekk(client):
    r = client.post("/api/dagssjekk", json={
        "dato": "2026-11-16", "fastet": True, "alkohol": True, "alkohol_enheter": "2,5",
        "trent": False, "syk": False,
    })
    assert r.status_code == 200 and r.json["alkohol_enheter"] == 2.5
    assert client.get("/api/dagssjekk?dato=2026-11-16").json["fastet"] == 1


def test_hent_uregistrert_dag_gir_null(client):
    assert client.get("/api/dagssjekk?dato=2026-11-10").json is None


def test_enheter_nullstilles_uten_alkohol(client):
    r = client.post("/api/dagssjekk", json={"dato": "2026-11-17", "alkohol": False, "alkohol_enheter": 4})
    assert r.json["alkohol_enheter"] is None


def test_ugyldig_dato_400(client):
    assert client.post("/api/dagssjekk", json={"dato": "i går"}).status_code == 400


def test_gammel_dagslogg_vises_som_trent(client, db):
    db.execute("INSERT INTO dagslogg (dato, gjennomfort) VALUES ('2026-08-22', 1)")
    db.commit()
    assert client.get("/api/dagssjekk?dato=2026-08-22").json["trent"] == 1
    dager = client.get("/api/historikk").json["dager"]
    assert any(d["dato"] == "2026-08-22" and d["trent"] for d in dager)


def _sett(db, dato, alkohol):
    livsstil.lagre_dagssjekk(db, dato, False, alkohol, None, False, False, "")


def test_alkoholfrie_hverdager_hopper_over_helg(db):
    _sett(db, "2026-11-12", True)   # torsdag
    for d in ("2026-11-13", "2026-11-14", "2026-11-15"):  # fre-søn
        _sett(db, d, True)
    _sett(db, "2026-11-16", False)  # mandag
    _sett(db, "2026-11-17", False)  # tirsdag
    assert livsstil.alkoholfrie_hverdager_pa_rad(db, date(2026, 11, 18)) == 2


def test_alkoholfri_rekke_teller_med_i_dag_nar_registrert(db):
    _sett(db, "2026-11-17", False)
    _sett(db, "2026-11-18", False)
    assert livsstil.alkoholfrie_hverdager_pa_rad(db, date(2026, 11, 18)) == 2


def test_alkoholfri_rekke_brytes_av_hull(db):
    _sett(db, "2026-11-16", False)
    # tirsdag 17 ikke registrert
    assert livsstil.alkoholfrie_hverdager_pa_rad(db, date(2026, 11, 18)) == 0


def test_oversikt_viser_trening_fra_dagssjekk(client, db):
    i_dag = livsstil.i_dag_oslo().isoformat()
    livsstil.lagre_dagssjekk(db, i_dag, False, False, None, True, False, "")
    uke = client.get("/api/oversikt").json["trening_uke"]
    assert uke[-1]["dato"] == i_dag and uke[-1]["gjennomfort"] is True
    assert "alkoholfri_rekke" in client.get("/api/oversikt").json
