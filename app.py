import json
import os
import secrets
import socket
import sqlite3
import webbrowser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import mkstemp
from threading import Timer
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

import coach
import livsstil
from flask import (
    Flask, Response, after_this_request, g, jsonify, redirect, request,
    send_file, session, url_for,
)

DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).parent / "trening.db")))

# APP_PASSORD settes kun i skyen (Railway). Er den ikke satt (lokal bruk hjemme
# på wifi), kreves ingen innlogging - appen oppfører seg akkurat som før.
APP_PASSORD = os.environ.get("APP_PASSORD")

# Egen, separat hemmelig kode for /api/varsel - denne ruten er unntatt fra
# innloggingskravet (Snarveier-appen på iPhone kan ikke logge inn), så den
# beskyttes i stedet med en lang kode i selve lenken.
VARSEL_NOKKEL = os.environ.get("VARSEL_NOKKEL")

# For automatisk henting av data fra Withings-vekten (satt opp i developer.withings.com).
WITHINGS_CLIENT_ID = os.environ.get("WITHINGS_CLIENT_ID")
WITHINGS_CLIENT_SECRET = os.environ.get("WITHINGS_CLIENT_SECRET")
WITHINGS_REDIRECT_URI = "https://trening.flibber.no/withings/callback"

# Withings sine måletype-koder -> norsk navn og enhet. Body Smart-vekten sender
# stort sett disse; ukjente typer hoppes bare stille over.
WITHINGS_MALETYPER = {
    1: ("Vekt", "kg"),
    6: ("Fettprosent", "%"),
    8: ("Fettmasse", "kg"),
    76: ("Muskelmasse", "kg"),
    77: ("Kroppsvann", "kg"),
    88: ("Beinmasse", "kg"),
    11: ("Puls", "bpm"),
}

# For automatisk henting av søvn/aktivitet/restitusjon fra Oura-ringen
# (satt opp i cloud.ouraring.com/oauth/applications).
OURA_CLIENT_ID = os.environ.get("OURA_CLIENT_ID")
OURA_CLIENT_SECRET = os.environ.get("OURA_CLIENT_SECRET")
OURA_REDIRECT_URI = "https://trening.flibber.no/oura/callback"

# Ouras daglige poengsummer (0-100) og noen få nøkkeltall - samme (navn, enhet)-
# form som WITHINGS_MALETYPER over, men med tekst-nøkler siden Oura ikke har
# tallkoder for målingene sine slik Withings har.
OURA_MALETYPER = {
    "sovn_score": ("Søvn-poengsum", ""),
    "restitusjon_score": ("Restitusjon-poengsum", ""),
    "aktivitet_score": ("Aktivitet-poengsum", ""),
    "skritt": ("Skritt", ""),
}

UKEDAGER = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 365  # 1 år
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


