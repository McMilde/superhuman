"""Push-varsler til iPhonen (web push) og planleggeren som sender dem.

Tar en åpen sqlite3-tilkobling og importerer aldri app.py.
"""
import base64
import json

VAPID_SUB = "https://trening.flibber.no"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def hent_eller_lag_vapid(conn) -> tuple:
    """(privat nøkkel som PEM, offentlig nøkkel som base64url). Lages én gang
    og lagres i databasen, så Eivin slipper å sette den opp selv."""
    rad = conn.execute("SELECT vapid_privat, vapid_offentlig FROM innstillinger WHERE id = 1").fetchone()
    if rad and rad["vapid_privat"] and rad["vapid_offentlig"]:
        return rad["vapid_privat"], rad["vapid_offentlig"]

    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from py_vapid import Vapid01

    v = Vapid01()
    v.generate_keys()
    privat = v.private_pem().decode()
    offentlig = _b64url(v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))
    conn.execute("UPDATE innstillinger SET vapid_privat = ?, vapid_offentlig = ? WHERE id = 1", (privat, offentlig))
    conn.commit()
    return privat, offentlig


def lagre_abonnement(conn, sub: dict) -> None:
    try:
        endpoint = sub["endpoint"]
        p256dh = sub["keys"]["p256dh"]
        auth = sub["keys"]["auth"]
    except (KeyError, TypeError):
        raise ValueError("Ugyldig abonnement")
    if not (isinstance(endpoint, str) and endpoint.startswith("https://") and p256dh and auth):
        raise ValueError("Ugyldig abonnement")
    conn.execute(
        """
        INSERT INTO push_abonnement (endpoint, p256dh, auth) VALUES (?, ?, ?)
        ON CONFLICT(endpoint) DO UPDATE SET p256dh = excluded.p256dh, auth = excluded.auth
        """,
        (endpoint, p256dh, auth),
    )
    conn.commit()


def _webpush_sender(conn):
    from py_vapid import Vapid01
    from pywebpush import webpush

    privat, _ = hent_eller_lag_vapid(conn)
    vapid = Vapid01.from_pem(privat.encode())

    def send(sub_info, data):
        webpush(subscription_info=sub_info, data=data, vapid_private_key=vapid,
                vapid_claims={"sub": VAPID_SUB}, ttl=6 * 3600, timeout=15)
    return send


def send_til_alle(conn, tittel: str, tekst: str, url: str = "/", sender=None) -> int:
    sender = sender or _webpush_sender(conn)
    data = json.dumps({"tittel": tittel, "tekst": tekst, "url": url}, ensure_ascii=False)
    levert = 0
    for rad in conn.execute("SELECT endpoint, p256dh, auth FROM push_abonnement").fetchall():
        sub_info = {"endpoint": rad["endpoint"], "keys": {"p256dh": rad["p256dh"], "auth": rad["auth"]}}
        try:
            sender(sub_info, data)
            levert += 1
        except Exception as feil:
            status = getattr(getattr(feil, "response", None), "status_code", None)
            if status in (404, 410):
                conn.execute("DELETE FROM push_abonnement WHERE endpoint = ?", (rad["endpoint"],))
                conn.commit()
            else:
                print(f"Push feilet ({status}): {feil}")
    return levert


# ---- Planlagte varsler ----

STANDARD_TIDER = {"morgen": "07:00", "middag": "15:30", "helg": "15:00", "kveld": "21:00", "sondag": "18:00"}
VINDU_MINUTTER = 90


def _gyldig_tid(verdi) -> bool:
    try:
        t, m = str(verdi).split(":")
        return len(t) == 2 and len(m) == 2 and 0 <= int(t) <= 23 and 0 <= int(m) <= 59
    except ValueError:
        return False


def hent_tider(conn) -> dict:
    rad = conn.execute("SELECT varsel_tider FROM innstillinger WHERE id = 1").fetchone()
    lagret = json.loads(rad["varsel_tider"]) if rad and rad["varsel_tider"] else {}
    return {k: lagret.get(k, v) for k, v in STANDARD_TIDER.items()}


def lagre_tider(conn, tider: dict) -> dict:
    nye = hent_tider(conn)
    for k, v in (tider or {}).items():
        if k not in STANDARD_TIDER:
            continue
        if not _gyldig_tid(v):
            raise ValueError(f"Ugyldig tid for {k}")
        nye[k] = v
    conn.execute("UPDATE innstillinger SET varsel_tider = ? WHERE id = 1", (json.dumps(nye),))
    conn.commit()
    return nye


def _forste_setning(tekst: str) -> str:
    for skille in (". ", "! ", "? "):
        if skille in tekst:
            return tekst.split(skille)[0] + skille.strip()
    return tekst


