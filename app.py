import json
import os
import secrets
import socket
import sqlite3
import webbrowser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Timer
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from flask import Flask, Response, g, jsonify, redirect, request, session, url_for

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
        "login", "static", "api_varsel",
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


# ---- Treningsplanen ----
# Tre faser som bygger på hverandre. Fase 1-2 varer fire uker hver, fase 3 er åpen.
# Se README for kildene planen er basert på.

STYRKE_OVELSER = (
    "- Knebøy med manual foran brystet, lett vekt\n"
    "- Sittende manual-press for skulder/bryst\n"
    "- Støttet roing med manual, én arm av gangen (støtt deg mot stol/benk)\n"
    "- Hoftehev (glute bridge)\n"
    "- Tåhev\n"
    "2-3 sett x 10-12 reps."
)

ROING_TEKNIKK = (
    "Teknikk: dra med bena først, så hoftene, og armene sist. "
    "Ikke rund korsryggen ved catch - hold ryggen nøytral gjennom hele draget."
)

# ---- Øvelsesbibliotek ----
# Instruksjoner + animerte strekfigur-illustrasjoner (SVG) for øvelsene som brukes i planen.
# Vises som utvidbare kort i appen når man trykker på en øvelse. Hvert element som skal bevege
# seg får et data-anim-attributt (attributt:posisjon_a:posisjon_b, mellomrom-separert for flere
# attributter) som JS (se app.js: startOvelseAnimasjon) leser og animerer mellom med
# requestAnimationFrame - A -> B -> A i en evig, myk løkke.

GRUNN = '<line x1="8" y1="148" x2="152" y2="148" stroke="#dcece6" stroke-width="4" stroke-linecap="round"/>'


def _dataanim(par):
    deler = [f"{attributt}:{a}:{b}" for attributt, a, b in par if a != b]
    if not deler:
        return ""
    return f' data-anim="{" ".join(deler)}"'


def linje(x1a, y1a, x2a, y2a, x1b=None, y1b=None, x2b=None, y2b=None, farge="currentColor", sw=7):
    x1b = x1a if x1b is None else x1b
    y1b = y1a if y1b is None else y1b
    x2b = x2a if x2b is None else x2b
    y2b = y2a if y2b is None else y2b
    anim = _dataanim([("x1", x1a, x1b), ("y1", y1a, y1b), ("x2", x2a, x2b), ("y2", y2a, y2b)])
    return (
        f'<line x1="{x1a}" y1="{y1a}" x2="{x2a}" y2="{y2a}" '
        f'stroke="{farge}" stroke-width="{sw}" stroke-linecap="round"{anim}/>'
    )


def sirkel(cxa, cya, r, cxb=None, cyb=None, fill="none", med_kant=True):
    cxb = cxa if cxb is None else cxb
    cyb = cya if cyb is None else cyb
    anim = _dataanim([("cx", cxa, cxb), ("cy", cya, cyb)])
    kant = 'stroke="currentColor" stroke-width="7"' if med_kant else ""
    return f'<circle cx="{cxa}" cy="{cya}" r="{r}" fill="{fill}" {kant}{anim}/>'


def rektangel(xa, ya, w, h, xb=None, yb=None, rx=4, fill="currentColor"):
    xb = xa if xb is None else xb
    yb = ya if yb is None else yb
    anim = _dataanim([("x", xa, xb), ("y", ya, yb)])
    return f'<rect x="{xa}" y="{ya}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"{anim}/>'

