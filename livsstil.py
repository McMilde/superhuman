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


def alkoholfrie_hverdager_pa_rad(conn, i_dag: date) -> int:
    """Hverdager (man-tor) uten alkohol på rad bakover. Fre-søn hoppes over
    (verken teller eller bryter). I dag teller bare hvis den er registrert."""
    teller = 0
    d = i_dag
    if hent_dagssjekk(conn, d.isoformat()) is None:
        d -= timedelta(days=1)
    for _ in range(400):
        if d.isoweekday() >= 5:
            d -= timedelta(days=1)
            continue
        sjekk = hent_dagssjekk(conn, d.isoformat())
        if sjekk is None or sjekk["alkohol"]:
            break
        teller += 1
        d -= timedelta(days=1)
    return teller


# ---- Ukeplan og treningsdager ----

def mandag_for(d: date) -> date:
    return d - timedelta(days=d.isoweekday() - 1)
