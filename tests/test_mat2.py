"""Pakke 4: smartere mat – vurderinger, «hva har vi?» og søndagsprep."""
from datetime import date

import pytest

import coach
import livsstil

MAN = date(2026, 11, 16)


@pytest.fixture(autouse=True)
def ingen_claude(monkeypatch):
    def feiler(*a, **k):
        raise coach.CoachUtilgjengelig("test")
    monkeypatch.setattr(coach, "sporr_claude", feiler)


# ---- Vurderinger ----

def test_vurder_og_hent(db):
    livsstil.vurder_middag(db, "Taco i skål", 1)
    livsstil.vurder_middag(db, "Fiskegrateng light", -1)
    livsstil.vurder_middag(db, "fiskegrateng LIGHT", -1)
    v = livsstil.hent_vurderinger(db)
    assert v["favoritter"] == ["Taco i skål"] and v["unnga"] == ["Fiskegrateng light"]


def test_vurdering_null_fjerner(db):
    livsstil.vurder_middag(db, "Taco i skål", 1)
    livsstil.vurder_middag(db, "Taco i skål", 0)
    assert livsstil.hent_vurderinger(db)["favoritter"] == []


def test_ugyldig_vurdering(db):
    with pytest.raises(ValueError):
        livsstil.vurder_middag(db, "Taco", 5)
    with pytest.raises(ValueError):
        livsstil.vurder_middag(db, "  ", 1)


def test_reserveplan_hopper_over_unngaa(db):
    for m in livsstil.RESERVE_MIDDAGER[:6]:
        livsstil.vurder_middag(db, m["navn"], -1)
    plan = livsstil.lag_reserveplan(db, MAN)
    unnga = {m["navn"] for m in livsstil.RESERVE_MIDDAGER[:6]}
    assert len(plan["middager"]) == 5 and not unnga & {m["navn"] for m in plan["middager"]}


def test_bytt_reserve_hopper_over_unngaa(db):
    plan = livsstil.hent_eller_lag_ukeplan(db, MAN)
    i_planen = {m["navn"] for m in plan["middager"]}
    ledige = [m["navn"] for m in livsstil.RESERVE_MIDDAGER if m["navn"] not in i_planen]
    livsstil.vurder_middag(db, ledige[0], -1)
    ny = coach.bytt_middag(db, MAN, "2026-11-16")
    assert livsstil.middag_for_dag(ny, "2026-11-16")["navn"] == ledige[1]


def test_menyprompt_nevner_favoritter_og_unngaa(db, monkeypatch):
    livsstil.vurder_middag(db, "Taco i skål", 1)
    livsstil.vurder_middag(db, "Fiskegrateng light", -1)
    sett = {}

    def fang(system, melding, *a, **k):
        sett["melding"] = melding
        raise coach.CoachUtilgjengelig("stopp")
    monkeypatch.setattr(coach, "sporr_claude", fang)
    coach.lag_ukeplan_med_claude(db, MAN)
    assert "Taco i skål" in sett["melding"] and "Fiskegrateng light" in sett["melding"]


def test_api_vurder(client):
    assert client.post("/api/mat/vurder", json={"navn": "Taco i skål", "vurdering": 1}).status_code == 200
    data = client.get("/api/mat").json
    assert data["vurderinger"]["favoritter"] == ["Taco i skål"]


@pytest.mark.parametrize("data", [{"navn": "x", "vurdering": 3}, {"navn": "", "vurdering": 1}, {"navn": "x"}])
def test_api_vurder_ugyldig(client, data):
    assert client.post("/api/mat/vurder", json=data).status_code == 400


# ---- Hva har vi? ----

def test_hva_har_vi_reserve_velger_mest_overlapp(db):
    m = coach.middag_fra_kjoleskap(db, "laks, brokkoli, poteter og sitron")
    assert m["navn"] == "Laks i ovn med potet og brokkoli" and m["kilde"] == "reserve"


def test_hva_har_vi_reserve_hopper_over_unngaa(db):
    livsstil.vurder_middag(db, "Laks i ovn med potet og brokkoli", -1)
    assert coach.middag_fra_kjoleskap(db, "laks brokkoli poteter")["navn"] != "Laks i ovn med potet og brokkoli"


def test_hva_har_vi_claude(db, monkeypatch):
    monkeypatch.setattr(coach, "sporr_claude", lambda *a, **k: coach.Middag(
        navn="Eggerøre med skinke", minutter=10, beskrivelse="b", ingredienser=["Egg", "Skinke"]))
    m = coach.middag_fra_kjoleskap(db, "egg og skinke")
    assert m["navn"] == "Eggerøre med skinke" and m["kilde"] == "claude"


def test_api_hva_har_vi(client):
    r = client.post("/api/mat/hva-har-vi", json={"tekst": "kylling, ris"})
    assert r.status_code == 200 and r.json["navn"]
    assert client.post("/api/mat/hva-har-vi", json={"tekst": " "}).status_code == 400


def test_bruk_som_dagens_middag(db):
    plan = livsstil.hent_eller_lag_ukeplan(db, MAN)
    ny = {"navn": "Eggerøre", "minutter": 10, "beskrivelse": "b", "ingredienser": ["Egg"]}
    oppdatert = livsstil.sett_middag(db, MAN, "2026-11-18", ny)
    assert livsstil.middag_for_dag(oppdatert, "2026-11-18")["navn"] == "Eggerøre"
    assert oppdatert["treningsdager"] == plan["treningsdager"]
    with pytest.raises(ValueError):
        livsstil.sett_middag(db, MAN, "2026-11-21", ny)


def test_api_bruk_middag(client):
    plan = client.get("/api/mat").json
    dag = plan["middager"][2]["dag"]
    r = client.post("/api/mat/bruk", json={"dag": dag, "middag": {"navn": "Eggerøre", "minutter": 10,
                                                                   "beskrivelse": "b", "ingredienser": ["Egg"]}})
    assert r.status_code == 200 and r.json["middager"][2]["navn"] == "Eggerøre"
    assert client.post("/api/mat/bruk", json={"dag": dag, "middag": {"navn": ""}}).status_code == 400


# ---- Søndagsprep ----

def test_prep_steg_finnes_alltid(client):
    lunsj = client.get("/api/mat").json["lunsj"]
    assert len(lunsj["steg"]) >= 4


def test_claude_meny_tar_med_steg(db, monkeypatch):
    m = coach.Middag(navn="Rett", minutter=20, beskrivelse="b", ingredienser=["Løk"])
    meny = coach.Ukemeny(middager=[m.model_copy(update={"navn": f"R{i}"}) for i in range(5)], lunsj=m,
                         brodtips=["Egg"], antall_trening=3, lunsj_steg=["Steg 1", "Steg 2", "Steg 3", "Steg 4"])
    monkeypatch.setattr(coach, "sporr_claude", lambda *a, **k: meny)
    plan = coach.lag_ukeplan_med_claude(db, MAN)
    assert plan["lunsj"]["steg"] == ["Steg 1", "Steg 2", "Steg 3", "Steg 4"]