OVELSER = {
    "kneboy": {
        "navn": "Knebøy med manual",
        "instruks": [
            "Hold en manual loddrett inntil brystet med begge hender, albuer pekende ned.",
            "Stå med føttene litt bredere enn hoftebredde, tær pekende lett utover.",
            "Bøy i knær og hofter som om du skal sette deg på en stol bak deg - hold brystet oppe og ryggen rett.",
            "Gå ned til lårene er parallelle med gulvet, eller så langt du kan uten at ryggen runder.",
            "Press deg opp igjen gjennom hælene til du står oppreist.",
        ],
        "fokus": "Hold ryggen rett/nøytral gjennom hele bevegelsen - ikke rund korsryggen. Se rett frem, ikke ned.",
        "svg": GRUNN
        + sirkel(94, 32, 11, 90, 22)
        + linje(94, 44, 80, 88, 90, 34, 84, 80)
        + linje(80, 88, 52, 98, 84, 80, 68, 112)
        + linje(52, 98, 58, 145, 68, 112, 58, 145)
        + linje(58, 145, 80, 148)
        + linje(93, 50, 78, 66, 89, 40, 76, 54)
        + linje(78, 66, 82, 82, 76, 54, 78, 68)
        + rektangel(73, 77, 18, 8, 69, 63)
        + sirkel(73, 81, 6, 69, 67, fill="currentColor", med_kant=False)
        + sirkel(91, 81, 6, 87, 67, fill="currentColor", med_kant=False),
    },
    "press": {
        "navn": "Sittende manual-press",
        "instruks": [
            "Sitt på en stol med god ryggstøtte, eller på kanten av en benk.",
            "Hold en manual i hver hånd i skulderhøyde, håndflatene pekende fremover.",
            "Press manualene rett opp til armene er nesten strake, uten å låse albuene helt.",
            "Senk kontrollert ned til utgangsposisjon.",
        ],
        "fokus": "Press rolig og kontrollert - ikke svai i korsryggen når du presser opp. Bruk lett vekt til du er trygg på bevegelsen.",
        "svg": GRUNN
        + linje(70, 120, 110, 120, farge="#c9dcd4", sw=10)
        + sirkel(90, 34, 11)
        + linje(90, 46, 90, 92)
        + linje(90, 92, 78, 120)
        + linje(90, 92, 102, 120)
        + linje(90, 52, 66, 24, 90, 52, 68, 50)
        + linje(90, 52, 114, 24, 90, 52, 112, 50)
        + sirkel(64, 20, 6, 68, 50, fill="currentColor", med_kant=False)
        + sirkel(116, 20, 6, 112, 50, fill="currentColor", med_kant=False),
    },
    "roing_manual": {
        "navn": "Støttet roing med manual",
        "instruks": [
            "Støtt en hånd og et kne mot en stol eller benk, slik at ryggen er flat og avlastet.",
            "Hold en manual i den andre hånden, armen strak ned mot gulvet.",
            "Dra manualen opp mot hoften/siden av kroppen, albuen tett inntil kroppen.",
            "Senk kontrollert ned igjen. Gjør ferdig ett sett, bytt side.",
        ],
        "fokus": "Hold ryggen flat/nøytral hele tiden - ikke rund den. Beveg kun armen, ikke vri i overkroppen.",
        "svg": GRUNN
        + linje(18, 100, 60, 100, farge="#c9dcd4", sw=10)
        + sirkel(118, 52, 11)
        + linje(110, 61, 70, 92)
        + linje(102, 66, 66, 100)
        + linje(70, 92, 78, 145)
        + linje(110, 63, 100, 83, 110, 63, 112, 90)
        + linje(100, 83, 108, 102, 112, 90, 112, 118)
        + sirkel(108, 104, 6, 112, 120, fill="currentColor", med_kant=False),
    },
    "hoftehev": {
        "navn": "Hoftehev (glute bridge)",
        "instruks": [
            "Ligg på ryggen med bøyde knær og føttene i gulvet, hoftebredde fra hverandre.",
            "Press gjennom hælene og løft hoftene opp til kroppen danner en rett linje fra knær til skuldre.",
            "Stram rumpemusklene øverst, hold 1-2 sekunder.",
            "Senk kontrollert ned igjen.",
        ],
        "fokus": "Trygg og bra øvelse for korsryggen - løft med rumpa, ikke ved å svaie i ryggen.",
        "svg": GRUNN
        + sirkel(30, 118, 11)
        + linje(41, 118, 85, 105, 41, 118, 85, 128)
        + linje(85, 105, 105, 118, 85, 128, 105, 118)
        + linje(105, 118, 105, 148)
        + linje(41, 118, 55, 140)
        + linje(55, 140, 80, 145),
    },
    "tahev": {
        "navn": "Tåhev",
        "instruks": [
            "Stå oppreist, gjerne med en hånd mot en vegg eller stolrygg for balanse.",
            "Løft hælene fra gulvet så du står på tærne.",
            "Hold kort på toppen.",
            "Senk kontrollert ned igjen.",
        ],
        "fokus": "Enkel og trygg øvelse. Gjør bevegelsen rolig for å kjenne leggmusklene jobbe.",
        "svg": GRUNN
        + sirkel(80, 28, 11, 80, 24)
        + linje(80, 40, 80, 100, 80, 36, 80, 94)
        + linje(80, 100, 72, 138, 80, 94, 76, 130)
        + linje(80, 100, 88, 138, 80, 94, 92, 130)
        + linje(72, 138, 80, 144, 76, 130, 80, 144)
        + linje(88, 138, 96, 144, 92, 130, 96, 144)
        + linje(80, 55, 62, 80, 80, 49, 62, 80)
        + linje(80, 55, 98, 45, 80, 49, 98, 45),
    },
    "roing_maskin": {
        "navn": "Roteknikk (rowingpad)",
        "instruks": [
            "Sitt med rak rygg og grip håndtaket med begge hender.",
            "Start hvert drag med å presse fra beina (som en knebøy bakover).",
            "Når beina er nesten strake, len overkroppen lett bakover og dra håndtaket inn mot magen med armene.",
            "Før bevegelsen tilbake i motsatt rekkefølge: armer frem, overkropp frem, så bøy knærne.",
        ],
        "fokus": "Ikke rund korsryggen når du bøyer deg frem mot starten av draget - hold brystet oppe og ryggen lang.",
        "svg": GRUNN
        + linje(15, 140, 145, 140, farge="#c9dcd4", sw=6)
        + sirkel(100, 55, 11, 115, 48)
        + linje(93, 65, 60, 95, 108, 58, 60, 95)
        + linje(60, 95, 90, 120)
        + linje(90, 120, 60, 132)
        + linje(60, 95, 30, 115)
        + linje(30, 115, 60, 132)
        + linje(88, 70, 30, 90, 100, 63, 75, 90)
        + sirkel(27, 91, 6, 72, 91, fill="currentColor", med_kant=False),
    },
}