@app.before_request
def krev_innlogging():
    if not APP_PASSORD:
        return
    if request.endpoint in (
        "login", "static",
        "withings_callback", "api_withings_synk_automatisk",
        "oura_callback", "api_oura_synk_automatisk",
    ):
        return
    if not session.get("innlogget"):
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    feil = False
    if request.method == "POST":
        if request.form.get("passord") == APP_PASSORD:
            session.permanent = True
            session["innlogget"] = True
            return redirect(url_for("index"))
        feil = True
    feilmelding = '<p style="color:#c0392b;font-family:sans-serif;">Feil passord.</p>' if feil else ""
    return f"""
    <!doctype html>
    <html lang="no"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Superhuman 2.0</title>
    <link rel="icon" type="image/svg+xml" href="/static/icon.svg" />
    <link rel="manifest" href="/static/manifest.json" />
    <link rel="apple-touch-icon" href="/static/apple-touch-icon.png" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-title" content="Superhuman 2.0" />
    <style>
      body {{ font-family: -apple-system, sans-serif; background: #f4faf8; display: flex;
             align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
      form {{ background: white; padding: 28px; border-radius: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.1);
              width: 100%; max-width: 320px; }}
      h1 {{ color: #17604a; font-size: 20px; margin: 0 0 16px; }}
      input {{ width: 100%; padding: 12px; border: 1px solid #dcece6; border-radius: 10px;
               font-size: 16px; box-sizing: border-box; margin-bottom: 12px; }}
      button {{ width: 100%; padding: 12px; border: none; border-radius: 999px; background: #1f7a5c;
                color: white; font-size: 15px; font-weight: 700; cursor: pointer; }}
    </style></head>
    <body>
      <form method="post">
        <h1>Superhuman 2.0</h1>
        {feilmelding}
        <input type="password" name="passord" placeholder="Passord" autofocus required />
        <button type="submit">Logg inn</button>
      </form>
    </body></html>
    """


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS innstillinger (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            start_dato TEXT NOT NULL
        )
        """
    )
    if conn.execute("SELECT 1 FROM innstillinger WHERE id = 1").fetchone() is None:
        # SEED_START_DATO brukes kun første gang en helt ny database opprettes et
        # nytt sted (f.eks. ved flytting til skyen), slik at man kan gjenskape
        # riktig ukenummer i stedet for at telling starter på nytt fra i dag.
        start_dato = os.environ.get("SEED_START_DATO") or date.today().isoformat()
        conn.execute(
            "INSERT INTO innstillinger (id, start_dato) VALUES (1, ?)",
            (start_dato,),
        )
    innstillinger_kolonner = {row["name"] for row in conn.execute("PRAGMA table_info(innstillinger)")}
    if "withings_pending_state" not in innstillinger_kolonner:
        # Brukes av /withings/connect + /withings/callback for å bekrefte at
        # innloggingen faktisk kom fra oss (CSRF-beskyttelse). Lagres i databasen
        # i stedet for i sesjons-cookien, fordi iPhonens hjemskjerm-app ikke
        # pålitelig beholder samme cookie gjennom turen til Withings og tilbake.
        conn.execute("ALTER TABLE innstillinger ADD COLUMN withings_pending_state TEXT")
    if "oura_pending_state" not in innstillinger_kolonner:
        # Samme mønster/begrunnelse som withings_pending_state over, for Oura-tilkoblingen.
        conn.execute("ALTER TABLE innstillinger ADD COLUMN oura_pending_state TEXT")
    if "mal_vekt_kg" not in innstillinger_kolonner:
        conn.execute("ALTER TABLE innstillinger ADD COLUMN mal_vekt_kg REAL")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fysio_ovelser (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            navn TEXT NOT NULL,
            beskrivelse TEXT NOT NULL DEFAULT '',
            aktiv INTEGER NOT NULL DEFAULT 1,
            opprettet TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS styrke_logg (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dato TEXT NOT NULL,
            ovelse_id TEXT NOT NULL,
            vekt_kg REAL,
            reps INTEGER,
            opprettet TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            UNIQUE(dato, ovelse_id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dagslogg (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dato TEXT NOT NULL UNIQUE,
            gjennomfort INTEGER NOT NULL DEFAULT 0,
            fysio_gjort INTEGER NOT NULL DEFAULT 0,
            notater TEXT NOT NULL DEFAULT '',
            oppdatert TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    dagslogg_kolonner = {row["name"] for row in conn.execute("PRAGMA table_info(dagslogg)")}
    if "annen_treningsform" not in dagslogg_kolonner:
        conn.execute("ALTER TABLE dagslogg ADD COLUMN annen_treningsform INTEGER NOT NULL DEFAULT 0")
    if "treningsform_begrunnelse" not in dagslogg_kolonner:
        conn.execute("ALTER TABLE dagslogg ADD COLUMN treningsform_begrunnelse TEXT NOT NULL DEFAULT ''")
    if "ikke_gjennomfort_begrunnelse" not in dagslogg_kolonner:
        conn.execute("ALTER TABLE dagslogg ADD COLUMN ikke_gjennomfort_begrunnelse TEXT NOT NULL DEFAULT ''")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vektlogg (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dato TEXT NOT NULL,
            vekt_kg REAL NOT NULL,
            notater TEXT NOT NULL DEFAULT '',
            opprettet TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    vektlogg_kolonner = {row["name"] for row in conn.execute("PRAGMA table_info(vektlogg)")}
    if "withings_grpid" not in vektlogg_kolonner:
        conn.execute("ALTER TABLE vektlogg ADD COLUMN withings_grpid TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_vektlogg_withings_grpid "
        "ON vektlogg(withings_grpid) WHERE withings_grpid IS NOT NULL"
    )

    # Lagrer tilgangen appen får fra Withings etter at brukeren kobler til vekten
    # sin (se /withings/connect). Kun én rad - appen er for én person.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS withings_konto (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            utloper TEXT NOT NULL,
            withings_bruker_id TEXT,
            siste_maling_epoch INTEGER NOT NULL DEFAULT 0,
            sist_synket TEXT
        )
        """
    )
    withings_konto_kolonner = {row["name"] for row in conn.execute("PRAGMA table_info(withings_konto)")}
    if "siste_feil" not in withings_konto_kolonner:
        conn.execute("ALTER TABLE withings_konto ADD COLUMN siste_feil TEXT")
    if "siste_feil_tidspunkt" not in withings_konto_kolonner:
        conn.execute("ALTER TABLE withings_konto ADD COLUMN siste_feil_tidspunkt TEXT")

    # Alle måletyper fra Withings (vekt, fettprosent, muskelmasse, puls osv.),
    # ikke bare vekten - se WITHINGS_MALETYPER. UNIQUE(grpid, type) gjør synk
    # trygt å kjøre flere ganger uten å lage duplikater.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS withings_malinger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grpid TEXT NOT NULL,
            dato TEXT NOT NULL,
            type INTEGER NOT NULL,
            verdi REAL NOT NULL,
            UNIQUE(grpid, type)
        )
        """
    )

    # Samme mønster som withings_konto/withings_malinger over, for Oura-ringen.
    # siste_dag_synket brukes som start_date i neste synk (Ouras API er
    # dato-basert, ikke epoch-basert som Withings sin).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS oura_konto (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            utloper TEXT NOT NULL,
            siste_dag_synket TEXT,
            sist_synket TEXT
        )
        """
    )
    oura_konto_kolonner = {row["name"] for row in conn.execute("PRAGMA table_info(oura_konto)")}
    if "siste_feil" not in oura_konto_kolonner:
        conn.execute("ALTER TABLE oura_konto ADD COLUMN siste_feil TEXT")
    if "siste_feil_tidspunkt" not in oura_konto_kolonner:
        conn.execute("ALTER TABLE oura_konto ADD COLUMN siste_feil_tidspunkt TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS oura_malinger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dato TEXT NOT NULL,
            type TEXT NOT NULL,
            verdi REAL NOT NULL,
            UNIQUE(dato, type)
        )
        """
    )

    conn.commit()
    livsstil.opprett_tabeller(conn)
    conn.close()


# ---- Withings (automatisk henting av vekt) ----

def withings_hent_og_lagre_token(**felter):
    """Henter access/refresh-token fra Withings (enten med en engangskode fra
    innlogging, eller med et refresh_token) og lagrer resultatet. Returnerer
    en feiltekst hvis noe gikk galt, ellers None."""
    data = {
        "action": "requesttoken",
        "client_id": WITHINGS_CLIENT_ID,
        "client_secret": WITHINGS_CLIENT_SECRET,
        **felter,
    }
    try:
        svar = requests.post("https://wbsapi.withings.net/v2/oauth2", data=data, timeout=15).json()
    except requests.RequestException as e:
        return str(e)

    if svar.get("status") != 0:
        return svar.get("error") or f"Withings-feil (status {svar.get('status')})"

    kropp = svar["body"]
    utloper = (datetime.now(timezone.utc) + timedelta(seconds=int(kropp["expires_in"]) - 60)).isoformat()

    db = get_db()
    db.execute(
        """
        INSERT INTO withings_konto (id, access_token, refresh_token, utloper, withings_bruker_id)
        VALUES (1, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            utloper = excluded.utloper,
            withings_bruker_id = excluded.withings_bruker_id
        """,
        (kropp["access_token"], kropp["refresh_token"], utloper, str(kropp.get("userid", ""))),
    )
    db.commit()
    return None


def withings_hent_gyldig_token():
    """Returnerer (access_token, None) eller (None, feiltekst). Fornyer selv
    tilgangen via refresh_token når den er i ferd med å gå ut."""
    db = get_db()
    rad = db.execute("SELECT * FROM withings_konto WHERE id = 1").fetchone()
    if rad is None:
        return None, "ikke_tilkoblet"

    if datetime.now(timezone.utc) < datetime.fromisoformat(rad["utloper"]):
        return rad["access_token"], None

    feil = withings_hent_og_lagre_token(grant_type="refresh_token", refresh_token=rad["refresh_token"])
    if feil:
        return None, feil

    rad = db.execute("SELECT access_token FROM withings_konto WHERE id = 1").fetchone()
    return rad["access_token"], None


def _lagre_withings_feil(feil):
    db = get_db()
    db.execute(
        "UPDATE withings_konto SET siste_feil = ?, siste_feil_tidspunkt = ? WHERE id = 1",
        (str(feil)[:300], datetime.now(timezone.utc).isoformat()),
    )
    db.commit()


def withings_synk():
    """Henter alle nye målinger fra Withings (vekt, fettprosent, muskelmasse,
    puls osv. - se WITHINGS_MALETYPER) og lagrer dem i withings_malinger.
    Vekten (type 1) legges i tillegg inn i vektlogg, som før.
    Returnerer (antall_nye, None) eller (None, feiltekst). Ved feil (utenom
    "ikke_tilkoblet", som bare betyr at Withings aldri er koblet til) lagres
    feilen slik at /api/oversikt kan varsle om at synken har stoppet opp."""
    access_token, feil = withings_hent_gyldig_token()
    if feil:
        if feil != "ikke_tilkoblet":
            _lagre_withings_feil(feil)
        return None, feil

    db = get_db()
    rad = db.execute("SELECT siste_maling_epoch FROM withings_konto WHERE id = 1").fetchone()

    parametre = {"action": "getmeas", "category": 1}
    if rad["siste_maling_epoch"]:
        parametre["lastupdate"] = rad["siste_maling_epoch"]

    try:
        svar = requests.get(
            "https://wbsapi.withings.net/measure",
            params=parametre,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        ).json()
    except requests.RequestException as e:
        _lagre_withings_feil(str(e))
        return None, str(e)

    if svar.get("status") != 0:
        feil = svar.get("error") or f"Withings-feil (status {svar.get('status')})"
        _lagre_withings_feil(feil)
        return None, feil

    antall_nye = 0
    nyeste_epoch = rad["siste_maling_epoch"]

    for gruppe in svar["body"].get("measuregrps", []):
        nyeste_epoch = max(nyeste_epoch, gruppe["date"])
        dato_lokal = datetime.fromtimestamp(gruppe["date"], tz=ZoneInfo("Europe/Oslo")).date().isoformat()
        for m in gruppe.get("measures", []):
            if m.get("type") not in WITHINGS_MALETYPER:
                continue
            verdi = round(m["value"] * (10 ** m["unit"]), 2)

            cur = db.execute(
                "INSERT OR IGNORE INTO withings_malinger (grpid, dato, type, verdi) VALUES (?, ?, ?, ?)",
                (str(gruppe["grpid"]), dato_lokal, m["type"], verdi),
            )
            if cur.rowcount:
                antall_nye += 1

            if m["type"] == 1:
                db.execute(
                    "INSERT OR IGNORE INTO vektlogg (dato, vekt_kg, notater, withings_grpid) VALUES (?, ?, '', ?)",
                    (dato_lokal, verdi, str(gruppe["grpid"])),
                )

    db.execute(
        "UPDATE withings_konto SET siste_maling_epoch = ?, sist_synket = ?, "
        "siste_feil = NULL, siste_feil_tidspunkt = NULL WHERE id = 1",
        (nyeste_epoch, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    return antall_nye, None


@app.route("/withings/connect")
def withings_connect():
    """Sender brukeren til Withings for å logge inn og godkjenne tilgang."""
    state = secrets.token_urlsafe(24)
    db = get_db()
    db.execute("UPDATE innstillinger SET withings_pending_state = ? WHERE id = 1", (state,))
    db.commit()
    parametre = {
        "response_type": "code",
        "client_id": WITHINGS_CLIENT_ID,
        "redirect_uri": WITHINGS_REDIRECT_URI,
        "scope": "user.metrics",
        "state": state,
    }
    return redirect("https://account.withings.com/oauth2_user/authorize2?" + urlencode(parametre))


@app.route("/withings/callback")
def withings_callback():
    """Withings sender brukeren hit etter innlogging/godkjenning på deres side."""
    code = request.args.get("code")
    if not code:
        return Response("Withings-tilkoblingen er klar til bruk.", mimetype="text/plain")

    db = get_db()
    rad = db.execute("SELECT withings_pending_state FROM innstillinger WHERE id = 1").fetchone()
    ventet_state = rad["withings_pending_state"] if rad else None
    db.execute("UPDATE innstillinger SET withings_pending_state = NULL WHERE id = 1")
    db.commit()

    if not ventet_state or request.args.get("state") != ventet_state:
        return Response("Ugyldig forespørsel (feil state). Prøv å koble til på nytt.", status=400, mimetype="text/plain")

    feil = withings_hent_og_lagre_token(
        grant_type="authorization_code", code=code, redirect_uri=WITHINGS_REDIRECT_URI
    )
    if feil:
        return Response(f"Noe gikk galt ved tilkobling til Withings: {feil}", status=502, mimetype="text/plain")

    withings_synk()
    return redirect(url_for("index"))


@app.route("/api/withings/status")
def api_withings_status():
    db = get_db()
    rad = db.execute("SELECT sist_synket FROM withings_konto WHERE id = 1").fetchone()
    return jsonify({"tilkoblet": rad is not None, "sist_synket": rad["sist_synket"] if rad else None})


@app.route("/api/withings/data")
def api_withings_data():
    db = get_db()
    rader = db.execute(
        "SELECT dato, type, verdi FROM withings_malinger ORDER BY dato DESC, type"
    ).fetchall()

    dager = {}
    for r in rader:
        navn, enhet = WITHINGS_MALETYPER.get(r["type"], (f"Type {r['type']}", ""))
        dager.setdefault(r["dato"], []).append({"navn": navn, "verdi": r["verdi"], "enhet": enhet})

    return jsonify([{"dato": dato, "malinger": malinger} for dato, malinger in dager.items()])


@app.route("/api/withings/synk", methods=["POST"])
def api_withings_synk():
    antall, feil = withings_synk()
    if feil == "ikke_tilkoblet":
        return jsonify({"error": "Ikke koblet til Withings ennå."}), 400
    if feil:
        return jsonify({"error": feil}), 502
    return jsonify({"nye": antall})


@app.route("/api/withings/synk-automatisk")
def api_withings_synk_automatisk():
    """Beregnet på en egen daglig Snarveier-automatisering (kl. 10) - samme
    kode-beskyttelse som /api/varsel, siden telefonen ikke kan logge inn."""
    if VARSEL_NOKKEL and request.args.get("kode") != VARSEL_NOKKEL:
        return Response("Feil eller manglende kode.", status=403, mimetype="text/plain")

    antall, feil = withings_synk()
    if feil == "ikke_tilkoblet":
        return Response("Ikke koblet til Withings ennå.", mimetype="text/plain")
    if feil:
        return Response(f"Withings-synk feilet: {feil}", status=502, mimetype="text/plain")
    return Response(f"Withings synkronisert: {antall} nye målinger.", mimetype="text/plain")


# ---- Oura (automatisk henting av søvn/restitusjon/aktivitet) ----

def oura_hent_og_lagre_token(**felter):
    """Henter access/refresh-token fra Oura (enten med en engangskode fra
    innlogging, eller med et refresh_token) og lagrer resultatet. Returnerer
    en feiltekst hvis noe gikk galt, ellers None."""
    try:
        svar = requests.post(
            "https://api.ouraring.com/oauth/token",
            data=felter,
            auth=(OURA_CLIENT_ID, OURA_CLIENT_SECRET),
            timeout=15,
        )
    except requests.RequestException as e:
        return str(e)

    if svar.status_code != 200:
        return f"Oura-feil ({svar.status_code}): {svar.text[:200]}"

    kropp = svar.json()
    utloper = (datetime.now(timezone.utc) + timedelta(seconds=int(kropp["expires_in"]) - 60)).isoformat()

    db = get_db()
    db.execute(
        """
        INSERT INTO oura_konto (id, access_token, refresh_token, utloper)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            utloper = excluded.utloper
        """,
        (kropp["access_token"], kropp["refresh_token"], utloper),
    )
    db.commit()
    return None


def oura_hent_gyldig_token():
    """Returnerer (access_token, None) eller (None, feiltekst). Fornyer selv
    tilgangen via refresh_token når den er i ferd med å gå ut."""
    db = get_db()
    rad = db.execute("SELECT * FROM oura_konto WHERE id = 1").fetchone()
    if rad is None:
        return None, "ikke_tilkoblet"

    if datetime.now(timezone.utc) < datetime.fromisoformat(rad["utloper"]):
        return rad["access_token"], None

    feil = oura_hent_og_lagre_token(grant_type="refresh_token", refresh_token=rad["refresh_token"])
    if feil:
        return None, feil

    rad = db.execute("SELECT access_token FROM oura_konto WHERE id = 1").fetchone()
    return rad["access_token"], None


def _lagre_oura_feil(feil):
    db = get_db()
    db.execute(
        "UPDATE oura_konto SET siste_feil = ?, siste_feil_tidspunkt = ? WHERE id = 1",
        (str(feil)[:300], datetime.now(timezone.utc).isoformat()),
    )
    db.commit()


def oura_synk():
    """Henter nye dagssammendrag (søvn-, restitusjon- og aktivitet-poengsum,
    pluss skritt) fra Oura og lagrer dem i oura_malinger.
    Returnerer (antall, None) eller (None, feiltekst). Se withings_synk for
    begrunnelsen bak feillagringen."""
    access_token, feil = oura_hent_gyldig_token()
    if feil:
        if feil != "ikke_tilkoblet":
            _lagre_oura_feil(feil)
        return None, feil

    db = get_db()
    rad = db.execute("SELECT siste_dag_synket FROM oura_konto WHERE id = 1").fetchone()
    start_dato = rad["siste_dag_synket"] or (date.today() - timedelta(days=7)).isoformat()
    slutt_dato = date.today().isoformat()

    headers = {"Authorization": f"Bearer {access_token}"}
    parametre = {"start_date": start_dato, "end_date": slutt_dato}

    antall_nye = 0
    nyeste_dag = start_dato

    for sti, type_navn in (
        ("daily_sleep", "sovn_score"),
        ("daily_readiness", "restitusjon_score"),
        ("daily_activity", "aktivitet_score"),
    ):
        try:
            svar = requests.get(
                f"https://api.ouraring.com/v2/usercollection/{sti}",
                params=parametre,
                headers=headers,
                timeout=15,
            )
        except requests.RequestException as e:
            _lagre_oura_feil(str(e))
            return None, str(e)

        if svar.status_code != 200:
            feil = f"Oura-feil ({svar.status_code}) på {sti}: {svar.text[:200]}"
            _lagre_oura_feil(feil)
            return None, feil

        for rad_data in svar.json().get("data", []):
            dag = rad_data.get("day")
            score = rad_data.get("score")
            if dag is None or score is None:
                continue
            nyeste_dag = max(nyeste_dag, dag)

            db.execute(
                "INSERT INTO oura_malinger (dato, type, verdi) VALUES (?, ?, ?) "
                "ON CONFLICT(dato, type) DO UPDATE SET verdi = excluded.verdi",
                (dag, type_navn, score),
            )
            antall_nye += 1

            if sti == "daily_activity" and rad_data.get("steps") is not None:
                db.execute(
                    "INSERT INTO oura_malinger (dato, type, verdi) VALUES (?, 'skritt', ?) "
                    "ON CONFLICT(dato, type) DO UPDATE SET verdi = excluded.verdi",
                    (dag, rad_data["steps"]),
                )
                antall_nye += 1

    db.execute(
        "UPDATE oura_konto SET siste_dag_synket = ?, sist_synket = ?, "
        "siste_feil = NULL, siste_feil_tidspunkt = NULL WHERE id = 1",
        (nyeste_dag, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    return antall_nye, None


@app.route("/oura/connect")
def oura_connect():
    """Sender brukeren til Oura for å logge inn og godkjenne tilgang."""
    state = secrets.token_urlsafe(24)
    db = get_db()
    db.execute("UPDATE innstillinger SET oura_pending_state = ? WHERE id = 1", (state,))
    db.commit()
    parametre = {
        "response_type": "code",
        "client_id": OURA_CLIENT_ID,
        "redirect_uri": OURA_REDIRECT_URI,
        "scope": "daily",
        "state": state,
    }
    return redirect("https://cloud.ouraring.com/oauth/authorize?" + urlencode(parametre))


@app.route("/oura/callback")
def oura_callback():
    """Oura sender brukeren hit etter innlogging/godkjenning på deres side."""
    code = request.args.get("code")
    if not code:
        return Response("Oura-tilkoblingen er klar til bruk.", mimetype="text/plain")

    db = get_db()
    rad = db.execute("SELECT oura_pending_state FROM innstillinger WHERE id = 1").fetchone()
    ventet_state = rad["oura_pending_state"] if rad else None
    db.execute("UPDATE innstillinger SET oura_pending_state = NULL WHERE id = 1")
    db.commit()

    if not ventet_state or request.args.get("state") != ventet_state:
        return Response("Ugyldig forespørsel (feil state). Prøv å koble til på nytt.", status=400, mimetype="text/plain")

    feil = oura_hent_og_lagre_token(
        grant_type="authorization_code", code=code, redirect_uri=OURA_REDIRECT_URI
    )
    if feil:
        return Response(f"Noe gikk galt ved tilkobling til Oura: {feil}", status=502, mimetype="text/plain")

    oura_synk()
    return redirect(url_for("index"))


@app.route("/api/oura/status")
def api_oura_status():
    db = get_db()
    rad = db.execute("SELECT sist_synket FROM oura_konto WHERE id = 1").fetchone()
    return jsonify({"tilkoblet": rad is not None, "sist_synket": rad["sist_synket"] if rad else None})


@app.route("/api/oura/data")
def api_oura_data():
    db = get_db()
    rader = db.execute(
        "SELECT dato, type, verdi FROM oura_malinger ORDER BY dato DESC, type"
    ).fetchall()

    dager = {}
    for r in rader:
        navn, enhet = OURA_MALETYPER.get(r["type"], (r["type"], ""))
        dager.setdefault(r["dato"], []).append({"navn": navn, "verdi": r["verdi"], "enhet": enhet})

    return jsonify([{"dato": dato, "malinger": malinger} for dato, malinger in dager.items()])


@app.route("/api/oura/synk", methods=["POST"])
def api_oura_synk():
    antall, feil = oura_synk()
    if feil == "ikke_tilkoblet":
        return jsonify({"error": "Ikke koblet til Oura ennå."}), 400
    if feil:
        return jsonify({"error": feil}), 502
    return jsonify({"nye": antall})


@app.route("/api/oura/synk-automatisk")
def api_oura_synk_automatisk():
    """Beregnet på en egen daglig Snarveier-automatisering, samme
    kode-beskyttelse som /api/varsel og /api/withings/synk-automatisk."""
    if VARSEL_NOKKEL and request.args.get("kode") != VARSEL_NOKKEL:
        return Response("Feil eller manglende kode.", status=403, mimetype="text/plain")

    antall, feil = oura_synk()
    if feil == "ikke_tilkoblet":
        return Response("Ikke koblet til Oura ennå.", mimetype="text/plain")
    if feil:
        return Response(f"Oura-synk feilet: {feil}", status=502, mimetype="text/plain")
    return Response(f"Oura synkronisert: {antall} nye målinger.", mimetype="text/plain")


# ---- Oversikt (samlet dashboard: vekt, søvn, restitusjon, aktivitet, trening) ----

def _serie_og_delta(rader, desimaler):
    """rader: liste av (dato, verdi)-tupler sortert stigende på dato.
    Returnerer (serie, siste_verdi, siste_dato, delta_7d) - delta_7d er
    endringen mot nærmeste måling minst 7 dager før siste. Hvert punkt i
    serien får også et "snitt"-felt (glidende 7-dagers snitt), som brukes
    til å tegne en jevnere trendlinje oppå de daglige (ofte støyete) punktene."""
    if not rader:
        return [], None, None, None

    datoer = [date.fromisoformat(d) for d, _ in rader]
    verdier = [v for _, v in rader]
    serie = []
    for i, (d_str, v) in enumerate(rader):
        vindu = [verdier[j] for j in range(len(rader)) if 0 <= (datoer[i] - datoer[j]).days <= 6]
        serie.append({
            "dato": d_str,
            "verdi": round(v, desimaler),
            "snitt": round(sum(vindu) / len(vindu), desimaler),
        })

    siste_dato, siste_verdi = rader[-1]
    grense = (date.fromisoformat(siste_dato) - timedelta(days=7)).isoformat()
    tidligere = [v for d, v in rader if d <= grense]
    delta = round(siste_verdi - tidligere[-1], desimaler) if tidligere else None
    return serie, round(siste_verdi, desimaler), siste_dato, delta


def beregn_mal_fremgang(db, mal_vekt):
    """Hvor langt Eivin har kommet mot målvekten, og en grov anslått dato
    han når den på - basert på farten siste 30 dager. Returnerer None hvis
    ingen målvekt er satt eller ingen vekt er registrert ennå."""
    if mal_vekt is None:
        return None
    forste = db.execute("SELECT dato, vekt_kg FROM vektlogg ORDER BY dato LIMIT 1").fetchone()
    siste = db.execute("SELECT dato, vekt_kg FROM vektlogg ORDER BY dato DESC LIMIT 1").fetchone()
    if forste is None or siste is None:
        return None

    start_vekt = forste["vekt_kg"]
    naa_vekt = siste["vekt_kg"]
    gjenstaende = round(naa_vekt - mal_vekt, 1)

    prosent = None
    if start_vekt != mal_vekt:
        prosent = round(max(0, min(100, (start_vekt - naa_vekt) / (start_vekt - mal_vekt) * 100)))

    projisert_dato = None
    tretti_dager_siden = (date.today() - timedelta(days=30)).isoformat()
    tidlig_rad = db.execute(
        "SELECT dato, vekt_kg FROM vektlogg WHERE dato <= ? ORDER BY dato DESC LIMIT 1",
        (tretti_dager_siden,),
    ).fetchone()
    if tidlig_rad is None:
        tidlig_rad = forste
    dager_span = (date.fromisoformat(siste["dato"]) - date.fromisoformat(tidlig_rad["dato"])).days
    if dager_span >= 10 and gjenstaende != 0:
        rate_per_dag = (tidlig_rad["vekt_kg"] - naa_vekt) / dager_span  # positiv = går ned
        beveger_mot_mal = (gjenstaende > 0 and rate_per_dag > 0) or (gjenstaende < 0 and rate_per_dag < 0)
        if beveger_mot_mal:
            dager_igjen = abs(gjenstaende) / abs(rate_per_dag)
            if dager_igjen < 3650:
                projisert_dato = (date.today() + timedelta(days=round(dager_igjen))).isoformat()

    return {
        "mal_vekt_kg": mal_vekt,
        "start_vekt_kg": start_vekt,
        "gjenstaende_kg": gjenstaende,
        "prosent_fullfort": prosent,
        "projisert_dato": projisert_dato,
    }


def beregn_innsikt(db, start_dato):
    """Enkel sammenligning: gikk vekten mer ned i uker med mange alkoholfrie
    dager (minst 5 av 7) enn i uker med færre? Trenger minst 2 uker i hver
    gruppe for å si noe fornuftig - ellers "ikke nok data ennå"."""
    i_dag = livsstil.i_dag_oslo()
    uke_start = livsstil.mandag_for(i_dag) - timedelta(days=7)
    eldste_grense = uke_start - timedelta(days=365)

    hoy, lav = [], []
    while uke_start >= start_dato and uke_start >= eldste_grense:
        dato_strenger = [(uke_start + timedelta(days=i)).isoformat() for i in range(7)]
        sjekker = db.execute(
            "SELECT alkohol FROM dagssjekk WHERE dato IN ({})".format(",".join("?" * 7)),
            dato_strenger,
        ).fetchall()
        vekt_rader = db.execute(
            "SELECT vekt_kg FROM vektlogg WHERE dato IN ({}) ORDER BY dato".format(",".join("?" * 7)),
            dato_strenger,
        ).fetchall()
        if len(sjekker) >= 5 and len(vekt_rader) >= 2:
            alkoholfrie = sum(1 for r in sjekker if not r["alkohol"])
            delta = vekt_rader[-1]["vekt_kg"] - vekt_rader[0]["vekt_kg"]
            (hoy if alkoholfrie >= 5 else lav).append(delta)
        uke_start -= timedelta(days=7)

    if len(hoy) < 2 or len(lav) < 2:
        return {"nok_data": False}

    return {
        "nok_data": True,
        "uker_hoy": len(hoy),
        "uker_lav": len(lav),
        "snitt_delta_hoy": round(sum(hoy) / len(hoy), 1),
        "snitt_delta_lav": round(sum(lav) / len(lav), 1),
    }


def _tilkobling_status(db, tabell):
    """Status for en Withings/Oura-tilkobling: tilkoblet eller ikke, og en
    advarsel hvis siste synk feilet eller det er over to døgn siden sist
    vellykkede synk (tyder på at noe har sluttet å virke i det stille)."""
    rad = db.execute(f"SELECT sist_synket, siste_feil FROM {tabell} WHERE id = 1").fetchone()
    if rad is None:
        return {"tilkoblet": False, "advarsel": False, "melding": None}

    if rad["siste_feil"]:
        return {"tilkoblet": True, "advarsel": True, "melding": rad["siste_feil"]}

    if rad["sist_synket"]:
        sist = datetime.fromisoformat(rad["sist_synket"])
        if datetime.now(timezone.utc) - sist > timedelta(hours=48):
            return {"tilkoblet": True, "advarsel": True, "melding": "Har ikke synkronisert på over to døgn."}

    return {"tilkoblet": True, "advarsel": False, "melding": None}


@app.route("/api/vekt-detaljer")
def api_vekt_detaljer():
    """Full utvikling (ikke bare siste verdi) for hver Withings-måling utenom
    selve vekten - fettprosent, muskelmasse, kroppsvann osv. Brukes til
    "Se utvikling"-visningen når man trykker seg inn på Vekt-kortet."""
    dager = max(7, min(int(request.args.get("dager", 30)), 365))
    fra_dato = (date.today() - timedelta(days=dager)).isoformat()
    db = get_db()

    metrikker = []
    for type_id, (navn, enhet) in WITHINGS_MALETYPER.items():
        if type_id == 1:
            continue
        rader = [
            (r["dato"], r["verdi"])
            for r in db.execute(
                "SELECT dato, verdi FROM withings_malinger WHERE type = ? AND dato >= ? ORDER BY dato",
                (type_id, fra_dato),
            ).fetchall()
        ]
        desimaler = 1 if enhet in ("kg", "%") else 0
        serie, siste, siste_dato, delta = _serie_og_delta(rader, desimaler)
        if siste is None:
            continue
        metrikker.append({
            "id": type_id, "navn": navn, "enhet": enhet,
            "siste": siste, "siste_dato": siste_dato, "delta_7d": delta,
            "serie": serie,
        })

    return jsonify(metrikker)


@app.route("/api/oversikt")
def api_oversikt():
    """Samlet data til dashboardet - én forespørsel i stedet for at
    frontend må spørre withings/oura/trening hver for seg."""
    dager = max(7, min(int(request.args.get("dager", 30)), 365))
    fra_dato = (date.today() - timedelta(days=dager)).isoformat()
    db = get_db()

    innstillinger_rad = db.execute("SELECT start_dato, mal_vekt_kg FROM innstillinger WHERE id = 1").fetchone()
    start_dato = date.fromisoformat(innstillinger_rad["start_dato"])
    mal_vekt = innstillinger_rad["mal_vekt_kg"]

    def hent(sql, *param):
        return [(r["dato"], r["verdi"]) for r in db.execute(sql, param).fetchall()]

    vekt_rader = hent(
        "SELECT dato, vekt_kg AS verdi FROM vektlogg WHERE dato >= ? ORDER BY dato", fra_dato
    )
    sovn_rader = hent(
        "SELECT dato, verdi FROM oura_malinger WHERE type = 'sovn_score' AND dato >= ? ORDER BY dato", fra_dato
    )
    restitusjon_rader = hent(
        "SELECT dato, verdi FROM oura_malinger WHERE type = 'restitusjon_score' AND dato >= ? ORDER BY dato", fra_dato
    )
    aktivitet_rader = hent(
        "SELECT dato, verdi FROM oura_malinger WHERE type = 'aktivitet_score' AND dato >= ? ORDER BY dato", fra_dato
    )
    skritt_rader = hent(
        "SELECT dato, verdi FROM oura_malinger WHERE type = 'skritt' AND dato >= ? ORDER BY dato", fra_dato
    )

    def sekundaer_verdi(rader, navn, enhet, desimaler):
        _, siste, _, _ = _serie_og_delta(rader, desimaler)
        return {"navn": navn, "enhet": enhet, "verdi": siste} if siste is not None else None

    # Alle Withings-målinger utenom selve vekten (type 1) vises som ekstra
    # nøkkeltall under Vekt-kortet, siden Eivin vil se alt Withings-vekten
    # sender - ikke bare fettprosent.
    withings_sekundaer = []
    for type_id, (navn, enhet) in WITHINGS_MALETYPER.items():
        if type_id == 1:
            continue
        rader = hent(
            "SELECT dato, verdi FROM withings_malinger WHERE type = ? AND dato >= ? ORDER BY dato",
            type_id, fra_dato,
        )
        verdi = sekundaer_verdi(rader, navn, enhet, 1)
        if verdi:
            withings_sekundaer.append(verdi)

    aktivitet_sekundaer = []
    skritt_verdi = sekundaer_verdi(skritt_rader, "Skritt", "", 0)
    if skritt_verdi:
        aktivitet_sekundaer.append(skritt_verdi)

    kort = []
    for id_, navn, enhet, desimaler, rader, sekundaer in (
        ("vekt", "Vekt", "kg", 1, vekt_rader, withings_sekundaer),
        ("sovn", "Søvn", "", 0, sovn_rader, []),
        ("restitusjon", "Restitusjon", "", 0, restitusjon_rader, []),
        ("aktivitet", "Aktivitet", "", 0, aktivitet_rader, aktivitet_sekundaer),
    ):
        serie, siste, siste_dato, delta = _serie_og_delta(rader, desimaler)
        kort_data = {
            "id": id_, "navn": navn, "enhet": enhet,
            "siste": siste, "siste_dato": siste_dato, "delta_7d": delta,
            "serie": serie, "sekundaer": sekundaer,
        }
        if id_ == "vekt":
            kort_data["mal"] = beregn_mal_fremgang(db, mal_vekt)
        kort.append(kort_data)

    i_dag = livsstil.i_dag_oslo()
    trening_uke = []
    for i in range(6, -1, -1):
        d = i_dag - timedelta(days=i)
        status = livsstil.dagsstatus(db, d.isoformat())
        trening_uke.append({
            "dato": d.isoformat(),
            "ukedag_kort": UKEDAGER[d.isoweekday() - 1][:2],
            "gjennomfort": bool(status["trent"]) if status else None,
        })

    return jsonify({
        "tilkoblinger": {
            "withings": _tilkobling_status(db, "withings_konto"),
            "oura": _tilkobling_status(db, "oura_konto"),
        },
        "kort": kort,
        "trening_uke": trening_uke,
        "alkoholfri_rekke": livsstil.alkoholfrie_hverdager_pa_rad(db, i_dag),
        "innsikt": beregn_innsikt(db, start_dato),
    })


# ---- Historikk ----

@app.route("/api/dagssjekk", methods=["GET"])
def api_hent_dagssjekk():
    dato = request.args.get("dato") or livsstil.i_dag_oslo().isoformat()
    return jsonify(livsstil.dagsstatus(get_db(), dato))


@app.route("/api/dagssjekk", methods=["POST"])
def api_lagre_dagssjekk():
    data = request.get_json(force=True) or {}
    dato = data.get("dato") or livsstil.i_dag_oslo().isoformat()
    try:
        rad = livsstil.lagre_dagssjekk(
            get_db(), dato, data.get("fastet"), data.get("alkohol"), data.get("alkohol_enheter"),
            data.get("trent"), data.get("syk"), data.get("notat"),
        )
    except ValueError:
        return jsonify({"error": "Ugyldig dato"}), 400
    return jsonify(rad)


@app.route("/api/historikk")
def api_historikk():
    db = get_db()
    datoer = sorted(
        {r["dato"] for r in db.execute("SELECT dato FROM dagssjekk")}
        | {r["dato"] for r in db.execute("SELECT dato FROM dagslogg")},
        reverse=True,
    )
    dager = []
    for dato in datoer:
        status = livsstil.dagsstatus(db, dato)
        status["ukedag_navn"] = UKEDAGER[date.fromisoformat(dato).isoweekday() - 1]
        dager.append(status)

    grense = (livsstil.i_dag_oslo() - timedelta(days=30)).isoformat()
    siste = [d for d in dager if d["dato"] >= grense]
    hverdager = [d for d in siste if date.fromisoformat(d["dato"]).isoweekday() <= 4]
    return jsonify({
        "dager": dager,
        "stats": {
            "totalt_registrert": len(siste),
            "fastedager": sum(1 for d in siste if d["fastet"]),
            "treningsdager": sum(1 for d in siste if d["trent"]),
            "alkoholfrie_hverdager_prosent": (
                round(100 * sum(1 for d in hverdager if not d["alkohol"]) / len(hverdager)) if hverdager else 0
            ),
        },
    })


# ---- Coach, mat og helg ----

def _helgeplan(db, uke_start):
    rad = db.execute("SELECT * FROM helgeplan WHERE uke_start = ?", (uke_start.isoformat(),)).fetchone()
    if not rad:
        return None
    return {
        "planlagte_enheter": rad["planlagte_enheter"],
        "tips": json.loads(rad["tips"] or "[]"),
        "oppsummering": rad["oppsummering"],
    }


@app.route("/api/i-dag")
def api_i_dag():
    db = get_db()
    i_dag = livsstil.i_dag_oslo()
    i_dag_str = i_dag.isoformat()
    melding = coach.hent_eller_lag_dagsmelding(db, i_dag)
    plan = livsstil.hent_eller_lag_ukeplan(db, livsstil.mandag_for(i_dag), lag_plan=coach.lag_ukeplan_med_claude)
    return jsonify({
        "dato": i_dag_str,
        "ukedag_navn": UKEDAGER[i_dag.isoweekday() - 1],
        "dagssjekk": livsstil.dagsstatus(db, i_dag_str),
        "melding": {"tittel": melding["tittel"], "tekst": melding["tekst"], "kilde": melding["kilde"]},
        "treningsdag": bool(melding["treningsdag"]),
        "flytt_grunn": melding["flyttet_fra"],
        "middag": livsstil.middag_for_dag(plan, i_dag_str),
        "treningsdager": plan["treningsdager"],
        "alkoholfri_rekke": livsstil.alkoholfrie_hverdager_pa_rad(db, i_dag),
        "helg": _helgeplan(db, livsstil.mandag_for(i_dag)),
        "er_fredag_til_sondag": i_dag.isoweekday() >= 5,
    })


@app.route("/api/mat")
def api_mat():
    uke_start = livsstil.mandag_for(livsstil.i_dag_oslo())
    return jsonify(livsstil.hent_eller_lag_ukeplan(get_db(), uke_start, lag_plan=coach.lag_ukeplan_med_claude))


@app.route("/api/mat/bytt", methods=["POST"])
def api_mat_bytt():
    data = request.get_json(force=True) or {}
    uke_start = livsstil.mandag_for(livsstil.i_dag_oslo())
    try:
        return jsonify(coach.bytt_middag(get_db(), uke_start, str(data.get("dag") or "")))
    except ValueError:
        return jsonify({"error": "Ugyldig dag"}), 400


@app.route("/api/coach/chat", methods=["GET"])
def api_chat_historikk():
    rader = get_db().execute("SELECT * FROM (SELECT * FROM chat ORDER BY id DESC LIMIT 30) ORDER BY id").fetchall()
    return jsonify([dict(r) for r in rader])


@app.route("/api/coach/chat", methods=["POST"])
def api_chat():
    tekst = ((request.get_json(force=True) or {}).get("tekst") or "").strip()
    if not tekst:
        return jsonify({"error": "Skriv noe først"}), 400
    return jsonify({"svar": coach.svar_chat(get_db(), tekst[:2000])})


@app.route("/api/coach/vanskelig", methods=["POST"])
def api_vanskelig():
    return jsonify({"tekst": coach.vanskelig_na(get_db())})


@app.route("/api/helg", methods=["POST"])
def api_helg():
    verdi = (request.get_json(force=True) or {}).get("planlagte_enheter")
    try:
        enheter = int(verdi)
    except (TypeError, ValueError):
        return jsonify({"error": "Skriv et tall"}), 400
    if isinstance(verdi, bool) or not 0 <= enheter <= 30:
        return jsonify({"error": "Velg mellom 0 og 30 enheter"}), 400
    db = get_db()
    uke_start = livsstil.mandag_for(livsstil.i_dag_oslo())
    tips = coach.helg_tips(db, enheter)
    db.execute(
        """
        INSERT INTO helgeplan (uke_start, planlagte_enheter, tips) VALUES (?, ?, ?)
        ON CONFLICT(uke_start) DO UPDATE SET planlagte_enheter = excluded.planlagte_enheter, tips = excluded.tips
        """,
        (uke_start.isoformat(), enheter, json.dumps(tips, ensure_ascii=False)),
    )
    db.commit()
    return jsonify({"planlagte_enheter": enheter, "tips": tips})


# ---- Målvekt ----

@app.route("/api/mal-vekt", methods=["POST"])
def api_sett_mal_vekt():
    data = request.get_json(force=True)
    verdi = data.get("mal_vekt_kg")
    db = get_db()

    if verdi in (None, ""):
        db.execute("UPDATE innstillinger SET mal_vekt_kg = NULL WHERE id = 1")
        db.commit()
        return jsonify({"mal_vekt_kg": None})

    try:
        mal = float(str(verdi).replace(",", "."))
    except (TypeError, ValueError):
        return jsonify({"error": "Ugyldig målvekt"}), 400

    db.execute("UPDATE innstillinger SET mal_vekt_kg = ? WHERE id = 1", (mal,))
    db.commit()
    return jsonify({"mal_vekt_kg": mal})


# ---- Sikkerhetskopi ----

@app.route("/api/backup")
def api_backup():
    """Laster ned en trygg, konsistent kopi av hele databasen (VACUUM INTO
    lager en ferdig, ukorrupt fil selv om noe skulle skje midt i en skriving
    et annet sted i appen akkurat da)."""
    db = get_db()
    fd, midlertidig_sti = mkstemp(suffix=".db")
    os.close(fd)
    os.remove(midlertidig_sti)  # VACUUM INTO krever at filen ikke finnes fra før
    db.execute("VACUUM INTO ?", (midlertidig_sti,))

    @after_this_request
    def rydd_opp(response):
        try:
            os.remove(midlertidig_sti)
        except OSError:
            pass
        return response

    filnavn = f"superhuman-backup-{date.today().isoformat()}.db"
    return send_file(midlertidig_sti, as_attachment=True, download_name=filnavn, mimetype="application/octet-stream")


# ---- Vektlogg ----

@app.route("/api/vekt", methods=["GET"])
def api_list_vekt():
    db = get_db()
    rows = db.execute("SELECT * FROM vektlogg ORDER BY dato").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/vekt", methods=["POST"])
def api_create_vekt():
    data = request.get_json(force=True)
    dato_str = data.get("dato") or date.today().isoformat()
    try:
        vekt_kg = float(str(data.get("vekt_kg")).replace(",", "."))
    except (TypeError, ValueError):
        return jsonify({"error": "Ugyldig vekt"}), 400
    notater = (data.get("notater") or "").strip()

    db = get_db()
    cur = db.execute(
        "INSERT INTO vektlogg (dato, vekt_kg, notater) VALUES (?, ?, ?)",
        (dato_str, vekt_kg, notater),
    )
    db.commit()
    row = db.execute("SELECT * FROM vektlogg WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/vekt/<int:vekt_id>", methods=["DELETE"])
def api_delete_vekt(vekt_id):
    db = get_db()
    db.execute("DELETE FROM vektlogg WHERE id = ?", (vekt_id,))
    db.commit()
    return "", 204


@app.route("/")
def index():
    return app.send_static_file("index.html")


def open_browser(port):
    webbrowser.open(f"http://127.0.0.1:{port}")


def finn_lokal_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


# Railway (og de fleste andre skytjenester) setter PORT selv og har ingen nettleser
# å åpne - da hopper vi over det som bare gir mening på PC-en hjemme.
KJORER_I_SKYEN = "PORT" in os.environ

# Kjører uansett om appen startes direkte (python app.py, lokalt) eller via
# gunicorn (i skyen, se Procfile) - gunicorn importerer bare "app" og hopper
# over __main__-blokken under, så databasen må klargjøres her i stedet.
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5003))

    if KJORER_I_SKYEN:
        print(f"Superhuman 2.0 kjører i skyen på port {port}.")
    else:
        Timer(1.0, lambda: open_browser(port)).start()
        lokal_ip = finn_lokal_ip()
        print("")
        print("Superhuman 2.0 kjører nå.")
        print(f"På denne PC-en: http://127.0.0.1:{port}")
        if lokal_ip:
            print(f"For å åpne appen på mobilen (samme wifi): http://{lokal_ip}:{port}")
        print("")

    app.run(debug=False, host="0.0.0.0", port=port)
