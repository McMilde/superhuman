"""Coachen: alle kall til Claude, med faste reservetekster når Claude ikke
er tilgjengelig (ingen nøkkel, tom kreditt, nettverksfeil, avslag).

Kun `sporr_claude` snakker med Anthropic. Alt annet bygger på den og faller
alltid tilbake på reserve, slik at appen aldri står tom.
"""
import os
import random
from datetime import date, datetime, timedelta

from pydantic import BaseModel

import livsstil

MODELL = "claude-opus-5-5"
TRENINGSDAG_TITTEL = "I DAG ER DET TRENINGSDAG 💪"


class CoachUtilgjengelig(Exception):
    pass


class Dagsmelding(BaseModel):
    tittel: str
    tekst: str


class Middag(BaseModel):
    navn: str
    minutter: int
    beskrivelse: str
    ingredienser: list[str]


class Ukemeny(BaseModel):
    middager: list[Middag]
    lunsj: Middag
    brodtips: list[str]
    antall_trening: int
    lunsj_steg: list[str] = []


class HelgTips(BaseModel):
    tips: list[str]


class HvisSaa(BaseModel):
    planer: list[str]


class Ukemal(BaseModel):
    forslag: list[str]


SYSTEM_PROMPT = """Du er Eivins personlige livsstilscoach i appen hans. Skriv alltid på norsk (bokmål).

Om Eivin:
- Mål: gå ned 20 kg (rolig tempo, ca. 0,5 kg i uka) og endre livsstil for godt.
- Alkohol: vil slutte å drikke på hverdager og bare kose seg med få enheter i helgene. Han sier selv at han har vanskelig for å stoppe når han først har begynt, så hjelp ham å planlegge FØR, ikke å bremse underveis.
- Faster som regel 16-18 timer. Han vet selv når fasten slutter; ikke mas om tidspunkter.
- Spiser lunsj kl. 11.30 på jobb (ofte samboerens surdeigsbrød, eller matboks han lager selv) og middag rundt 17.30. Når han ikke faster kan det bli frokost og litt kveldsmat.
- Hjemme spiser hele familien det samme; barna er 5 og 10 år. Middager må være raske (maks ca. 30 min) og barnevennlige. Han tåler alt.
- Han styrer treningen selv. Du sier bare OM det er treningsdag, aldri hva han skal trene.
- Han teller ikke kalorier. Gi heller enkle porsjonsråd (mer grønnsaker og protein, mindre pasta/ris/brød).

Tone:
- Varm, direkte og kort. Som en god venn som er coach. Maks ca. 80 ord med mindre han ber om mer.
- Aldri moraliser, skam eller kjeft – heller ikke etter en dårlig helg. Se fremover.
- Ros konkret når noe går bra (f.eks. alkoholfrie dager på rad).
- Du gir ikke medisinske råd. Sjelden, og bare når det passer naturlig (f.eks. hvis han sier at det er tungt med alkoholen), kan du rolig nevne at fastlegen kan hjelpe, eller RUSinfo på 915 08588 (anonymt og gratis). Ikke i vanlige meldinger.
"""


