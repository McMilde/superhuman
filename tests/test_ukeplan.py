from datetime import date

import livsstil

MAN = date(2026, 11, 16)


def _plan(db, uke_start, dager, antall=None):
    return livsstil.lagre_ukeplan(
        db, uke_start, dager, livsstil.RESERVE_MIDDAGER[:5], livsstil.RESERVE_LUNSJ, "reserve",
        antall_trening=antall,
    )


def _trent(db, dato, trent=True, syk=False):
    livsstil.lagre_dagssjekk(db, dato, False, False, None, trent, syk, "")


def test_velg_treningsdager_tre():
    assert livsstil.velg_treningsdager(MAN, 3) == ["2026-11-16", "2026-11-18", "2026-11-20"]


def test_velg_treningsdager_klemmes():
    assert len(livsstil.velg_treningsdager(MAN, 9)) == 5
    assert len(livsstil.velg_treningsdager(MAN, 0)) == 2


def test_antall_er_tre_uten_forrige_uke(db):
    assert livsstil.neste_antall_trening(db, MAN) == 3


def test_antall_okes_etter_full_uke(db):
    forrige = date(2026, 11, 9)
    dager = livsstil.velg_treningsdager(forrige, 3)
    _plan(db, forrige, dager)
    for d in dager:
        _trent(db, d)
    assert livsstil.neste_antall_trening(db, MAN) == 4


def test_antall_minskes_og_klemmes(db):
    forrige = date(2026, 11, 9)
    _plan(db, forrige, livsstil.velg_treningsdager(forrige, 2))
    assert livsstil.neste_antall_trening(db, MAN) == 2


def test_hent_eller_lag_ukeplan_lager_ved_behov(db):
    plan = livsstil.hent_eller_lag_ukeplan(db, MAN)
    assert plan["kilde"] == "reserve"
    assert len(plan["middager"]) == 5 and plan["middager"][0]["dag"] == "2026-11-16"
    assert plan["treningsdager"] == ["2026-11-16", "2026-11-18", "2026-11-20"]
    assert plan["handleliste"]
    igjen = livsstil.hent_eller_lag_ukeplan(db, MAN)
    assert igjen["laget"] == plan["laget"]


def test_hent_eller_lag_bruker_krok(db):
    kalt = []

    def lag(conn, uke_start):
        kalt.append(uke_start)
        return _plan(conn, uke_start, ["2026-11-17"])

    plan = livsstil.hent_eller_lag_ukeplan(db, MAN, lag_plan=lag)
    assert kalt == [MAN] and plan["treningsdager"] == ["2026-11-17"]


def test_handleliste_uten_duplikater():
    plan = {
        "middager": [{"ingredienser": ["Løk", "Kylling"]}, {"ingredienser": ["løk", "Ris"]}],
        "lunsj": {"ingredienser": ["kylling", "Brokkoli"]},
    }
    assert livsstil.handleliste(plan) == ["Løk", "Kylling", "Ris", "Brokkoli"]


def test_vanlig_treningsdag(db):
    _plan(db, MAN, ["2026-11-16", "2026-11-18"])
    assert livsstil.er_treningsdag_i_dag(db, date(2026, 11, 16), 85) == (True, None)
    assert livsstil.er_treningsdag_i_dag(db, date(2026, 11, 17), 85) == (False, None)


def test_lav_restitusjon_flytter_treningsdag(db):
    _plan(db, MAN, ["2026-11-16", "2026-11-18"])
    trening, grunn = livsstil.er_treningsdag_i_dag(db, date(2026, 11, 16), 55)
    assert trening is False and grunn
    dager = livsstil.hent_eller_lag_ukeplan(db, MAN)["treningsdager"]
    assert "2026-11-17" in dager and "2026-11-16" not in dager


def test_syk_i_gar_flytter(db):
    _plan(db, MAN, ["2026-11-18"])
    _trent(db, "2026-11-17", trent=False, syk=True)
    trening, grunn = livsstil.er_treningsdag_i_dag(db, date(2026, 11, 18), None)
    assert trening is False and "syk" in grunn.lower()
    assert "2026-11-19" in livsstil.hent_eller_lag_ukeplan(db, MAN)["treningsdager"]


def test_ingen_ledig_dag_senere_i_uka(db):
    _plan(db, MAN, ["2026-11-22"])
    trening, grunn = livsstil.er_treningsdag_i_dag(db, date(2026, 11, 22), 50)
    assert trening is False and grunn
    assert livsstil.hent_eller_lag_ukeplan(db, MAN)["treningsdager"] == []


def test_middag_for_dag(db):
    plan = livsstil.hent_eller_lag_ukeplan(db, MAN)
    assert livsstil.middag_for_dag(plan, "2026-11-17")["navn"] == plan["middager"][1]["navn"]
    assert livsstil.middag_for_dag(plan, "2026-11-21") is None