STYRKE_ID_LISTE = ["kneboy", "press", "roing_manual", "hoftehev", "tahev"]

FASER = [
    {"fase": 1, "uke_fra": 1, "uke_til": 4, "navn": "Bygge vane og kondisjon",
     "beskrivelse": "Kun gange og roing denne perioden - ingen vekter ennå. Målet er å bygge en treningsvane og en grunnkondisjon, ikke å presse hardt."},
    {"fase": 2, "uke_fra": 5, "uke_til": 8, "navn": "Introduserer styrke",
     "beskrivelse": "Nå kommer styrkeøktene inn i tillegg til gange og roing. Fortsatt lette vekter og fokus på teknikk."},
    {"fase": 3, "uke_fra": 9, "uke_til": None, "navn": "Videre progresjon",
     "beskrivelse": "En tredje styrkeøkt og lengre utholdenhetsøkter, justert etter hvordan kroppen din responderer."},
]

# (uke_fra, uke_til, ukedag 1=mandag..7=søndag, tittel, type, beskrivelse)
# Mandag/torsdag/lørdag har egen progresjon uke for uke (1-8), resten følger fasen (uke 1-4 / 5-8).
# Fra uke 9 (fase 3) er hele uken lagt om, se egne rader nederst.
OKT_MAL = [
    # Mandag - Gange, uke for uke
    (1, 1, 1, "Gange", "gange", "Walkingpad, 15 min i rolig tempo (ca. 3,5-4 km/t)."),
    (2, 2, 1, "Gange", "gange", "Walkingpad, 18 min i samme rolige tempo."),
    (3, 3, 1, "Gange", "gange", "Walkingpad, 20 min. Prøv gjerne 1% stigning hvis du har den funksjonen."),
    (4, 4, 1, "Gange", "gange", "Walkingpad, 20 min med 2% stigning."),
    (5, 5, 1, "Gange", "gange", "Walkingpad, 25 min med 2% stigning."),
    (6, 6, 1, "Gange", "gange", "Walkingpad, 27 min med 2-3% stigning. Kjenn etter om du kan gå litt friskere (ca. 4,5 km/t)."),
    (7, 7, 1, "Gange", "gange", "Walkingpad, 30 min med 2-3% stigning."),
    (8, 8, 1, "Gange", "gange", "Walkingpad, 30 min. Valgfritt: legg inn 2 x 2 minutter litt raskere tempo underveis."),

    # Tirsdag - uke 1-4 er ren kondisjon (roing) uten styrke ennå, følger fasen fra uke 5
    (1, 1, 2, "Roing", "roing", "Rowingpad, 10 min rolig.\n" + ROING_TEKNIKK),
    (2, 2, 2, "Roing", "roing", "Rowingpad, 12 min rolig.\n" + ROING_TEKNIKK),
    (3, 3, 2, "Roing", "roing", "Rowingpad, 15 min rolig.\n" + ROING_TEKNIKK),
    (4, 4, 2, "Roing", "roing", "Rowingpad, 15 min. Kjenn etter om drag-tempoet kan være litt jevnere.\n" + ROING_TEKNIKK),
    (5, 8, 2, "Styrke", "styrke", STYRKE_OVELSER + "\nØk litt i vekt eller reps sammenlignet med forrige uke."),

    # Onsdag - Hvile, følger fasen
    (1, 4, 3, "Hvile", "hvile", "Hviledag. Evt. 15 min rolig gange hvis du har lyst."),
    (5, 8, 3, "Hvile", "hvile", "Hviledag. Evt. 20 min rolig gange."),

    # Torsdag - Roing, uke for uke
    (1, 1, 4, "Roing", "roing", "Rowingpad, 10 min rolig.\n" + ROING_TEKNIKK),
    (2, 2, 4, "Roing", "roing", "Rowingpad, 12 min rolig.\n" + ROING_TEKNIKK),
    (3, 3, 4, "Roing", "roing", "Rowingpad, 15 min rolig.\n" + ROING_TEKNIKK),
    (4, 4, 4, "Roing", "roing", "Rowingpad, 15 min. Kjenn etter om drag-tempoet kan være litt jevnere.\n" + ROING_TEKNIKK),
    (5, 5, 4, "Roing", "roing", "Rowingpad, 17 min rolig.\n" + ROING_TEKNIKK),
    (6, 6, 4, "Roing", "roing", "Rowingpad, 18 min rolig.\n" + ROING_TEKNIKK),
    (7, 7, 4, "Roing", "roing", "Rowingpad, 20 min rolig.\n" + ROING_TEKNIKK),
    (8, 8, 4, "Roing", "roing", "Rowingpad, 20 min. Valgfritt: del opp i 2 x 10 min med kort pause.\n" + ROING_TEKNIKK),

    # Fredag - uke 1-4 er ren kondisjon (gange) uten styrke ennå, følger fasen fra uke 5
    (1, 1, 5, "Gange", "gange", "Walkingpad, 15 min i rolig tempo (ca. 3,5-4 km/t)."),
    (2, 2, 5, "Gange", "gange", "Walkingpad, 18 min i samme rolige tempo."),
    (3, 3, 5, "Gange", "gange", "Walkingpad, 20 min. Prøv gjerne 1% stigning hvis du har den funksjonen."),
    (4, 4, 5, "Gange", "gange", "Walkingpad, 20 min med 2% stigning."),
    (5, 8, 5, "Styrke", "styrke", STYRKE_OVELSER + "\nØk litt i vekt eller reps sammenlignet med forrige uke."),

    # Lørdag - ekstra hviledag i uke 1-4 (mandag dekker allerede gange), lang gåtur fra uke 5
    (1, 4, 6, "Hvile", "hvile", "Hviledag."),
    (5, 5, 6, "Gange", "gange", "Walkingpad, 30 min rolig tur."),
    (6, 6, 6, "Gange", "gange", "Walkingpad, 30 min rolig tur."),
    (7, 7, 6, "Gange", "gange", "Walkingpad, 35 min rolig tur."),
    (8, 8, 6, "Gange", "gange", "Walkingpad, 35 min rolig tur."),

    # Søndag - Hvile, følger fasen
    (1, 4, 7, "Hvile", "hvile", "Hviledag."),
    (5, 8, 7, "Hvile", "hvile", "Hviledag."),

    # Fase 3 (uke 9+) - hele uken lagt om med en tredje styrkeøkt
    (9, None, 1, "Gange", "gange", "Walkingpad, 30-40 min. Variér gjerne mellom rolig og litt raskere tempo, og bruk stigning."),
    (9, None, 2, "Styrke", "styrke", STYRKE_OVELSER + "\nFortsett å øke vekt/reps gradvis."),
    (9, None, 3, "Roing", "roing", "Rowingpad, 20-25 min. Valgfritt: prøv intervaller, f.eks. 4 x 3 min jevnt drag med 1 min rolig imellom.\n" + ROING_TEKNIKK),
    (9, None, 4, "Styrke (3. økt)", "styrke", "Tredje styrkeøkt denne uken.\n" + STYRKE_OVELSER),
    (9, None, 5, "Gange eller roing", "valgfritt", "Walkingpad eller rowingpad, 20-30 min - det du har mest lyst på."),
    (9, None, 6, "Gange", "gange", "Walkingpad, lengre tur: 35-45 min i rolig tempo - ukens lengste økt."),
    (9, None, 7, "Hvile", "hvile", "Hviledag."),
]

