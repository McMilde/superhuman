from datetime import date

import pytest

import coach
import livsstil

MAN = date(2026, 11, 16)


def _feiler(*a, **k):
    raise coach.CoachUtilgjengelig("test")


@pytest.fixture(autouse=True)
def ingen_claude(monkeypatch):
    monkeypatch.setattr(coach, "sporr_claude", _feiler)


def test_sporr_claude_uten_nokkel_gir_utilgjengelig(monkeypatch):
    monkeypatch.undo()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(coach.CoachUtilgjengelig):
        coach.sporr_claude("s", "m", None, "low")


def test_dagsmelding_reserve_uten_nokkel(db):
    m = coach.lag_dagsmelding(db, date(2026, 11, 18), True, None, {"navn": "Kyllingwok"})
    assert m["tittel"] == "I DAG ER DET TRENINGSDAG 💪" and m["kilde"] == "reserve"
    assert "Kyllingwok" in m["tekst"]


def test_dagsmelding_reserve_nevner_flytting(db):
    m = coach.lag_dagsmelding(db, date(2026, 11, 18), False, "Lav restitusjon.", None)
    assert "Lav restitusjon." in m["tekst"]


def test_dagsmelding_bruker_claude(db, monkeypatch):
    monkeypatch.setattr(coach, "sporr_claude", lambda *a, **k: coach.Dagsmelding(tittel="God morgen", tekst="Hei"))
    m = coach.lag_dagsmelding(db, date(2026, 11, 19), False, None, None)
    assert m == {"tittel": "God morgen", "tekst": "Hei", "kilde": "claude"}


def test_treningsdag_tittel_tvinges_selv_med_claude(db, monkeypatch):
    monkeypatch.setattr(coach, "sporr_claude", lambda *a, **k: coach.Dagsmelding(tittel="Hei", tekst="Tekst"))
    assert coach.lag_dagsmelding(db, date(2026, 11, 19), True, None, None)["tittel"] == "I DAG ER DET TRENINGSDAG 💪"


def _ukemeny(antall):
    m = coach.Middag(navn="Rett", minutter=20, beskrivelse="b", ingredienser=["Løk"])
    return coach.Ukemeny(
        middager=[m.model_copy(update={"navn": f"Rett {i}"}) for i in range(5)],
        lunsj=m, brodtips=["Egg"], antall_trening=antall,
    )


def test_ukeplan_claude_klemmer_antall(db, monkeypatch):
    monkeypatch.setattr(coach, "sporr_claude", lambda *a, **k: _ukemeny(9))
    plan = coach.lag_ukeplan_med_claude(db, MAN)
    assert plan["kilde"] == "claude" and plan["antall_trening"] == 4
    assert len(plan["treningsdager"]) == 4 and plan["lunsj"]["brodtips"] == ["Egg"]


def test_ukeplan_faller_tilbake(db):
    assert coach.lag_ukeplan_med_claude(db, MAN)["kilde"] == "reserve"


def test_bytt_middag_reserve_gir_ny_og_oppdatert_handleliste(db):
    plan = livsstil.hent_eller_lag_ukeplan(db, MAN)
    gamle = {m["navn"] for m in plan["middager"]}
    ny = coach.bytt_middag(db, MAN, "2026-11-17")
    ny_middag = livsstil.middag_for_dag(ny, "2026-11-17")
    assert ny_middag["navn"] not in gamle
    assert ny_middag["ingredienser"][0] in ny["handleliste"]


def test_bytt_middag_med_claude(db, monkeypatch):
    livsstil.hent_eller_lag_ukeplan(db, MAN)
    monkeypatch.setattr(coach, "sporr_claude", lambda *a, **k: coach.Middag(
        navn="Fiskeboller", minutter=15, beskrivelse="b", ingredienser=["Fiskeboller i hvit saus"]))
    ny = coach.bytt_middag(db, MAN, "2026-11-18")
    assert livsstil.middag_for_dag(ny, "2026-11-18")["navn"] == "Fiskeboller"
    assert "Fiskeboller i hvit saus" in ny["handleliste"]


def test_bytt_middag_ugyldig_dag(db):
    livsstil.hent_eller_lag_ukeplan(db, MAN)
    with pytest.raises(ValueError):
        coach.bytt_middag(db, MAN, "2026-11-21")


def test_chat_lagrer_begge_roller(db, monkeypatch):
    monkeypatch.setattr(coach, "sporr_claude", lambda *a, **k: "Spis en omelett.")
    assert coach.svar_chat(db, "Hva spiser jeg?") == "Spis en omelett."
    roller = [r["rolle"] for r in db.execute("SELECT rolle FROM chat ORDER BY id")]
    assert roller == ["user", "assistant"]


def test_chat_reserve(db):
    assert "ikke tilgjengelig" in coach.svar_chat(db, "Hei")


def test_vanskelig_reserve(db):
    assert coach.vanskelig_na(db)


def test_helg_tips_reserve(db):
    assert len(coach.helg_tips(db, 4)) == 3


def test_helg_oppsummering_reserve(db):
    db.execute("INSERT INTO helgeplan (uke_start, planlagte_enheter) VALUES ('2026-11-16', 4)")
    for d, e in (("2026-11-20", 2), ("2026-11-21", 5)):
        livsstil.lagre_dagssjekk(db, d, False, True, e, False, False, "")
    tekst = coach.helg_oppsummering(db, MAN)
    assert "4" in tekst and "7" in tekst


def test_sammendrag_inneholder_rekke_og_malvekt(db):
    db.execute("UPDATE innstillinger SET mal_vekt_kg = 85 WHERE id = 1")
    db.commit()
    tekst = coach.lag_sammendrag(db, date(2026, 11, 18))
    assert "alkoholfrie hverdager på rad" in tekst.lower() and "85" in tekst


def test_sammendrag_sender_ikke_hemmeligheter(db):
    db.execute("INSERT INTO withings_konto (id, access_token, refresh_token, utloper) "
               "VALUES (1, 'HEMMELIG-TOKEN', 'HEMMELIG-TOKEN', '2030-01-01')")
    db.commit()
    assert "HEMMELIG-TOKEN" not in coach.lag_sammendrag(db, date(2026, 11, 18))
