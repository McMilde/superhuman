import pytest


@pytest.mark.parametrize("url", [
    "/api/dag", "/api/uke", "/api/ovelser", "/api/fysio", "/api/varsel", "/api/styrke-logg/kneboy",
])
def test_treningsplan_ruter_er_fjernet(client, url):
    assert client.get(url).status_code == 404


def test_oversikt_og_backup_virker_fortsatt(client):
    assert client.get("/api/oversikt?dager=30").status_code == 200
    assert client.get("/api/backup").status_code == 200


def test_init_db_lar_gamle_tabeller_sta(db):
    navn = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"dagslogg", "vektlogg", "innstillinger"} <= navn
