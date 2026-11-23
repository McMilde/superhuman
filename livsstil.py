"""Livsstil-logikken: daglig avkrysning, ukeplan, treningsdager og rekker.

Alle funksjoner tar en åpen sqlite3-tilkobling (row_factory = sqlite3.Row)
og importerer aldri app.py, slik at de kan testes og brukes fra planleggeren.
"""
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")


def i_dag_oslo() -> date:
    return datetime.now(OSLO).date()


def opprett_tabeller(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS dagssjekk (
            dato TEXT PRIMARY KEY,
            fastet INTEGER NOT NULL DEFAULT 0,
            alkohol INTEGER NOT NULL DEFAULT 0,
            alkohol_enheter REAL,
            trent INTEGER NOT NULL DEFAULT 0,
            syk INTEGER NOT NULL DEFAULT 0,
            notat TEXT NOT NULL DEFAULT '',
            oppdatert TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS ukeplan (
            uke_start TEXT PRIMARY KEY,
            treningsdager TEXT NOT NULL,
            antall_trening INTEGER NOT NULL,
            middager TEXT NOT NULL,
            lunsj TEXT NOT NULL,
            kilde TEXT NOT NULL,
            laget TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS helgeplan (
            uke_start TEXT PRIMARY KEY,
            planlagte_enheter INTEGER,
            tips TEXT NOT NULL DEFAULT '[]',
            oppsummering TEXT,
            opprettet TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS dagsmelding (
            dato TEXT PRIMARY KEY,
            tittel TEXT NOT NULL,
            tekst TEXT NOT NULL,
            treningsdag INTEGER NOT NULL DEFAULT 0,
            flyttet_fra TEXT,
            kilde TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tid TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            rolle TEXT NOT NULL,
            tekst TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS push_abonnement (
            endpoint TEXT PRIMARY KEY,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            opprettet TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS middag_vurdering (
            nokkel TEXT PRIMARY KEY,
            navn TEXT NOT NULL,
            vurdering INTEGER NOT NULL,
            oppdatert TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS ukemal (
            uke_start TEXT PRIMARY KEY,
            mal TEXT,
            forslag TEXT NOT NULL DEFAULT '[]',
            opprettet TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS varsel_logg (
            dato TEXT NOT NULL,
            type TEXT NOT NULL,
            sendt TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            UNIQUE(dato, type)
        );
        """
    )
    kolonner = {r[1] for r in conn.execute("PRAGMA table_info(innstillinger)")}
    for kol in ("varsel_tider", "vapid_privat", "vapid_offentlig"):
        if kol not in kolonner:
            conn.execute(f"ALTER TABLE innstillinger ADD COLUMN {kol} TEXT")
    for kol in ("alkohol_utgangspunkt_uke", "alkohol_kr_per_enhet"):
        if kol not in kolonner:
            conn.execute(f"ALTER TABLE innstillinger ADD COLUMN {kol} REAL")
    helg_kolonner = {r[1] for r in conn.execute("PRAGMA table_info(helgeplan)")}
    if "sluttid" not in helg_kolonner:
        conn.execute("ALTER TABLE helgeplan ADD COLUMN sluttid TEXT")
    if "planer" not in helg_kolonner:
        conn.execute("ALTER TABLE helgeplan ADD COLUMN planer TEXT NOT NULL DEFAULT '[]'")
    conn.commit()


# ---- Daglig avkrysning ----

def _tall_eller_none(verdi):
    if verdi is None or verdi == "":
        return None
    try:
        return float(str(verdi).replace(",", "."))
    except ValueError:
        return None


def lagre_dagssjekk(conn, dato, fastet, alkohol, alkohol_enheter, trent, syk, notat) -> dict:
    date.fromisoformat(dato)  # ValueError ved ugyldig dato
    enheter = _tall_eller_none(alkohol_enheter) if alkohol else None
    conn.execute(
        """
        INSERT INTO dagssjekk (dato, fastet, alkohol, alkohol_enheter, trent, syk, notat)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dato) DO UPDATE SET
            fastet = excluded.fastet, alkohol = excluded.alkohol,
            alkohol_enheter = excluded.alkohol_enheter, trent = excluded.trent,
            syk = excluded.syk, notat = excluded.notat,
            oppdatert = datetime('now', 'localtime')
        """,
        (dato, int(bool(fastet)), int(bool(alkohol)), enheter, int(bool(trent)),
         int(bool(syk)), (notat or "").strip()),
    )
    conn.commit()
    return hent_dagssjekk(conn, dato)


def hent_dagssjekk(conn, dato):
    rad = conn.execute("SELECT * FROM dagssjekk WHERE dato = ?", (dato,)).fetchone()
    return dict(rad) if rad else None


def dagsstatus(conn, dato):
    """Dagens avkrysning, eller en avledet status fra den gamle dagsloggen."""
    sjekk = hent_dagssjekk(conn, dato)
    if sjekk:
        sjekk["kilde"] = "ny"
        return sjekk
    gammel = conn.execute(
        "SELECT gjennomfort, annen_treningsform, notater FROM dagslogg WHERE dato = ?", (dato,)
    ).fetchone()
    if not gammel:
        return None
    return {
        "dato": dato, "fastet": 0, "alkohol": 0, "alkohol_enheter": None,
        "trent": int(bool(gammel["gjennomfort"] or gammel["annen_treningsform"])),
        "syk": 0, "notat": gammel["notater"] or "", "kilde": "gammel",
    }


FRIKORT_DAGER = 7


def rekke_status(conn, i_dag: date) -> dict:
    """Alkoholfrie hverdager (man-tor) på rad, med ett frikort: én glipp
    (alkohol eller glemt avkrysning) tilgis, men en ny glipp innen 7 dager
    nullstiller rekka. Fre-søn hopper over. I dag teller bare når den er
    registrert. Glipper tilgis bare når det finnes en rekke å redde."""
    rader = {r["dato"]: r["alkohol"] for r in conn.execute("SELECT dato, alkohol FROM dagssjekk")}
    if not rader:
        return {"naa": 0, "beste": 0, "frikort_brukt": False}
    d = date.fromisoformat(min(rader))
    naa = beste = 0
    tilgitt = None
    while d <= i_dag:
        if d.isoweekday() <= 4:
            alkohol = rader.get(d.isoformat())
            if alkohol is None and d == i_dag:
                pass
            elif alkohol == 0:
                naa += 1
                beste = max(beste, naa)
            elif naa > 0 and (tilgitt is None or (d - tilgitt).days > FRIKORT_DAGER):
                tilgitt = d
            else:
                naa = 0
                tilgitt = None
        d += timedelta(days=1)
    frikort = tilgitt is not None and (i_dag - tilgitt).days <= FRIKORT_DAGER
    return {"naa": naa, "beste": beste, "frikort_brukt": frikort}


def alkoholfrie_hverdager_pa_rad(conn, i_dag: date) -> int:
    return rekke_status(conn, i_dag)["naa"]


# ---- Ukeplan og treningsdager ----

def mandag_for(d: date) -> date:
    return d - timedelta(days=d.isoweekday() - 1)


def _m(navn, minutter, beskrivelse, ingredienser):
    return {"navn": navn, "minutter": minutter, "beskrivelse": beskrivelse, "ingredienser": ingredienser}


# Raske familiemiddager (barn på 5 og 10 år) som brukes når coachen (Claude)
# ikke er tilgjengelig. Rulleres etter ukenummer.
RESERVE_MIDDAGER = [
    _m("Kyllingwok med nudler", 20, "Strimlet kylling, masse grønnsaker og litt soyasaus. Barna kan få nudlene for seg.",
       ["600 g kyllingfilet", "1 pose wokgrønnsaker", "Eggnudler", "Soyasaus", "Hvitløk"]),
    _m("Laks i ovn med potet og brokkoli", 25, "Laks med sitron i ovnen mens potetene koker. Ta deg rikelig brokkoli, færre poteter.",
       ["600 g laksefilet", "Poteter", "Brokkoli", "Sitron"]),
    _m("Taco i skål", 25, "Kjøttdeig med krydder, masse salat, mais og rømme. Du dropper lefsene, barna tar dem.",
       ["500 g kjøttdeig", "Tacokrydder", "Isbergsalat", "Agurk", "Mais", "Lett rømme", "Tortillalefser"]),
    _m("Omelett med skinke og grønnsaker", 15, "Rask hverdagsmiddag. Server med grovt brød til barna.",
       ["8 egg", "Skinke", "Paprika", "Spinat", "Revet ost"]),
    _m("Kjøttboller i tomatsaus med pasta", 25, "Ferdige kjøttboller i tomatsaus. Halv porsjon pasta til deg, dobbel salat.",
       ["Kjøttboller", "Knuste tomater", "Pasta", "Salat"]),
    _m("Fiskegrateng light", 30, "Fiskegrateng med ekstra gulrot og erter ved siden av.",
       ["Fiskegrateng", "Gulrøtter", "Erter"]),
    _m("Kylling i ovn med rotgrønnsaker", 30, "Kyllinglår og rotgrønnsaker på samme brett. Lite oppvask.",
       ["Kyllinglår", "Gulrøtter", "Søtpotet", "Rødløk", "Olivenolje"]),
    _m("Torsk med smørdampede grønnsaker", 20, "Mild fisk som barna liker. Litt smør går fint.",
       ["600 g torskefilet", "Brokkoli", "Gulrøtter", "Poteter", "Smør"]),
    _m("Kyllingsuppe", 25, "Kylling, grønnsaker og buljong. Varm og mettende.",
       ["Kyllingfilet", "Kyllingbuljong", "Gulrøtter", "Purre", "Selleri", "Pasta (til barna)"]),
    _m("Karbonader med løk og grønnsaker", 25, "Karbonadedeig stekt i panne med løk, kokte grønnsaker og poteter.",
       ["Karbonadedeig", "Løk", "Poteter", "Brokkoli", "Gulrøtter"]),
    _m("Pita med kylling og salat", 20, "Barna fyller selv. Du tar mer salat og kylling, mindre brød.",
       ["Pitabrød", "Kyllingfilet", "Salat", "Tomat", "Agurk", "Lett rømme"]),
    _m("Ørret med grønnsaksris", 25, "Ørret i panne, ris med erter og mais.",
       ["600 g ørretfilet", "Ris", "Erter", "Mais", "Sitron"]),
]

RESERVE_LUNSJ = {
    **_m("Kjøttdeig med grønnsaker i bokser", 30,
         "Stek 1 kg kjøttdeig med løk og hvitløk, ha i frosne grønnsaker og knuste tomater. Fordel i 5 bokser – lunsj for hele uka.",
         ["1 kg kjøttdeig", "Løk", "Hvitløk", "2 poser frosne grønnsaker", "Knuste tomater", "5 matbokser"]),
    "brodtips": [
        "Surdeigsbrød med kokt egg, avokado og tomat",
        "Surdeigsbrød med kyllingpålegg, cottage cheese og agurk",
        "Surdeigsbrød med makrell i tomat og rødløk",
        "Surdeigsbrød med hummus, kalkun og paprika",
    ],
}

_FORDELING = {
    2: [1, 3],
    3: [0, 2, 4],
    4: [0, 1, 3, 5],
    5: [0, 1, 2, 4, 5],
}


def _klem(antall: int) -> int:
    return max(2, min(5, int(antall)))


def velg_treningsdager(uke_start: date, antall: int) -> list:
    return [(uke_start + timedelta(days=i)).isoformat() for i in _FORDELING[_klem(antall)]]


def standard_prep_steg(lunsj: dict) -> list:
    return [
        "Finn fram 5 matbokser og alt fra handlelista som hører til lunsjen.",
        "Kutt det som skal kuttes først, så går resten fort.",
        "Lag selve retten etter oppskriften over. Lag gjerne dobbelt så mye grønnsaker som du tror du trenger.",
        "La maten avkjøles i 15–20 minutter før du fordeler den i boksene.",
        "Sett boksene i kjøleskapet – de holder i 4–5 dager. Frys gjerne én hvis fredagen er usikker.",
    ]


def _rad_til_plan(rad) -> dict:
    plan = {
        "uke_start": rad["uke_start"],
        "treningsdager": json.loads(rad["treningsdager"]),
        "antall_trening": rad["antall_trening"],
        "middager": json.loads(rad["middager"]),
        "lunsj": json.loads(rad["lunsj"]),
        "kilde": rad["kilde"],
        "laget": rad["laget"],
    }
    if not plan["lunsj"].get("steg"):
        plan["lunsj"]["steg"] = standard_prep_steg(plan["lunsj"])
    plan["handleliste"] = handleliste(plan)
    return plan


def hent_ukeplan(conn, uke_start: date):
    rad = conn.execute("SELECT * FROM ukeplan WHERE uke_start = ?", (uke_start.isoformat(),)).fetchone()
    return _rad_til_plan(rad) if rad else None


def neste_antall_trening(conn, uke_start: date) -> int:
    forrige_start = uke_start - timedelta(days=7)
    forrige = hent_ukeplan(conn, forrige_start)
    if forrige is None:
        return 3
    antall = forrige["antall_trening"]
    datoer = [(forrige_start + timedelta(days=i)).isoformat() for i in range(7)]
    trent = conn.execute(
        "SELECT COUNT(*) FROM dagssjekk WHERE trent = 1 AND dato IN ({})".format(",".join("?" * 7)), datoer
    ).fetchone()[0]
    if trent >= antall:
        antall += 1
    elif trent < antall / 2:
        antall -= 1
    return _klem(antall)


def lagre_ukeplan(conn, uke_start: date, treningsdager, middager, lunsj, kilde, antall_trening=None) -> dict:
    middager_med_dag = []
    for i, m in enumerate(middager):
        m = dict(m)
        m.setdefault("dag", (uke_start + timedelta(days=i)).isoformat())
        middager_med_dag.append(m)
    conn.execute(
        """
        INSERT INTO ukeplan (uke_start, treningsdager, antall_trening, middager, lunsj, kilde)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(uke_start) DO UPDATE SET
            treningsdager = excluded.treningsdager, antall_trening = excluded.antall_trening,
            middager = excluded.middager, lunsj = excluded.lunsj, kilde = excluded.kilde,
            laget = datetime('now', 'localtime')
        """,
        (uke_start.isoformat(), json.dumps(sorted(treningsdager)),
         antall_trening if antall_trening is not None else len(treningsdager),
         json.dumps(middager_med_dag, ensure_ascii=False), json.dumps(lunsj, ensure_ascii=False), kilde),
    )
    conn.commit()
    return hent_ukeplan(conn, uke_start)


def tilgjengelige_reservemiddager(conn) -> list:
    """Reservemiddagene minus dem familien har gitt tommel ned."""
    unnga = {n.lower() for n in hent_vurderinger(conn)["unnga"]}
    ledige = [m for m in RESERVE_MIDDAGER if m["navn"].lower() not in unnga]
    return ledige if len(ledige) >= 5 else ledige + [m for m in RESERVE_MIDDAGER if m not in ledige][:5 - len(ledige)]


def lag_reserveplan(conn, uke_start: date) -> dict:
    antall = neste_antall_trening(conn, uke_start)
    uke_nr = uke_start.isocalendar()[1]
    ledige = tilgjengelige_reservemiddager(conn)
    middager = [ledige[(uke_nr * 5 + i) % len(ledige)] for i in range(5)]
    return lagre_ukeplan(conn, uke_start, velg_treningsdager(uke_start, antall), middager,
                         RESERVE_LUNSJ, "reserve", antall_trening=antall)


def hent_eller_lag_ukeplan(conn, uke_start: date, lag_plan=None) -> dict:
    plan = hent_ukeplan(conn, uke_start)
    if plan is not None:
        return plan
    return (lag_plan or lag_reserveplan)(conn, uke_start)


def handleliste(plan: dict) -> list:
    sett, liste = set(), []
    kilder = [m.get("ingredienser", []) for m in plan.get("middager", [])]
    kilder.append(plan.get("lunsj", {}).get("ingredienser", []))
    for ingredienser in kilder:
        for ing in ingredienser:
            nokkel = ing.strip().lower()
            if nokkel and nokkel not in sett:
                sett.add(nokkel)
                liste.append(ing.strip())
    return liste


def middag_for_dag(plan: dict, dato: str):
    return next((m for m in plan["middager"] if m.get("dag") == dato), None)


def _sett_treningsdager(conn, uke_start: date, dager: list) -> None:
    conn.execute("UPDATE ukeplan SET treningsdager = ? WHERE uke_start = ?",
                 (json.dumps(sorted(dager)), uke_start.isoformat()))
    conn.commit()


def er_treningsdag_i_dag(conn, i_dag: date, restitusjon):
    """(treningsdag?, grunn til flytting). Flytter dagens økt til neste ledige
    dag samme uke ved lav restitusjon (< 70) eller hvis han var syk i går."""
    uke_start = mandag_for(i_dag)
    plan = hent_eller_lag_ukeplan(conn, uke_start)
    dager = list(plan["treningsdager"])
    i_dag_str = i_dag.isoformat()
    if i_dag_str not in dager:
        return False, None

    i_gar = hent_dagssjekk(conn, (i_dag - timedelta(days=1)).isoformat())
    grunn = None
    if i_gar and i_gar["syk"]:
        grunn = "Du var syk i går, så kroppen trenger en rolig dag."
    elif restitusjon is not None and restitusjon < 70:
        grunn = f"Oura viser lav restitusjon ({int(restitusjon)}), så vi tar det rolig i dag."
    if grunn is None:
        return True, None

    dager.remove(i_dag_str)
    for i in range(1, 7):
        kandidat = i_dag + timedelta(days=i)
        if kandidat.isoweekday() == 1:
            break
        if kandidat.isoformat() not in dager:
            dager.append(kandidat.isoformat())
            grunn += f" Treningen flyttes til {['mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag', 'søndag'][kandidat.isoweekday() - 1]}."
            break
    _sett_treningsdager(conn, uke_start, dager)
    return False, grunn



# ---- Hva alkoholen gjør med deg ----

MIN_DAGER_EFFEKT = 5
KALORIER_PER_ENHET = 100
KALORIER_PER_KG = 7700
ENHETER_NAAR_UKJENT = 2
STANDARD_KR_PER_ENHET = 40


def beste_alkoholfrie_rekke(conn, i_dag: date) -> int:
    return rekke_status(conn, i_dag)["beste"]


def _snitt(verdier):
    return round(sum(verdier) / len(verdier)) if verdier else None


def alkohol_effekt(conn, i_dag: date) -> dict:
    """Sammenligner Oura-tallene dagen ETTER dager med og uten alkohol
    (siste 180 dager). Krever minst 5 dager i hver gruppe."""
    fra = (i_dag - timedelta(days=180)).isoformat()
    oura = {}
    for r in conn.execute("SELECT dato, type, verdi FROM oura_malinger WHERE type IN ('restitusjon_score', 'sovn_score')"):
        oura.setdefault(r["dato"], {})[r["type"]] = r["verdi"]
    grupper = {True: {"restitusjon": [], "sovn": []}, False: {"restitusjon": [], "sovn": []}}
    for r in conn.execute("SELECT dato, alkohol FROM dagssjekk WHERE dato >= ? AND dato < ?", (fra, i_dag.isoformat())):
        neste = oura.get((date.fromisoformat(r["dato"]) + timedelta(days=1)).isoformat(), {})
        if "restitusjon_score" not in neste:
            continue
        g = grupper[bool(r["alkohol"])]
        g["restitusjon"].append(neste["restitusjon_score"])
        if "sovn_score" in neste:
            g["sovn"].append(neste["sovn_score"])
    med, uten = grupper[True], grupper[False]
    n_med, n_uten = len(med["restitusjon"]), len(uten["restitusjon"])
    resultat = {
        "nok_data": n_med >= MIN_DAGER_EFFEKT and n_uten >= MIN_DAGER_EFFEKT,
        "dager_med": n_med,
        "dager_uten": n_uten,
        "trengs_med": max(0, MIN_DAGER_EFFEKT - n_med),
        "trengs_uten": max(0, MIN_DAGER_EFFEKT - n_uten),
    }
    if resultat["nok_data"]:
        resultat.update({
            "restitusjon_med": _snitt(med["restitusjon"]),
            "restitusjon_uten": _snitt(uten["restitusjon"]),
            "sovn_med": _snitt(med["sovn"]),
            "sovn_uten": _snitt(uten["sovn"]),
        })
    return resultat


def hent_alkohol_utgangspunkt(conn):
    rad = conn.execute(
        "SELECT alkohol_utgangspunkt_uke, alkohol_kr_per_enhet FROM innstillinger WHERE id = 1"
    ).fetchone()
    if not rad or rad["alkohol_utgangspunkt_uke"] is None:
        return None
    return {
        "enheter_per_uke": rad["alkohol_utgangspunkt_uke"],
        "kr_per_enhet": rad["alkohol_kr_per_enhet"] or STANDARD_KR_PER_ENHET,
    }


def lagre_alkohol_utgangspunkt(conn, enheter_per_uke, kr_per_enhet=None) -> dict:
    enheter = _tall_eller_none(enheter_per_uke)
    kr = _tall_eller_none(kr_per_enhet) if kr_per_enhet not in (None, "") else STANDARD_KR_PER_ENHET
    if enheter is None or not 0 <= enheter <= 200:
        raise ValueError("Skriv hvor mange enheter du drakk i en vanlig uke (0-200).")
    if kr is None or not 0 < kr <= 500:
        raise ValueError("Pris per enhet må være mellom 1 og 500 kr.")
    conn.execute("UPDATE innstillinger SET alkohol_utgangspunkt_uke = ?, alkohol_kr_per_enhet = ? WHERE id = 1",
                 (enheter, kr))
    conn.commit()
    return hent_alkohol_utgangspunkt(conn)


def alkohol_spart(conn):
    """Enheter, kroner og kalorier spart mot «slik jeg drakk før», regnet over
    dagene som er registrert. Alkohol uten antall regnes som 2 enheter."""
    utgangspunkt = hent_alkohol_utgangspunkt(conn)
    if utgangspunkt is None:
        return None
    rader = conn.execute("SELECT dato, alkohol, alkohol_enheter FROM dagssjekk").fetchall()
    if not rader:
        return None
    faktisk = sum(
        (r["alkohol_enheter"] if r["alkohol_enheter"] is not None else ENHETER_NAAR_UKJENT)
        for r in rader if r["alkohol"]
    )
    spart = round(utgangspunkt["enheter_per_uke"] / 7 * len(rader) - faktisk, 1)
    kalorier = round(spart * KALORIER_PER_ENHET)
    return {
        "enheter_spart": spart,
        "kr": round(spart * utgangspunkt["kr_per_enhet"]),
        "kalorier": kalorier,
        "kg": round(kalorier / KALORIER_PER_KG, 2),
        "dager": len(rader),
        "fra_dato": min(r["dato"] for r in rader),
    }



# ---- Helgeplan 2.0 ----

STANDARD_SLUTTID = "22:00"


def brukt_i_helgen(conn, uke_start: date) -> float:
    datoer = [(uke_start + timedelta(days=i)).isoformat() for i in (4, 5, 6)]
    sum_ = conn.execute(
        "SELECT COALESCE(SUM(alkohol_enheter), 0) FROM dagssjekk WHERE alkohol = 1 AND dato IN (?, ?, ?)", datoer
    ).fetchone()[0]
    return float(sum_)


def hent_helgeplan(conn, uke_start: date):
    rad = conn.execute("SELECT * FROM helgeplan WHERE uke_start = ?", (uke_start.isoformat(),)).fetchone()
    if not rad:
        return None
    return {
        "planlagte_enheter": rad["planlagte_enheter"],
        "tips": json.loads(rad["tips"] or "[]"),
        "oppsummering": rad["oppsummering"],
        "sluttid": rad["sluttid"] or (STANDARD_SLUTTID if rad["planlagte_enheter"] is not None else None),
        "planer": json.loads(rad["planer"] or "[]"),
        "brukt": brukt_i_helgen(conn, uke_start),
    }


def lagre_helgeplan(conn, uke_start: date, enheter: int, tips: list, sluttid: str) -> dict:
    conn.execute(
        """
        INSERT INTO helgeplan (uke_start, planlagte_enheter, tips, sluttid) VALUES (?, ?, ?, ?)
        ON CONFLICT(uke_start) DO UPDATE SET planlagte_enheter = excluded.planlagte_enheter,
            tips = excluded.tips, sluttid = excluded.sluttid
        """,
        (uke_start.isoformat(), enheter, json.dumps(tips, ensure_ascii=False), sluttid),
    )
    conn.commit()
    return hent_helgeplan(conn, uke_start)


def lagre_helg_planer(conn, uke_start: date, planer: list) -> list:
    if hent_helgeplan(conn, uke_start) is None:
        raise ValueError("Lag helgeplanen først.")
    rene = [str(p).strip()[:200] for p in (planer or []) if str(p).strip()][:3]
    conn.execute("UPDATE helgeplan SET planer = ? WHERE uke_start = ?",
                 (json.dumps(rene, ensure_ascii=False), uke_start.isoformat()))
    conn.commit()
    return rene


def endre_enheter(conn, dato: str, endring: int):
    """+1 / -1 enhet på en dag, uten å røre de andre avkrysningene."""
    rad = hent_dagssjekk(conn, dato)
    if rad is None:
        if endring < 0:
            return None
        return lagre_dagssjekk(conn, dato, False, True, endring, False, False, "")
    enheter = max(0.0, (rad["alkohol_enheter"] or 0) + endring)
    alkohol = enheter > 0
    return lagre_dagssjekk(conn, dato, rad["fastet"], alkohol, enheter if alkohol else None,
                           rad["trent"], rad["syk"], rad["notat"])


UKEDAG_NAVN = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]


def risikodag(conn, i_dag: date):
    """Hverdagen (1=man ... 4=tor) han oftest har drukket på de siste 8 ukene,
    hvis det har skjedd minst to ganger. Ellers None."""
    fra = (i_dag - timedelta(days=56)).isoformat()
    teller = {}
    for r in conn.execute("SELECT dato FROM dagssjekk WHERE alkohol = 1 AND dato >= ? AND dato < ?",
                          (fra, i_dag.isoformat())):
        dag = date.fromisoformat(r["dato"]).isoweekday()
        if dag <= 4:
            teller[dag] = teller.get(dag, 0) + 1
    if not teller:
        return None
    dag, antall = max(sorted(teller.items()), key=lambda x: x[1])
    return dag if antall >= 2 else None


def helg_over_plan(conn, i_dag: date):
    """På mandager: (planlagt, faktisk) hvis forrige helg gikk over planen."""
    if i_dag.isoweekday() != 1:
        return None
    forrige = i_dag - timedelta(days=7)
    plan = hent_helgeplan(conn, forrige)
    if not plan or plan["planlagte_enheter"] is None:
        return None
    datoer = [(forrige + timedelta(days=i)).isoformat() for i in (4, 5, 6)]
    faktisk = sum(
        (r["alkohol_enheter"] if r["alkohol_enheter"] is not None else ENHETER_NAAR_UKJENT)
        for r in conn.execute("SELECT alkohol_enheter FROM dagssjekk WHERE alkohol = 1 AND dato IN (?, ?, ?)", datoer)
    )
    if faktisk > plan["planlagte_enheter"]:
        return plan["planlagte_enheter"], faktisk
    return None



# ---- Søndagssjekk og ukemål ----

def ukestatistikk(conn, uke_start: date) -> dict:
    datoer = [(uke_start + timedelta(days=i)).isoformat() for i in range(7)]
    rader = {r["dato"]: r for r in conn.execute(
        "SELECT * FROM dagssjekk WHERE dato IN ({})".format(",".join("?" * 7)), datoer)}
    hverdager = [rader[d] for d in datoer[:4] if d in rader]
    helg = [rader[d] for d in datoer[4:] if d in rader]
    vekter = conn.execute(
        "SELECT vekt_kg FROM vektlogg WHERE dato >= ? AND dato <= ? ORDER BY dato, id", (datoer[0], datoer[-1])
    ).fetchall()
    plan = hent_ukeplan(conn, uke_start)
    return {
        "uke_start": uke_start.isoformat(),
        "alkoholfrie_hverdager": sum(1 for r in hverdager if not r["alkohol"]),
        "registrerte_hverdager": len(hverdager),
        "fastedager": sum(1 for r in rader.values() if r["fastet"]),
        "treningsdager": sum(1 for r in rader.values() if r["trent"]),
        "planlagte_treningsdager": plan["antall_trening"] if plan else None,
        "helg_enheter": sum(
            (r["alkohol_enheter"] if r["alkohol_enheter"] is not None else ENHETER_NAAR_UKJENT)
            for r in helg if r["alkohol"]
        ),
        "registrerte_dager": len(rader),
        "vekt_endring": round(vekter[-1]["vekt_kg"] - vekter[0]["vekt_kg"], 1) if len(vekter) >= 2 else None,
    }


FYLL_UKEMAL = [
    "Halve tallerkenen grønnsaker til hver middag",
    "Gå en tur på minst 20 minutter hver dag",
    "Legg deg før kl. 23 på hverdager",
    "Drikk et stort glass vann før hvert måltid",
]


def reserve_ukemal_forslag(conn, uke_start: date) -> list:
    """Tre ukemål ut fra uka før: det som glapp først, så faste reserver."""
    st = ukestatistikk(conn, uke_start - timedelta(days=7))
    forslag = []
    if st["alkoholfrie_hverdager"] < st["registrerte_hverdager"]:
        forslag.append("Alkoholfrie hverdager – alle fire, mandag til torsdag")
    if st["planlagte_treningsdager"] and st["treningsdager"] < st["planlagte_treningsdager"]:
        forslag.append(f"Gjennomfør alle {st['planlagte_treningsdager']} treningsdagene")
    if st["registrerte_dager"] and st["fastedager"] < 5:
        forslag.append("Fast minst 5 av 7 dager")
    for f in FYLL_UKEMAL:
        if len(forslag) >= 3:
            break
        forslag.append(f)
    return forslag[:3]


def _hent_ukemal_rad(conn, uke_start: date):
    return conn.execute("SELECT * FROM ukemal WHERE uke_start = ?", (uke_start.isoformat(),)).fetchone()


def lagre_ukemal_forslag(conn, uke_start: date, forslag: list) -> None:
    conn.execute(
        """
        INSERT INTO ukemal (uke_start, forslag) VALUES (?, ?)
        ON CONFLICT(uke_start) DO UPDATE SET forslag = excluded.forslag
        """,
        (uke_start.isoformat(), json.dumps(forslag, ensure_ascii=False)),
    )
    conn.commit()


def velg_ukemal(conn, uke_start: date, mal: str) -> str:
    mal = (mal or "").strip()[:200]
    if not mal:
        raise ValueError("Skriv eller velg et ukemål.")
    conn.execute(
        """
        INSERT INTO ukemal (uke_start, mal) VALUES (?, ?)
        ON CONFLICT(uke_start) DO UPDATE SET mal = excluded.mal
        """,
        (uke_start.isoformat(), mal),
    )
    conn.commit()
    return mal


def hent_ukemal(conn, uke_start: date):
    rad = _hent_ukemal_rad(conn, uke_start)
    return rad["mal"] if rad else None


def aktivt_ukemal(conn, i_dag: date, lag_forslag=None) -> dict:
    """Ukemålet som skal vises i dag. Søndag, når neste ukes forslag er klare,
    gjelder det neste uke. Mangler forslag, lages de på stedet."""
    denne = mandag_for(i_dag)
    neste = denne + timedelta(days=7)
    uke, gjelder = denne, "denne"
    if i_dag.isoweekday() == 7 and _hent_ukemal_rad(conn, neste) is not None:
        uke, gjelder = neste, "neste"
    rad = _hent_ukemal_rad(conn, uke)
    forslag = json.loads(rad["forslag"]) if rad else []
    if not forslag:
        forslag = (lag_forslag or reserve_ukemal_forslag)(conn, uke)
        lagre_ukemal_forslag(conn, uke, forslag)
        rad = _hent_ukemal_rad(conn, uke)
    return {
        "uke_start": uke.isoformat(),
        "gjelder": gjelder,
        "mal": rad["mal"],
        "forslag": forslag,
        "statistikk": ukestatistikk(conn, uke - timedelta(days=7)),
    }



# ---- Smartere mat ----

def vurder_middag(conn, navn: str, vurdering: int) -> None:
    navn = (navn or "").strip()[:120]
    if not navn:
        raise ValueError("Mangler navn på middagen.")
    if isinstance(vurdering, bool) or vurdering not in (-1, 0, 1):
        raise ValueError("Vurdering må være -1, 0 eller 1.")
    if vurdering == 0:
        conn.execute("DELETE FROM middag_vurdering WHERE nokkel = ?", (navn.lower(),))
    else:
        conn.execute(
            """
            INSERT INTO middag_vurdering (nokkel, navn, vurdering) VALUES (?, ?, ?)
            ON CONFLICT(nokkel) DO UPDATE SET vurdering = excluded.vurdering, oppdatert = datetime('now', 'localtime')
            """,
            (navn.lower(), navn, vurdering),
        )
    conn.commit()


def hent_vurderinger(conn) -> dict:
    rader = conn.execute("SELECT navn, vurdering FROM middag_vurdering ORDER BY oppdatert, navn").fetchall()
    return {
        "favoritter": [r["navn"] for r in rader if r["vurdering"] > 0],
        "unnga": [r["navn"] for r in rader if r["vurdering"] < 0],
    }


def sett_middag(conn, uke_start: date, dag: str, middag: dict) -> dict:
    plan = hent_eller_lag_ukeplan(conn, uke_start)
    if middag_for_dag(plan, dag) is None:
        raise ValueError("Den dagen har ingen middag i planen.")
    if not str(middag.get("navn") or "").strip():
        raise ValueError("Middagen mangler navn.")
    ny = {
        "navn": str(middag["navn"]).strip()[:120],
        "minutter": int(middag.get("minutter") or 30),
        "beskrivelse": str(middag.get("beskrivelse") or "")[:400],
        "ingredienser": [str(i)[:80] for i in (middag.get("ingredienser") or [])][:20],
    }
    middager = [({**ny, "dag": dag} if m["dag"] == dag else m) for m in plan["middager"]]
    return lagre_ukeplan(conn, uke_start, plan["treningsdager"], middager, plan["lunsj"], plan["kilde"],
                         antall_trening=plan["antall_trening"])