def sporr_claude(system: str, melding: str, utdata, effort: str, historikk=None, tidsavbrudd: int = 40):
    """Eneste funksjon som kaller Anthropic. Returnerer en utfylt pydantic-modell
    (når `utdata` er gitt) eller tekst. Kaster CoachUtilgjengelig ved alt som
    ikke gir et brukbart svar."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise CoachUtilgjengelig("ingen nøkkel")
    try:
        import anthropic

        # Kort tidsavbrudd og ett nytt forsøk, så reserveteksten kommer raskt
        # hvis Claude er treg. Ukemenyen lages i bakgrunnen og får mer tid.
        client = anthropic.Anthropic(timeout=tidsavbrudd, max_retries=1)
        meldinger = list(historikk or []) + [{"role": "user", "content": melding}]
        felles = dict(
            model=MODELL,
            max_tokens=16000,
            system=system,
            messages=meldinger,
            output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if utdata is not None:
            svar = client.beta.messages.parse(output_format=utdata, **felles)
        else:
            svar = client.beta.messages.create(**felles)
    except CoachUtilgjengelig:
        raise
    except Exception as feil:  # nettverk, kreditt, rate limit, osv.
        raise CoachUtilgjengelig(str(feil)) from feil

    if svar.stop_reason == "refusal":
        raise CoachUtilgjengelig("avslag")
    if utdata is not None:
        if getattr(svar, "parsed_output", None) is None:
            raise CoachUtilgjengelig("ingen strukturert svar")
        return svar.parsed_output
    tekst = "".join(b.text for b in svar.content if getattr(b, "type", None) == "text").strip()
    if not tekst:
        raise CoachUtilgjengelig("tomt svar")
    return tekst


# ---- Sammendrag av dataene (det eneste som sendes til Claude) ----

def _oura_siste(conn, type_, dager, i_dag):
    fra = (i_dag - timedelta(days=dager)).isoformat()
    return conn.execute(
        "SELECT dato, verdi FROM oura_malinger WHERE type = ? AND dato >= ? ORDER BY dato", (type_, fra)
    ).fetchall()


def lag_sammendrag(conn, i_dag: date) -> str:
    linjer = [f"I dag: {i_dag.isoformat()} ({['mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag', 'søndag'][i_dag.isoweekday() - 1]})."]

    vekter = conn.execute("SELECT dato, vekt_kg FROM vektlogg ORDER BY dato").fetchall()
    mal = conn.execute("SELECT mal_vekt_kg FROM innstillinger WHERE id = 1").fetchone()["mal_vekt_kg"]
    if vekter:
        siste = vekter[-1]
        linjer.append(f"Siste vekt: {siste['vekt_kg']:.1f} kg ({siste['dato']}). Startvekt i appen: {vekter[0]['vekt_kg']:.1f} kg ({vekter[0]['dato']}).")
        mnd = [v for v in vekter if v["dato"] >= (i_dag - timedelta(days=30)).isoformat()]
        if len(mnd) >= 2:
            linjer.append(f"Endring siste 30 dager: {mnd[-1]['vekt_kg'] - mnd[0]['vekt_kg']:+.1f} kg.")
    if mal:
        linjer.append(f"Målvekt: {mal:g} kg.")

    linjer.append(f"Alkoholfrie hverdager på rad: {livsstil.alkoholfrie_hverdager_pa_rad(conn, i_dag)} "
                  f"(beste noensinne: {livsstil.beste_alkoholfrie_rekke(conn, i_dag)}).")
    ukemal = livsstil.hent_ukemal(conn, livsstil.mandag_for(i_dag))
    if ukemal:
        linjer.append(f"Ukemål denne uka (valgt av ham selv – følg det opp): {ukemal}.")
    effekt = livsstil.alkohol_effekt(conn, i_dag)
    if effekt["nok_data"]:
        linjer.append(
            f"Hans egne Oura-tall: restitusjon dagen etter alkohol {effekt['restitusjon_med']} mot "
            f"{effekt['restitusjon_uten']} ellers; søvn {effekt['sovn_med']} mot {effekt['sovn_uten']}."
        )
    spart = livsstil.alkohol_spart(conn)
    if spart and spart["enheter_spart"] > 0:
        linjer.append(f"Spart siden {spart['fra_dato']}: {spart['enheter_spart']:g} enheter, ca. {spart['kr']} kr og {spart['kalorier']} kalorier.")

    linjer.append("Avkrysning siste 14 dager (dato: fastet/alkohol(enheter)/trent/syk):")
    for i in range(14, 0, -1):
        d = (i_dag - timedelta(days=i)).isoformat()
        s = livsstil.dagsstatus(conn, d)
        if s is None:
            linjer.append(f"- {d}: ikke registrert")
            continue
        alk = f"ja ({s['alkohol_enheter']:g})" if s["alkohol"] and s["alkohol_enheter"] else ("ja" if s["alkohol"] else "nei")
        linjer.append(
            f"- {d}: fastet {'ja' if s['fastet'] else 'nei'}, alkohol {alk}, "
            f"trent {'ja' if s['trent'] else 'nei'}, syk {'ja' if s['syk'] else 'nei'}"
        )

    for type_, navn in (("sovn_score", "Søvn"), ("restitusjon_score", "Restitusjon")):
        rader = _oura_siste(conn, type_, 7, i_dag)
        if rader:
            linjer.append(f"Oura {navn} siste 7 dager: " + ", ".join(f"{r['verdi']:.0f}" for r in rader) + ".")

    plan = livsstil.hent_ukeplan(conn, livsstil.mandag_for(i_dag))
    if plan:
        linjer.append(f"Treningsdager denne uka: {', '.join(plan['treningsdager']) or 'ingen'}.")
        linjer.append("Middager denne uka: " + ", ".join(f"{m['dag']} {m['navn']}" for m in plan["middager"]) + ".")
    return "\n".join(linjer)


# ---- Dagens melding ----

RESERVE_DAG = [
    "Ny dag, nye muligheter. Ett godt valg om gangen er nok.",
    "Du trenger ikke være perfekt, bare litt bedre enn i går.",
    "Drikk et stort glass vann nå, og kjenn at du tar vare på deg selv.",
    "Små vaner slår store planer. Hold rytmen i dag.",
    "Lag deg en god lunsj og vær stolt av den.",
    "Husk hvorfor du startet. Du gjør det for deg og familien.",
    "Rolig og jevnt vinner. Fortsett som du gjør.",
    "Gå en ekstra runde i dag hvis du får sjansen.",
    "Middag med familien uten alkohol er en seier i seg selv.",
    "Det er helt greit å ha en tung dag. Bare ikke gi opp.",
    "Fyll halve tallerkenen med grønnsaker i dag.",
    "Fokuser på søvnen i kveld – den hjelper på alt annet.",
    "Hver alkoholfri hverdag er en investering i deg selv.",
    "Du er i gang med noe bra. Ta i dag også.",
]


def lag_dagsmelding(conn, i_dag: date, treningsdag: bool, flytt_grunn, middag, kun_reserve=False) -> dict:
    over = livsstil.helg_over_plan(conn, i_dag)
    try:
        if kun_reserve:
            raise CoachUtilgjengelig("før morgenmeldingen")
        oppgave = (
            "Skriv dagens morgenmelding til Eivin. Tittel: maks 6 ord. Tekst: 2-4 korte setninger. "
            + (f"Det er mandag, og helgen ble mer enn planlagt ({over[1]:g} enheter mot planlagt {over[0]}). "
               "Skriv en varm nullstilling helt uten skam, og gi én konkret plan for uka. " if over else "")
            + 
            f"Treningsdag i dag: {'ja' if treningsdag else 'nei'}. "
            + (f"Treningen er flyttet fordi: {flytt_grunn} " if flytt_grunn else "")
            + (f"Middag i dag: {middag['navn']}. " if middag else "")
            + "Nevn gjerne noe konkret fra dataene hans.\n\n" + lag_sammendrag(conn, i_dag)
        )
        svar = sporr_claude(SYSTEM_PROMPT, oppgave, Dagsmelding, "low")
        tittel, tekst, kilde = svar.tittel, svar.tekst, "claude"
    except CoachUtilgjengelig:
        tittel = "God morgen!"
        deler = [RESERVE_DAG[i_dag.toordinal() % len(RESERVE_DAG)]]
        if flytt_grunn:
            deler.insert(0, flytt_grunn)
        if over:
            deler.insert(0, f"Ny uke, blanke ark. Helgen ble litt mer enn planlagt ({over[1]:g} mot {over[0]}) – det skjer. "
                            "Denne uka: alkoholfrie hverdager, én kveld om gangen.")
        rekke = livsstil.alkoholfrie_hverdager_pa_rad(conn, i_dag)
        if rekke >= 2:
            deler.append(f"Du har {rekke} alkoholfrie hverdager på rad – sterkt!")
        if middag:
            deler.append(f"Middag i dag: {middag['navn']}.")
        tekst, kilde = " ".join(deler), "reserve"
    if treningsdag:
        tittel = TRENINGSDAG_TITTEL
    return {"tittel": tittel, "tekst": tekst, "kilde": kilde}


# ---- Ukeplan og middager ----

def _smak_tekst(conn) -> str:
    v = livsstil.hent_vurderinger(conn)
    deler = []
    if v["favoritter"]:
        deler.append("Familiens favoritter (bruk gjerne én av dem, eller noe i samme stil): " + ", ".join(v["favoritter"]) + ".")
    if v["unnga"]:
        deler.append("Familien liker IKKE disse – ikke foreslå dem eller noe veldig likt: " + ", ".join(v["unnga"]) + ".")
    return " ".join(deler)


def _be_om_meny(conn, uke_start: date, forslag: int):
    oppgave = (
        f"Lag ukeplan for uka som starter {uke_start.isoformat()}: nøyaktig 5 middager (mandag-fredag), "
        "raske (maks 30 min), sunne og barnevennlige, med enkel ingrediensliste (norske navn, med mengde). "
        "Varier fisk, kylling og kjøtt. Lag én lunsj som lages søndag og holder i 4-5 dager i matboks, og 4 tips "
        "til mettende pålegg på surdeigsbrød. Gi også 4-6 korte, nummererbare steg (lunsj_steg) for å lage "
        "lunsjboksene på søndag på under 45 minutter. Velg antall treningsdager (2-5); "
        f"forslaget basert på forrige uke er {forslag}. " + _smak_tekst(conn) + "\n\n" + lag_sammendrag(conn, uke_start)
    )
    meny = sporr_claude(SYSTEM_PROMPT, oppgave, Ukemeny, "medium", tidsavbrudd=150)
    if len(meny.middager) < 5:
        raise CoachUtilgjengelig("for få middager")
    lunsj = {**meny.lunsj.model_dump(), "brodtips": meny.brodtips}
    if len(meny.lunsj_steg) >= 3:
        lunsj["steg"] = meny.lunsj_steg[:8]
    return meny, [m.model_dump() for m in meny.middager[:5]], lunsj


def lag_ukeplan_med_claude(conn, uke_start: date) -> dict:
    """Brukes av planleggeren (bakgrunnstråd). Faller tilbake på reserveplan."""
    forslag = livsstil.neste_antall_trening(conn, uke_start)
    try:
        meny, middager, lunsj = _be_om_meny(conn, uke_start, forslag)
    except CoachUtilgjengelig:
        return livsstil.lag_reserveplan(conn, uke_start)
    antall = max(forslag - 1, min(forslag + 1, meny.antall_trening))
    antall = max(2, min(5, antall))
    return livsstil.lagre_ukeplan(
        conn, uke_start, livsstil.velg_treningsdager(uke_start, antall),
        middager, lunsj, "claude", antall_trening=antall,
    )


def oppgrader_ukeplan(conn, uke_start: date):
    """Bytter ut menyen i en reserveplan med en fra Claude, men beholder
    treningsdagene (de kan allerede være vist til Eivin). None ved feil."""
    plan = livsstil.hent_ukeplan(conn, uke_start)
    if plan is None or plan["kilde"] != "reserve":
        return plan
    try:
        _, middager, lunsj = _be_om_meny(conn, uke_start, plan["antall_trening"])
    except CoachUtilgjengelig:
        return None
    return livsstil.lagre_ukeplan(conn, uke_start, plan["treningsdager"], middager, lunsj, "claude",
                                  antall_trening=plan["antall_trening"])


def bytt_middag(conn, uke_start: date, dag: str) -> dict:
    plan = livsstil.hent_eller_lag_ukeplan(conn, uke_start)
    if livsstil.middag_for_dag(plan, dag) is None:
        raise ValueError("Ugyldig dag")
    brukte = {m["navn"] for m in plan["middager"]}
    try:
        ny = sporr_claude(
            SYSTEM_PROMPT,
            "Foreslå én ny rask, sunn og barnevennlig middag (maks 30 min) med ingrediensliste. "
            f"Den må være forskjellig fra: {', '.join(sorted(brukte))}. " + _smak_tekst(conn),
            Middag, "low",
        ).model_dump()
    except CoachUtilgjengelig:
        ledige = [m for m in livsstil.tilgjengelige_reservemiddager(conn) if m["navn"] not in brukte]
        ny = dict(ledige[0] if ledige else livsstil.RESERVE_MIDDAGER[0])
    middager = [({**ny, "dag": dag} if m["dag"] == dag else m) for m in plan["middager"]]
    return livsstil.lagre_ukeplan(conn, uke_start, plan["treningsdager"], middager, plan["lunsj"],
                                  plan["kilde"], antall_trening=plan["antall_trening"])


# ---- Chat, vanskelige øyeblikk og helg ----

def svar_chat(conn, tekst: str) -> str:
    tidligere = conn.execute("SELECT rolle, tekst FROM chat ORDER BY id DESC LIMIT 20").fetchall()
    historikk = [{"role": r["rolle"], "content": r["tekst"]} for r in reversed(tidligere)]
    conn.execute("INSERT INTO chat (rolle, tekst) VALUES ('user', ?)", (tekst,))
    conn.commit()
    try:
        system = SYSTEM_PROMPT + "\n\nDataene hans akkurat nå:\n" + lag_sammendrag(conn, livsstil.i_dag_oslo())
        svar = sporr_claude(system, tekst, None, "low", historikk=historikk)
    except CoachUtilgjengelig:
        return "Coachen er ikke tilgjengelig akkurat nå. Prøv igjen litt senere."
    conn.execute("INSERT INTO chat (rolle, tekst) VALUES ('assistant', ?)", (svar,))
    conn.commit()
    return svar


RESERVE_VANSKELIG = [
    "Hell opp et stort glass kullsyrevann med sitron eller en alkoholfri øl. Drikk det sakte før du bestemmer deg for noe annet.",
    "Ta på deg skoene og gå en tur rundt kvartalet i 10 minutter. Suget går som regel over på 15-20 minutter.",
    "Ta en varm dusj. Det endrer stemningen i kroppen raskere enn du tror.",
    "Ring eller send melding til noen du liker. Prat om noe helt annet.",
    "Spis noe salt og mettende – en håndfull nøtter eller et kokt egg. Sult forveksles ofte med sug.",
    "Sett på en episode av en serie du liker, med en kopp te.",
    "Skriv ned hvorfor du vil ha en alkoholfri kveld i kveld. Les det høyt.",
    "Gjør noe med hendene: rydd en skuff, lag mat til i morgen, fiks noe småtteri.",
    "Pust rolig: inn i 4 sekunder, hold i 4, ut i 6. Gjenta ti ganger.",
    "Lek med barna eller gjør noe sammen med samboeren. Vær til stede i 20 minutter.",
]


def vanskelig_na(conn) -> str:
    try:
        return sporr_claude(
            SYSTEM_PROMPT,
            "Eivin trykket på «Det er vanskelig nå» – han har lyst på alkohol eller er i ferd med å miste kontrollen. "
            "Gi ÉN konkret ting han kan gjøre akkurat nå, maks 60 ord, varmt og uten preken.\n\n"
            + lag_sammendrag(conn, livsstil.i_dag_oslo()),
            None, "low",
        )
    except CoachUtilgjengelig:
        return random.choice(RESERVE_VANSKELIG)


RESERVE_HELG_TIPS = [
    "Kjøp bare inn akkurat det antallet du har bestemt – ingenting ekstra i skapet.",
    "Drikk et glass vann mellom hver enhet.",
    "Spis et skikkelig måltid før du begynner – det er lettere å stoppe når du er mett.",
]


RESERVE_HVIS_SAA = [
    "Hvis jeg får lyst på mer enn planen, så tar jeg en alkoholfri øl eller kullsyrevann først og venter 20 minutter.",
    "Hvis noen byr meg på en til, så sier jeg «nei takk, jeg kjører i morgen tidlig».",
    "Hvis klokka er blitt sluttidspunktet, så pusser jeg tennene – da er kvelden over.",
]


def hvis_saa_forslag(conn, planlagte_enheter: int) -> list:
    """Tre konkrete «hvis–så»-planer for helgen. Brukes også uten tilkobling."""
    try:
        svar = sporr_claude(
            SYSTEM_PROMPT,
            f"Eivin har planlagt maks {planlagte_enheter} enheter i helgen. Foreslå nøyaktig 3 korte «hvis–så»-planer "
            "(én setning hver, start med «Hvis ...») for situasjonene der det typisk glipper: når suget kommer etter "
            "de første enhetene, når noen byr på mer, og når kvelden drar ut. Konkret og vennlig."
            + ("\n\n" + lag_sammendrag(conn, livsstil.i_dag_oslo()) if conn is not None else ""),
            HvisSaa, "low",
        )
        if len(svar.planer) < 3:
            raise CoachUtilgjengelig("for få planer")
        return svar.planer[:3]
    except CoachUtilgjengelig:
        return list(RESERVE_HVIS_SAA)


def helg_tips(conn, planlagte_enheter: int) -> list:
    try:
        svar = sporr_claude(
            SYSTEM_PROMPT,
            f"Eivin har bestemt maks {planlagte_enheter} enheter alkohol denne helgen (fredag-søndag), og har allerede satt et sluttidspunkt. "
            "Gi 2-3 korte, konkrete tips som hjelper ham å holde planen, gitt at han har vanskelig for å stoppe når han først begynner.",
            HelgTips, "low",
        )
        if not svar.tips:
            raise CoachUtilgjengelig("ingen tips")
        return svar.tips[:3]
    except CoachUtilgjengelig:
        return list(RESERVE_HELG_TIPS)


def helg_oppsummering(conn, uke_start: date) -> str:
    rad = conn.execute("SELECT planlagte_enheter FROM helgeplan WHERE uke_start = ?", (uke_start.isoformat(),)).fetchone()
    planlagt = rad["planlagte_enheter"] if rad else None
    datoer = [(uke_start + timedelta(days=i)).isoformat() for i in (4, 5, 6)]
    faktisk = conn.execute(
        "SELECT COALESCE(SUM(alkohol_enheter), 0) FROM dagssjekk WHERE alkohol = 1 AND dato IN (?, ?, ?)", datoer
    ).fetchone()[0]
    try:
        return sporr_claude(
            SYSTEM_PROMPT,
            f"Oppsummer helgen nøytralt og fremoverlent i 2-3 setninger. Planlagt: {planlagt if planlagt is not None else 'ingen plan'} enheter. "
            f"Registrert: {faktisk:g} enheter.",
            None, "low",
        )
    except CoachUtilgjengelig:
        if planlagt is None:
            return f"Du registrerte {faktisk:g} enheter i helgen. Neste fredag kan du prøve å bestemme antallet på forhånd."
        if faktisk <= planlagt:
            return f"Du planla {planlagt} enheter og endte på {faktisk:g}. Du holdt planen – godt jobbet!"
        return (f"Du planla {planlagt} enheter og endte på {faktisk:g}. Det skjer. "
                "Neste helg: kjøp bare inn det du har bestemt, så blir det lettere.")


# ---- Felles for API og planlegger ----

def hent_restitusjon(conn, dato: str):
    rad = conn.execute(
        "SELECT verdi FROM oura_malinger WHERE type = 'restitusjon_score' AND dato = ?", (dato,)
    ).fetchone()
    return rad["verdi"] if rad else None


def hent_eller_lag_dagsmelding(conn, i_dag: date, naa=None) -> dict:
    """Dagens melding lages én gang per dag og lagres, slik at åpning av appen
    og morgenvarselet viser det samme (og Claude bare spørres én gang).

    Åpnes appen før morgentidspunktet og Oura ikke har levert dagens
    restitusjon ennå, lagres ingenting: da får morgenjobben (som synker Oura
    først) avgjøre om treningen skal flyttes."""
    import varsler

    rad = conn.execute("SELECT * FROM dagsmelding WHERE dato = ?", (i_dag.isoformat(),)).fetchone()
    if rad:
        return dict(rad)
    naa = naa or datetime.now(livsstil.OSLO)
    plan = livsstil.hent_eller_lag_ukeplan(conn, livsstil.mandag_for(i_dag))
    middag = livsstil.middag_for_dag(plan, i_dag.isoformat())
    restitusjon = hent_restitusjon(conn, i_dag.isoformat())

    t, m = (int(x) for x in varsler.hent_tider(conn)["morgen"].split(":"))
    for_morgen = naa.date() == i_dag and (naa.hour, naa.minute) < (t, m)
    if restitusjon is None and for_morgen:
        treningsdag = i_dag.isoformat() in plan["treningsdager"]
        melding = lag_dagsmelding(conn, i_dag, treningsdag, None, middag, kun_reserve=True)
        return {"dato": i_dag.isoformat(), "tittel": melding["tittel"], "tekst": melding["tekst"],
                "treningsdag": int(treningsdag), "flyttet_fra": None, "kilde": melding["kilde"]}

    treningsdag, grunn = livsstil.er_treningsdag_i_dag(conn, i_dag, restitusjon)
    melding = lag_dagsmelding(conn, i_dag, treningsdag, grunn, middag)
    conn.execute(
        "INSERT OR REPLACE INTO dagsmelding (dato, tittel, tekst, treningsdag, flyttet_fra, kilde) VALUES (?, ?, ?, ?, ?, ?)",
        (i_dag.isoformat(), melding["tittel"], melding["tekst"], int(treningsdag), grunn, melding["kilde"]),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM dagsmelding WHERE dato = ?", (i_dag.isoformat(),)).fetchone())



def ukemal_forslag(conn, uke_start: date) -> list:
    """Tre konkrete, målbare ukemål for uka som starter uke_start, ut fra uka før."""
    reserve = livsstil.reserve_ukemal_forslag(conn, uke_start)
    st = livsstil.ukestatistikk(conn, uke_start - timedelta(days=7))
    try:
        svar = sporr_claude(
            SYSTEM_PROMPT,
            "Foreslå nøyaktig 3 ukemål for neste uke. Hvert mål: én kort setning, konkret og målbart, "
            "og realistisk for én uke. Det første målet bør ta tak i det som glapp mest forrige uke. "
            f"Forrige uke: {st}.\n\n" + lag_sammendrag(conn, uke_start - timedelta(days=1)),
            Ukemal, "low",
        )
        if len(svar.forslag) < 3:
            raise CoachUtilgjengelig("for få forslag")
        return [f.strip() for f in svar.forslag[:3]]
    except CoachUtilgjengelig:
        return reserve



def _ord(tekst: str) -> set:
    import re
    return {o for o in re.findall(r"[a-zæøå]+", tekst.lower()) if len(o) > 2}


def middag_fra_kjoleskap(conn, tekst: str) -> dict:
    """Én middag ut fra det han har i kjøleskapet. Reserve: den reservemiddagen
    som deler flest ord med det han skrev."""
    try:
        m = sporr_claude(
            SYSTEM_PROMPT,
            f"Eivin har dette hjemme: «{tekst[:500]}». Foreslå én rask, sunn og barnevennlig middag (maks 30 min) "
            "som bruker mest mulig av dette. Ingrediensene skal være det han trenger – marker gjerne det han "
            "eventuelt må kjøpe med «(kjøp)». " + _smak_tekst(conn),
            Middag, "low",
        )
        return {**m.model_dump(), "kilde": "claude"}
    except CoachUtilgjengelig:
        har = _ord(tekst)
        kandidater = livsstil.tilgjengelige_reservemiddager(conn)
        beste = max(kandidater, key=lambda m: len(har & _ord(m["navn"] + " " + " ".join(m["ingredienser"]))))
        return {**beste, "kilde": "reserve"}