QUOTES = [
    "Det er ikke målet som teller mest, det er hva du blir underveis for å nå det.",
    "Du trenger ikke være motivert, du trenger bare å begynne.",
    "Sakte fremgang er fortsatt fremgang.",
    "Kroppen din klarer mer enn du tror. Det er hodet du må overbevise.",
    "I dag trenger du bare å gjøre litt bedre enn i går.",
    "Disiplin er å velge mellom det du vil nå og det du vil nå akkurat nå.",
    "Hver økt teller, selv den du ikke har lyst på.",
    "Du kommer aldri til å angre på en økt du gjennomførte.",
    "Konsistens slår intensitet - møt opp, gang på gang.",
    "Formen kommer ikke av én god økt, men av at du ikke gir opp.",
    "Det eneste dårlige treningsøkten er den du ikke gjennomførte.",
    "Fremgang liker seg best i det stille - stol på prosessen.",
    "Du bygger ikke en ny kropp på én dag, men du kan bygge én vane om gangen.",
    "Ta det rolig, men ta det.",
    "Hver gang du velger å trene, stemmer du på den du ønsker å bli.",
    "Det som føles tungt i dag, blir din nye normal om noen uker.",
    "Ikke sammenlign din dag 1 med noen andres dag 100.",
    "Kroppen forandrer seg når du gir den en god grunn til det, om og om igjen.",
    "Liten innsats gjentatt er sterkere enn stor innsats som ikke gjentas.",
    "Du trenger ikke være perfekt, du trenger bare å møte opp.",
    "Fremgang er sjelden rett frem - bli værende i prosessen.",
    "Den beste treningstiden er den du faktisk gjennomfører.",
    "Sterk kropp og sterk vilje bygges på samme måte: litt om gangen.",
    "Du har allerede gjort det vanskeligste - du har begynt.",
    "Hver dag du trener er en investering i dagene du ikke trener.",
    "Ingen forventer at du skal være rask. De forventer at du skal fortsette.",
    "Tålmodighet er en treningsøvelse i seg selv.",
    "Kroppen husker det du gjentar, ikke det du gjør én gang.",
    "Om det er tungt, er det fordi det virker.",
    "Du løper ikke et kappløp mot noen andre enn deg selv i går.",
]


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

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS faser (
            fase INTEGER PRIMARY KEY,
            uke_fra INTEGER NOT NULL,
            uke_til INTEGER,
            navn TEXT NOT NULL,
            beskrivelse TEXT NOT NULL
        )
        """
    )
    if conn.execute("SELECT COUNT(*) AS n FROM faser").fetchone()["n"] == 0:
        conn.executemany(
            "INSERT INTO faser (fase, uke_fra, uke_til, navn, beskrivelse) VALUES (:fase, :uke_fra, :uke_til, :navn, :beskrivelse)",
            FASER,
        )

    # okt_mal er ren plandata (ikke noe brukeren har lagt inn selv) - den slettes
    # og bygges på nytt fra OKT_MAL hver gang appen starter, slik at endringer i
    # selve treningsplanen alltid slår igjennom. Påvirker ikke
    # dagslogg/vektlogg/fysio_ovelser/hendelse_typer/styrke_logg.
    conn.execute("DROP TABLE IF EXISTS okt_mal")
    conn.execute(
        """
        CREATE TABLE okt_mal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uke_fra INTEGER NOT NULL,
            uke_til INTEGER,
            ukedag INTEGER NOT NULL,
            tittel TEXT NOT NULL,
            type TEXT NOT NULL,
            beskrivelse TEXT NOT NULL
        )
        """
    )
    conn.executemany(
        "INSERT INTO okt_mal (uke_fra, uke_til, ukedag, tittel, type, beskrivelse) VALUES (?, ?, ?, ?, ?, ?)",
        OKT_MAL,
    )

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
        CREATE TABLE IF NOT EXISTS hendelse_typer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            navn TEXT NOT NULL,
            aktiv INTEGER NOT NULL DEFAULT 1,
            pauser_plan INTEGER NOT NULL DEFAULT 0,
            opprettet TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    hendelse_kolonner = {row["name"] for row in conn.execute("PRAGMA table_info(hendelse_typer)")}
    if "pauser_plan" not in hendelse_kolonner:
        conn.execute("ALTER TABLE hendelse_typer ADD COLUMN pauser_plan INTEGER NOT NULL DEFAULT 0")
    if conn.execute("SELECT COUNT(*) AS n FROM hendelse_typer").fetchone()["n"] == 0:
        conn.executemany(
            "INSERT INTO hendelse_typer (navn, pauser_plan) VALUES (?, ?)",
            [("Alkohol", 0), ("Syk", 1)],
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
            hendelser TEXT NOT NULL DEFAULT '[]',
            notater TEXT NOT NULL DEFAULT '',
            oppdatert TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    dagslogg_kolonner = {row["name"] for row in conn.execute("PRAGMA table_info(dagslogg)")}
    if "hendelser" not in dagslogg_kolonner:
        conn.execute("ALTER TABLE dagslogg ADD COLUMN hendelser TEXT NOT NULL DEFAULT '[]'")

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
    conn.close()


def hent_fase(uke_nummer):
    db = get_db()
    row = db.execute(
        "SELECT * FROM faser WHERE uke_fra <= ? AND (uke_til IS NULL OR uke_til >= ?) ORDER BY fase DESC LIMIT 1",
        (uke_nummer, uke_nummer),
    ).fetchone()
    if row is not None:
        return dict(row)
    # Etter siste definerte fase: bruk den siste (fase 3, åpen)
    row = db.execute("SELECT * FROM faser ORDER BY fase DESC LIMIT 1").fetchone()
    return dict(row)


def hent_mal(uke_nummer, ukedag):
    db = get_db()
    row = db.execute(
        """
        SELECT * FROM okt_mal
        WHERE ukedag = ? AND uke_fra <= ? AND (uke_til IS NULL OR uke_til >= ?)
        ORDER BY uke_fra DESC LIMIT 1
        """,
        (ukedag, uke_nummer, uke_nummer),
    ).fetchone()
    return dict(row) if row else None


def dagens_sitat(dato_obj):
    indeks = dato_obj.toordinal() % len(QUOTES)
    return QUOTES[indeks]


def hent_aktive_fysio():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM fysio_ovelser WHERE aktiv = 1 ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def hent_aktive_hendelse_typer():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM hendelse_typer WHERE aktiv = 1 ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def tell_pausedager(db, start_dato, til_dato):
    """Antall dager mellom start_dato og til_dato (ekskl.) hvor en hendelse som
    'pauser planen' (f.eks. sykdom) ble registrert - disse teller ikke med i
    ukeberegningen, slik at planen venter på deg i stedet for å marsjere videre."""
    pause_ider = {row["id"] for row in db.execute("SELECT id FROM hendelse_typer WHERE pauser_plan = 1")}
    if not pause_ider:
        return 0
    rows = db.execute(
        "SELECT hendelser FROM dagslogg WHERE dato >= ? AND dato < ?",
        (start_dato.isoformat(), til_dato.isoformat()),
    ).fetchall()
    return sum(1 for row in rows if pause_ider.intersection(json.loads(row["hendelser"])))


def uke_og_dag(db, dato_obj, start_dato):
    dager_siden_start = (dato_obj - start_dato).days
    pausedager = tell_pausedager(db, start_dato, dato_obj)
    effektive_dager = max(0, dager_siden_start - pausedager)
    uke_nummer = max(1, effektive_dager // 7 + 1)
    ukedag = dato_obj.isoweekday()  # 1 = mandag ... 7 = søndag
    return uke_nummer, ukedag


@app.route("/api/ovelser")
def api_ovelser():
    return jsonify({
        "ovelser": {oid: {"navn": o["navn"], "instruks": o["instruks"], "fokus": o["fokus"], "svg": o["svg"]}
                    for oid, o in OVELSER.items()},
        "styrke_ider": STYRKE_ID_LISTE,
        "roing_ider": ["roing_maskin"],
    })


@app.route("/api/dag")
def api_dag():
    dato_str = request.args.get("dato") or date.today().isoformat()
    dato_obj = date.fromisoformat(dato_str)

    db = get_db()
    start_dato = date.fromisoformat(
        db.execute("SELECT start_dato FROM innstillinger WHERE id = 1").fetchone()["start_dato"]
    )

    uke_nummer, ukedag = uke_og_dag(db, dato_obj, start_dato)
    fase = hent_fase(uke_nummer)
    mal = hent_mal(uke_nummer, ukedag)

    logg_row = db.execute("SELECT * FROM dagslogg WHERE dato = ?", (dato_str,)).fetchone()
    logg = dict(logg_row) if logg_row else None
    if logg is not None:
        logg["hendelser"] = json.loads(logg["hendelser"])

    return jsonify({
        "dato": dato_str,
        "ukedag_navn": UKEDAGER[ukedag - 1],
        "uke_nummer": uke_nummer,
        "fase": fase,
        "okt": mal,
        "fysio_ovelser": hent_aktive_fysio(),
        "hendelse_typer": hent_aktive_hendelse_typer(),
        "logg": logg,
        "sitat": dagens_sitat(dato_obj),
    })


@app.route("/api/varsel")
def api_varsel():
    """Ren tekst beregnet på f.eks. iPhonens Snarveier-app, til bruk i et daglig varsel."""
    if VARSEL_NOKKEL and request.args.get("kode") != VARSEL_NOKKEL:
        return Response("Feil eller manglende kode.", status=403, mimetype="text/plain")

    # Gratis-passasjer: appen sjekkes uansett hver kveld av Snarveier-varselet,
    # så vi bruker samme kall til å plukke opp evt. ny Withings-data.
    # Skal aldri kunne ødelegge selve varselet, uansett hva som går galt her.
    try:
        withings_synk()
    except Exception:
        pass

    dato_obj = date.today()
    dato_str = dato_obj.isoformat()
    db = get_db()

    logg_row = db.execute("SELECT * FROM dagslogg WHERE dato = ?", (dato_str,)).fetchone()
    if logg_row is not None:
        return Response("Bra jobbet, du har allerede logget i dag! 💪", mimetype="text/plain")

    start_dato = date.fromisoformat(
        db.execute("SELECT start_dato FROM innstillinger WHERE id = 1").fetchone()["start_dato"]
    )
    uke_nummer, ukedag = uke_og_dag(db, dato_obj, start_dato)
    mal = hent_mal(uke_nummer, ukedag)

    if mal is None:
        tekst = "Husk å logge treningen din i dag! Åpne appen for detaljer."
    elif mal["type"] == "hvile":
        tekst = "Hviledag i dag – husk å logg den likevel, så telles den med i oversikten."
    else:
        kort_beskrivelse = mal["beskrivelse"].split("\n")[0].lstrip("- ").strip()
        tekst = f"Husk å logge treningen din i dag: {mal['tittel']} – {kort_beskrivelse}"

    return Response(tekst, mimetype="text/plain")


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


def withings_synk():
    """Henter alle nye målinger fra Withings (vekt, fettprosent, muskelmasse,
    puls osv. - se WITHINGS_MALETYPER) og lagrer dem i withings_malinger.
    Vekten (type 1) legges i tillegg inn i vektlogg, som før.
    Returnerer (antall_nye, None) eller (None, feiltekst)."""
    access_token, feil = withings_hent_gyldig_token()
    if feil:
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
        return None, str(e)

    if svar.get("status") != 0:
        return None, svar.get("error") or f"Withings-feil (status {svar.get('status')})"

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
        "UPDATE withings_konto SET siste_maling_epoch = ?, sist_synket = ? WHERE id = 1",
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


def oura_synk():
    """Henter nye dagssammendrag (søvn-, restitusjon- og aktivitet-poengsum,
    pluss skritt) fra Oura og lagrer dem i oura_malinger.
    Returnerer (antall, None) eller (None, feiltekst)."""
    access_token, feil = oura_hent_gyldig_token()
    if feil:
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
            return None, str(e)

        if svar.status_code != 200:
            return None, f"Oura-feil ({svar.status_code}) på {sti}: {svar.text[:200]}"

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
        "UPDATE oura_konto SET siste_dag_synket = ?, sist_synket = ? WHERE id = 1",
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


@app.route("/api/uke")
def api_uke():
    dato_str = request.args.get("dato") or date.today().isoformat()
    dato_obj = date.fromisoformat(dato_str)
    mandag = dato_obj - timedelta(days=dato_obj.isoweekday() - 1)

    db = get_db()
    start_dato = date.fromisoformat(
        db.execute("SELECT start_dato FROM innstillinger WHERE id = 1").fetchone()["start_dato"]
    )

    dager = []
    for i in range(7):
        d = mandag + timedelta(days=i)
        d_str = d.isoformat()
        uke_nummer, ukedag = uke_og_dag(db, d, start_dato)
        mal = hent_mal(uke_nummer, ukedag)
        logg_row = db.execute("SELECT * FROM dagslogg WHERE dato = ?", (d_str,)).fetchone()
        dager.append({
            "dato": d_str,
            "ukedag_navn": UKEDAGER[ukedag - 1],
            "er_i_dag": d_str == date.today().isoformat(),
            "okt": mal,
            "gjennomfort": bool(logg_row["gjennomfort"]) if logg_row else False,
        })

    return jsonify({"dager": dager})


@app.route("/api/dagslogg", methods=["POST"])
def api_lagre_dagslogg():
    data = request.get_json(force=True)
    dato_str = data.get("dato") or date.today().isoformat()
    gjennomfort = 1 if data.get("gjennomfort") else 0
    fysio_gjort = 1 if data.get("fysio_gjort") else 0
    hendelser = data.get("hendelser") or []
    hendelser_json = json.dumps([int(h) for h in hendelser])
    notater = (data.get("notater") or "").strip()

    db = get_db()
    db.execute(
        """
        INSERT INTO dagslogg (dato, gjennomfort, fysio_gjort, hendelser, notater)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(dato) DO UPDATE SET
            gjennomfort = excluded.gjennomfort,
            fysio_gjort = excluded.fysio_gjort,
            hendelser = excluded.hendelser,
            notater = excluded.notater,
            oppdatert = datetime('now', 'localtime')
        """,
        (dato_str, gjennomfort, fysio_gjort, hendelser_json, notater),
    )
    db.commit()
    row = db.execute("SELECT * FROM dagslogg WHERE dato = ?", (dato_str,)).fetchone()
    resultat = dict(row)
    resultat["hendelser"] = json.loads(resultat["hendelser"])
    return jsonify(resultat)


# ---- Fysioterapi-øvelser ----

@app.route("/api/fysio", methods=["GET"])
def api_list_fysio():
    db = get_db()
    rows = db.execute("SELECT * FROM fysio_ovelser ORDER BY aktiv DESC, id").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/fysio", methods=["POST"])
def api_create_fysio():
    data = request.get_json(force=True)
    navn = (data.get("navn") or "").strip()
    if not navn:
        return jsonify({"error": "Navn er påkrevd"}), 400
    beskrivelse = (data.get("beskrivelse") or "").strip()

    db = get_db()
    cur = db.execute(
        "INSERT INTO fysio_ovelser (navn, beskrivelse) VALUES (?, ?)",
        (navn, beskrivelse),
    )
    db.commit()
    row = db.execute("SELECT * FROM fysio_ovelser WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/fysio/<int:fysio_id>", methods=["PUT"])
def api_update_fysio(fysio_id):
    data = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT * FROM fysio_ovelser WHERE id = ?", (fysio_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Fant ikke øvelsen"}), 404

    navn = (data.get("navn", row["navn"]) or "").strip() or row["navn"]
    beskrivelse = data.get("beskrivelse", row["beskrivelse"])
    aktiv = 1 if data.get("aktiv", row["aktiv"]) else 0

    db.execute(
        "UPDATE fysio_ovelser SET navn = ?, beskrivelse = ?, aktiv = ? WHERE id = ?",
        (navn, beskrivelse, aktiv, fysio_id),
    )
    db.commit()
    updated = db.execute("SELECT * FROM fysio_ovelser WHERE id = ?", (fysio_id,)).fetchone()
    return jsonify(dict(updated))


@app.route("/api/fysio/<int:fysio_id>", methods=["DELETE"])
def api_delete_fysio(fysio_id):
    db = get_db()
    db.execute("DELETE FROM fysio_ovelser WHERE id = ?", (fysio_id,))
    db.commit()
    return "", 204


# ---- Hendelser (alkohol, syk, osv.) ----

@app.route("/api/hendelser", methods=["GET"])
def api_list_hendelser():
    db = get_db()
    rows = db.execute("SELECT * FROM hendelse_typer ORDER BY aktiv DESC, id").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/hendelser", methods=["POST"])
def api_create_hendelse():
    data = request.get_json(force=True)
    navn = (data.get("navn") or "").strip()
    if not navn:
        return jsonify({"error": "Navn er påkrevd"}), 400
    pauser_plan = 1 if data.get("pauser_plan") else 0

    db = get_db()
    cur = db.execute("INSERT INTO hendelse_typer (navn, pauser_plan) VALUES (?, ?)", (navn, pauser_plan))
    db.commit()
    row = db.execute("SELECT * FROM hendelse_typer WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/hendelser/<int:hendelse_id>", methods=["PUT"])
def api_update_hendelse(hendelse_id):
    data = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT * FROM hendelse_typer WHERE id = ?", (hendelse_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Fant ikke hendelsestypen"}), 404

    navn = (data.get("navn", row["navn"]) or "").strip() or row["navn"]
    aktiv = 1 if data.get("aktiv", row["aktiv"]) else 0
    pauser_plan = 1 if data.get("pauser_plan", row["pauser_plan"]) else 0

    db.execute(
        "UPDATE hendelse_typer SET navn = ?, aktiv = ?, pauser_plan = ? WHERE id = ?",
        (navn, aktiv, pauser_plan, hendelse_id),
    )
    db.commit()
    updated = db.execute("SELECT * FROM hendelse_typer WHERE id = ?", (hendelse_id,)).fetchone()
    return jsonify(dict(updated))


@app.route("/api/hendelser/<int:hendelse_id>", methods=["DELETE"])
def api_delete_hendelse(hendelse_id):
    db = get_db()
    db.execute("DELETE FROM hendelse_typer WHERE id = ?", (hendelse_id,))
    db.commit()
    return "", 204


# ---- Styrkelogg (vekt/reps brukt per øvelse) ----

@app.route("/api/styrke-logg/<ovelse_id>")
def api_hent_styrke_logg(ovelse_id):
    dato_str = request.args.get("dato") or date.today().isoformat()
    db = get_db()
    i_dag = db.execute(
        "SELECT * FROM styrke_logg WHERE dato = ? AND ovelse_id = ?", (dato_str, ovelse_id)
    ).fetchone()
    forrige = db.execute(
        "SELECT * FROM styrke_logg WHERE ovelse_id = ? AND dato < ? ORDER BY dato DESC LIMIT 1",
        (ovelse_id, dato_str),
    ).fetchone()
    return jsonify({
        "i_dag": dict(i_dag) if i_dag else None,
        "forrige": dict(forrige) if forrige else None,
    })


@app.route("/api/styrke-logg", methods=["POST"])
def api_lagre_styrke_logg():
    data = request.get_json(force=True)
    dato_str = data.get("dato") or date.today().isoformat()
    ovelse_id = (data.get("ovelse_id") or "").strip()
    if not ovelse_id:
        return jsonify({"error": "ovelse_id mangler"}), 400

    def tall_eller_none(verdi):
        if verdi is None or verdi == "":
            return None
        try:
            return float(str(verdi).replace(",", "."))
        except ValueError:
            return None

    vekt_kg = tall_eller_none(data.get("vekt_kg"))
    reps_tall = tall_eller_none(data.get("reps"))
    reps = int(reps_tall) if reps_tall is not None else None

    db = get_db()
    db.execute(
        """
        INSERT INTO styrke_logg (dato, ovelse_id, vekt_kg, reps)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(dato, ovelse_id) DO UPDATE SET
            vekt_kg = excluded.vekt_kg,
            reps = excluded.reps
        """,
        (dato_str, ovelse_id, vekt_kg, reps),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM styrke_logg WHERE dato = ? AND ovelse_id = ?", (dato_str, ovelse_id)
    ).fetchone()
    return jsonify(dict(row))


# ---- Historikk ----

@app.route("/api/historikk")
def api_historikk():
    db = get_db()
    rader = db.execute("SELECT * FROM dagslogg ORDER BY dato DESC").fetchall()
    start_dato = date.fromisoformat(
        db.execute("SELECT start_dato FROM innstillinger WHERE id = 1").fetchone()["start_dato"]
    )
    hendelse_navn = {row["id"]: row["navn"] for row in db.execute("SELECT id, navn FROM hendelse_typer")}

    dager = []
    hendelse_antall = {}
    for rad in rader:
        d = dict(rad)
        hendelse_ider = json.loads(d["hendelser"])
        d["hendelser"] = [{"id": hid, "navn": hendelse_navn.get(hid, "?")} for hid in hendelse_ider]
        for hid in hendelse_ider:
            navn = hendelse_navn.get(hid, "?")
            hendelse_antall[navn] = hendelse_antall.get(navn, 0) + 1

        dato_obj = date.fromisoformat(d["dato"])
        uke_nummer, ukedag = uke_og_dag(db, dato_obj, start_dato)
        mal = hent_mal(uke_nummer, ukedag)
        d["okt_tittel"] = mal["tittel"] if mal else None
        d["ukedag_navn"] = UKEDAGER[ukedag - 1]
        dager.append(d)

    totalt = len(rader)
    gjennomfort_antall = sum(1 for r in rader if r["gjennomfort"])

    return jsonify({
        "dager": dager,
        "stats": {
            "totalt_registrert": totalt,
            "gjennomfort_antall": gjennomfort_antall,
            "gjennomfort_prosent": round(100 * gjennomfort_antall / totalt) if totalt else 0,
            "hendelse_antall": hendelse_antall,
        },
    })


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
