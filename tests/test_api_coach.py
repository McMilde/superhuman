import pytest

import coach
import livsstil


@pytest.fixture(autouse=True)
def ingen_claude(monkeypatch):
    def feiler(*a, **k):
        raise coach.CoachUtilgjengelig("test")
    monkeypatch.setattr(coach, "sporr_claude", feiler)


def test_i_dag_uten_nokkel_gir_reserve(client):
    r = client.get("/api/i-dag")
    assert r.status_code == 200
    data = r.json
    assert data["melding"]["kilde"] == "reserve" and data["melding"]["tekst"]
    for felt in ("dato", "ukedag_navn", "dagssjekk", "treningsdag", "flytt_grunn", "middag",
                 "alkoholfri_rekke", "helg", "er_fredag_til_sondag"):
        assert felt in data


def test_i_dag_lagres_og_gjenbrukes(client, monkeypatch):
    client.get("/api/i-dag")
    kall = []
    monkeypatch.setattr(coach, "lag_dagsmelding", lambda *a, **k: kall.append(1) or {})
    client.get("/api/i-dag")
    assert kall == []


def test_mat_lager_plan_ved_behov(client):
    data = client.get("/api/mat").json
    assert len(data["middager"]) == 5 and data["handleliste"] and data["lunsj"]["brodtips"]


def test_bytt_middag_via_api(client):
    plan = client.get("/api/mat").json
    dag = plan["middager"][1]["dag"]
    ny = client.post("/api/mat/bytt", json={"dag": dag}).json
    assert ny["middager"][1]["navn"] != plan["middager"][1]["navn"]


def test_bytt_ugyldig_dag_400(client):
    client.get("/api/mat")
    assert client.post("/api/mat/bytt", json={"dag": "1999-01-01"}).status_code == 400


def test_chat_tom_tekst_400(client):
    assert client.post("/api/coach/chat", json={"tekst": "  "}).status_code == 400


def test_chat_svar_og_historikk(client):
    r = client.post("/api/coach/chat", json={"tekst": "Hei"})
    assert r.status_code == 200 and r.json["svar"]
    assert client.get("/api/coach/chat").json[0]["tekst"] == "Hei"


def test_vanskelig(client):
    assert client.post("/api/coach/vanskelig").json["tekst"]


def test_helg_lagrer_og_gir_tips(client, db):
    r = client.post("/api/helg", json={"planlagte_enheter": 4})
    assert r.status_code == 200 and r.json["planlagte_enheter"] == 4 and len(r.json["tips"]) == 3
    uke = livsstil.mandag_for(livsstil.i_dag_oslo()).isoformat()
    assert db.execute("SELECT planlagte_enheter FROM helgeplan WHERE uke_start = ?", (uke,)).fetchone()[0] == 4
    assert client.get("/api/i-dag").json["helg"]["planlagte_enheter"] == 4


@pytest.mark.parametrize("verdi", [-1, 31, "mange", None])
def test_helg_ugyldig_antall_400(client, verdi):
    assert client.post("/api/helg", json={"planlagte_enheter": verdi}).status_code == 400
