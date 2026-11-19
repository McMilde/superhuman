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
                vapid_claims={"sub": VAPID_SUB}, ttl=6 * 3600)
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