def _jobb_morgen(conn, i_dag, synk, sender):
    import coach
    if synk:
        try:
            synk()
        except Exception as feil:
            print(f"Synk før morgenmelding feilet: {feil}")
    melding = coach.hent_eller_lag_dagsmelding(conn, i_dag)
    send_til_alle(conn, melding["tittel"], _forste_setning(melding["tekst"]), "/", sender=sender)
    return True


def _jobb_middag(conn, i_dag, synk, sender):
    import coach
    import livsstil
    plan = livsstil.hent_eller_lag_ukeplan(conn, livsstil.mandag_for(i_dag), lag_plan=coach.lag_ukeplan_med_claude)
    middag = livsstil.middag_for_dag(plan, i_dag.isoformat())
    if middag:
        send_til_alle(conn, "Middag i dag", f"{middag['navn']} ({middag['minutter']} min)", "/#mat", sender=sender)
        return True
    return False


def _jobb_helg(conn, i_dag, synk, sender):
    send_til_alle(conn, "Helgeplan",
                  "Hvor mange enheter skal du ha i helgen? Bestem det nå, mens du er edru.", "/#helg", sender=sender)
    return True


def _jobb_kveld(conn, i_dag, synk, sender):
    import livsstil
    if livsstil.hent_dagssjekk(conn, i_dag.isoformat()) is None:
        send_til_alle(conn, "Kryss av dagen", "Fastet, alkohol, trent, syk – tar 5 sekunder.", "/", sender=sender)
        return True
    return False


def _jobb_sondag(conn, i_dag, synk, sender):
    from datetime import timedelta

    import coach
    import livsstil
    denne_uka = livsstil.mandag_for(i_dag)
    oppsummering = coach.helg_oppsummering(conn, denne_uka)
    conn.execute(
        """
        INSERT INTO helgeplan (uke_start, oppsummering) VALUES (?, ?)
        ON CONFLICT(uke_start) DO UPDATE SET oppsummering = excluded.oppsummering
        """,
        (denne_uka.isoformat(), oppsummering),
    )
    conn.commit()
    livsstil.hent_eller_lag_ukeplan(conn, denne_uka + timedelta(days=7), lag_plan=coach.lag_ukeplan_med_claude)
    send_til_alle(conn, "Ny uke klar", "Ukemeny, handleliste og treningsdager er klare.", "/#mat", sender=sender)
    return True


JOBBER = {
    "morgen": (lambda d: True, _jobb_morgen),
    "middag": (lambda d: d.isoweekday() <= 5, _jobb_middag),
    "helg": (lambda d: d.isoweekday() == 5, _jobb_helg),
    "kveld": (lambda d: True, _jobb_kveld),
    "sondag": (lambda d: d.isoweekday() == 7, _jobb_sondag),
}


def kjor_planlagte_jobber(conn, naa, synk=None, sender=None) -> list:
    """Kjører jobber som er forfalt (innenfor 90 min etter tidspunktet) og ikke
    allerede kjørt i dag. Markerer FØR kjøring, så en jobb aldri dobbeltsendes.
    Returnerer jobbene som faktisk sendte noe."""
    i_dag = naa.date()
    minutter_na = naa.hour * 60 + naa.minute
    fyrt = []
    for type_, tid in hent_tider(conn).items():
        dag_ok, jobb = JOBBER[type_]
        t, m = (int(x) for x in tid.split(":"))
        start = t * 60 + m
        if not dag_ok(i_dag) or not (start <= minutter_na < start + VINDU_MINUTTER):
            continue
        cur = conn.execute("INSERT OR IGNORE INTO varsel_logg (dato, type) VALUES (?, ?)", (i_dag.isoformat(), type_))
        conn.commit()
        if cur.rowcount == 0:
            continue
        try:
            if jobb(conn, i_dag, synk, sender):
                fyrt.append(type_)
        except Exception as feil:
            print(f"Planlagt jobb '{type_}' feilet: {feil}")
    return fyrt


def start_planlegger(db_path, synk=None):
    import sqlite3
    import threading
    import time
    from datetime import datetime

    from livsstil import OSLO

    def loop():
        while True:
            try:
                conn = sqlite3.connect(db_path, timeout=30)
                conn.row_factory = sqlite3.Row
                try:
                    kjor_planlagte_jobber(conn, datetime.now(OSLO), synk)
                finally:
                    conn.close()
            except Exception as feil:
                print(f"Planleggeren feilet: {feil}")
            time.sleep(60)

    trad = threading.Thread(target=loop, name="planlegger", daemon=True)
    trad.start()
    return trad
