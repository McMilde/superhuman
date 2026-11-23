"""Minikurs: 30 korte leksjoner (under 2 minutter), én ny per dag.

Innholdet er skrevet på forhånd (ikke av Claude underveis), slik at det er
gjennomtenkt, gratis å vise og likt hver gang. Hver leksjon slutter med én
konkret ting å prøve samme dag.
"""
from datetime import date


def _l(tittel, tekst, prov):
    return {"tittel": tittel, "tekst": tekst, "prov": prov}


_INNHOLD = [
    _l("Små vaner slår viljestyrke",
       ["Viljestyrke er som et batteri: det er fullt om morgenen og nesten tomt klokka 21. Derfor ryker gode forsetter oftest om kvelden.",
        "Vaner trenger ikke batteri. Når noe blir automatisk – som å pusse tenner – koster det nesten ingenting. Målet de neste 30 dagene er derfor ikke å bli sterkere, men å gjøre de gode valgene enklere og de dårlige litt tyngre."],
       "Finn ett lite valg du tar hver kveld (f.eks. hva du drikker til middag) og bestem det nå – lenge før kvelden kommer."),
    _l("Suget er en bølge",
       ["Lyst på alkohol eller søtt kommer som en bølge: den bygger seg opp, topper seg og ebber ut. For de fleste er toppen over etter 15–20 minutter.",
        "Det som holder suget i live, er å diskutere med det («bare én?»). Det som får det til å gå over, er å legge merke til det uten å gjøre noe: «Nå kjenner jeg suget. Det er sterkt nå. Det går over.»"],
       "Neste gang suget kommer: se på klokka, og vent 20 minutter før du bestemmer deg."),
    _l("Alkohol og søvn",
       ["Alkohol gjør at man sovner fortere, men søvnen blir dårligere. Kroppen bruker natta på å bryte ned alkoholen: pulsen går opp, pulsvariasjonen (HRV) går ned og drømmesøvnen blir kortere.",
        "Det er derfor Oura ofte viser lav restitusjon dagen etter – selv etter bare et par glass. Du ser dine egne tall i kortet «Alkohol og kroppen din»."],
       "Se på restitusjonen din i morgen tidlig, og legg merke til hva du gjorde i kveld."),
    _l("Sult eller lyst?",
       ["Ekte sult kommer gradvis, sitter i magen og blir fornøyd av vanlig mat. Lyst kommer plutselig, sitter i hodet og vil ha noe bestemt – gjerne søtt, salt eller en øl.",
        "Et enkelt triks før du åpner kjøleskapet: spør deg selv om du er sulten, sint/stresset, ensom eller sliten. Tre av de fire løses ikke med mat eller alkohol."],
       "Før neste mellommåltid: still deg de fire spørsmålene, og se hva svaret er."),
    _l("Hvorfor «bare én» er vanskelig",
       ["Den første enheten senker evnen til å stoppe. Alkohol demper akkurat den delen av hjernen som tar fornuftige beslutninger – samtidig som belønningssystemet roper på mer.",
        "Det er ikke svak karakter når én blir fem. Det er derfor det lønner seg å bestemme antallet og sluttidspunktet før du begynner, mens den fornuftige delen fortsatt sitter i førersetet."],
       "Hvis du skal drikke denne uka: bestem antallet nå, og kjøp bare inn det."),
    _l("Hvis–så-planer",
       ["Forskning på vaner viser at én ting virker bedre enn det meste: å bestemme på forhånd hva du gjør i en bestemt situasjon. «Hvis X skjer, så gjør jeg Y.»",
        "Planen gjør at du slipper å bestemme deg der og da, når batteriet er tomt. Jo mer konkret, jo bedre: «Hvis jeg kommer hjem fredag og har lyst på øl, så tar jeg en alkoholfri først.»"],
       "Skriv én hvis–så-plan for den situasjonen som oftest går galt for deg."),
    _l("Protein metter",
       ["Protein holder deg mett lengre enn karbohydrater og fett. Det er også det kroppen trenger for å beholde muskler mens du går ned i vekt.",
        "Et godt grep er å spise proteinet først: kjøtt, fisk, egg, kylling eller cottage cheese før brødet og poteten. Da blir det naturlig å spise litt mindre av resten."],
       "I dag: få noe proteinrikt i hvert måltid, og spis det først."),
    _l("Hva fasten gjør",
       ["Når du faster 16–18 timer, er den viktigste effekten enkel: spisevinduet blir kortere, og du får i deg mindre totalt. Det er ingen magi, men det er en metode som passer mange godt.",
        "Fasten virker best når måltidene i vinduet er ordentlige. Et stort, proteinrikt måltid er bedre enn mange små snacks."],
       "Gjør første måltid etter fasten til et skikkelig måltid med protein og grønnsaker."),
    _l("Vekten svinger",
       ["Vekten kan gå opp og ned 1–2 kg fra dag til dag uten at du har lagt på deg et gram fett. Salt mat, alkohol, sen middag og trening binder vann i kroppen.",
        "Derfor er det trendlinja som teller, ikke enkeltdagene. Veie deg ofte gir mer data og mindre drama – én høy dag drukner i snittet."],
       "Vei deg i morgen tidlig, og se på linja for de siste 30 dagene i stedet for tallet i dag."),
    _l("Alkohol og kalorier",
       ["Én enhet alkohol er 12 gram ren alkohol – rundt 85 kalorier bare fra alkoholen. En halvliter øl ligger nærmere 200.",
        "Det som ofte koster mest, er likevel det som kommer etterpå: alkohol øker appetitten og senker terskelen for chips, pizza og nattmat. Mange som kutter alkohol, går ned i vekt uten å endre noe annet."],
       "Se på «Spart»-tallet ditt i appen og regn ut hvor mange kilo det tilsvarer på et år."),
    _l("Søvn og sult",
       ["Etter en natt med dårlig søvn får kroppen mer av hormonet som gir sult, og mindre av det som sier at du er mett. Du blir rett og slett sultnere – særlig på søtt og fett.",
        "God søvn er derfor et av de enkleste verktøyene for vektnedgang. Det er også grunnen til at en tung helg gjerne gir en tung mandag."],
       "Legg deg 30 minutter tidligere enn vanlig i kveld."),
    _l("Omgivelsene slår motivasjonen",
       ["Det du ser, er det du spiser og drikker. Står ølen fremst i kjøleskapet og godteriet på benken, må du si nei mange ganger om dagen.",
        "Det er mye lettere å si nei én gang i butikken enn tjue ganger hjemme. Små endringer i hvor ting står, gjør mer enn du tror."],
       "Flytt én ting du vil ha mindre av ut av syne – eller ut av huset."),
    _l("Gode alternativer",
       ["Ofte er det ikke alkoholen man savner, men ritualet: noe kaldt i et fint glass når arbeidsdagen er over. Det ritualet kan du beholde.",
        "Alkoholfri øl, kullsyrevann med sitron og is, eller en god alkoholfri drink fyller samme plass. Det viktigste er at det står klart før suget kommer."],
       "Sørg for at det står et godt alkoholfritt alternativ kaldt i kjøleskapet i kveld."),
    _l("En glipp er ikke et tilbakefall",
       ["Den farligste tanken etter en glipp er «nå er det uansett ødelagt». Den gjør én øl til en hel kveld, og én dårlig dag til en dårlig uke.",
        "Det som betyr noe, er hva du gjør neste dag. Derfor har rekka i appen et frikort: én glipp er lov, og du er fortsatt i gang."],
       "Tenk på din siste glipp. Hva kunne vært en god «neste dag»?"),
    _l("Stress og drikking",
       ["Mange drikker for å skru ned stresset etter en lang dag. Det virker en stund – men alkohol gjør søvnen dårligere, og dårlig søvn gjør morgendagen mer stressende.",
        "Det hjelper å ha noen andre «av-knapper»: en tur, en dusj, musikk, ti minutter alene i bilen før du går inn døra."],
       "Finn din egen av-knapp, og prøv den i dag når du kommer hjem."),
    _l("Si nei uten å forklare",
       ["Du skylder ingen en forklaring på hvorfor du ikke drikker. Jo lengre forklaring, jo mer inviterer du til diskusjon.",
        "Korte svar fungerer best: «Nei takk, jeg kjører», «Jeg tar en alkoholfri i kveld» eller bare «Nei takk.» Har du et glass i hånda, får du færre spørsmål."],
       "Bestem deg for ditt eget korte nei-svar, så det ligger klart."),
    _l("Spis litt saktere",
       ["Det tar rundt 20 minutter fra magen er fornøyd til hjernen får beskjeden. Spiser du fort, rekker du å spise mye mer enn du trenger.",
        "Legg fra deg gaffelen mellom bitene, snakk med barna, og vent litt før du forsyner deg på nytt."],
       "I dag til middag: vent 10 minutter før du tar påfyll."),
    _l("Tallerkenmodellen",
       ["En enkel måte å spise riktig på uten å telle kalorier: halve tallerkenen grønnsaker, en firedel protein og en firedel poteter, ris eller pasta.",
        "Barna trenger ikke samme fordeling, men du kan legge opp din egen tallerken slik – samme middag, ulik fordeling."],
       "Legg opp middagen etter tallerkenmodellen i dag."),
    _l("Hverdagsbevegelse teller",
       ["Det du forbrenner utenom trening – gå til bilen, bære handleposer, leke med barna, gå i trapper – kan utgjøre flere hundre kalorier om dagen.",
        "Skrittene fra Oura er en god pekepinn. Små ting som å ta en telefon stående eller gå en runde etter middag legger seg på toppen hver eneste dag."],
       "Gå en runde på 10 minutter etter middag i dag."),
    _l("Trening og vekt",
       ["Trening alene gir sjelden stor vektnedgang – det er lett å spise opp en treningsøkt. Det er maten og alkoholen som flytter vekten mest.",
        "Men trening gjør nesten alt annet bedre: søvn, humør, stress, blodtrykk – og du beholder musklene mens du går ned. Se på treningen som det som gjør resten lettere."],
       "Legg merke til hvordan du sover og har det etter en treningsdag, kontra uten."),
    _l("Vaneløkka",
       ["Alle vaner følger samme løkke: et signal (kl. 17, fredag, stress), en rutine (åpne en øl) og en belønning (avslapning, «nå er det helg»).",
        "Signalet og belønningen kan du sjelden fjerne. Men du kan bytte ut rutinen i midten – og beholde belønningen."],
       "Finn signalet bak den vanen du helst vil endre. Når og hvor skjer den?"),
    _l("Behold fredagsfølelsen",
       ["Fredagsølen handler ofte om følelsen av at uka er ferdig. Den følelsen kan du fortsatt få – med et annet ritual.",
        "God mat, en film med familien, en badstue, en tur – eller en alkoholfri øl i favorittglasset. Det viktigste er at det er noe du gleder deg til."],
       "Planlegg en fredagsbelønning som ikke er alkohol, og fortell noen om den."),
    _l("Kveldssnacks",
       ["Kveldssnacks er sjelden sult – oftere vane, kjedsomhet eller tretthet. Og når man faster, er kvelden der fasten oftest ryker.",
        "Hjelp deg selv: «kjøkkenet er stengt» etter et fast klokkeslett, puss tennene tidlig, og ha te eller kullsyrevann tilgjengelig."],
       "Bestem et klokkeslett der kjøkkenet stenger i kveld."),
    _l("Hva 30 alkoholfrie dager gjør",
       ["Mange som tar en pause fra alkohol, merker etter noen uker bedre søvn, mer energi, jevnere humør og at det blir lettere å holde vekta.",
        "Hvor mye du merker, varierer – men Oura-tallene dine vil vise det svart på hvitt. Se på restitusjonen nå og om en måned."],
       "Skriv ned i notatfeltet i dag hvordan du sover og føler deg, så du kan sammenligne senere."),
    _l("Hvem vil du være?",
       ["Det er lettere å holde en vane som passer med hvem du mener du er. «Jeg prøver å la være å drikke» er tyngre enn «Jeg er en som ikke drikker på hverdager».",
        "Hver gang du gjør det du har bestemt, er det en stemme for den personen du vil være."],
       "Fullfør setningen «Jeg er en som …» – og gjør én ting i dag som passer med den."),
    _l("Planlegg de vanskelige dagene",
       ["Julebord, bursdager, ferie og helligdager er der planene oftest ryker – fordi man ikke har planlagt dem.",
        "Bruk samme metode som for helgen: bestem antallet og sluttidspunktet på forhånd, spis før du går, og veksle med vann. Fortell gjerne én person planen din."],
       "Se i kalenderen etter neste vanskelige dag, og lag en plan for den nå."),
    _l("Barna ser deg",
       ["Barn lærer mer av det vi gjør enn av det vi sier. Når de ser deg velge vann til middag, gå en tur eller lage god mat, lærer de at det er normalt.",
        "Det er ikke et krav om å være perfekt – bare en påminnelse om at endringen din smitter, på en god måte."],
       "Gjør noe aktivt sammen med barna i dag, selv om det bare er 15 minutter."),
    _l("En god kveldsrutine",
       ["God søvn starter en time før du legger deg: dempet lys, mindre skjerm, ingen tung mat sent og ingen alkohol.",
        "Faste tider hjelper kroppen mest – også i helgene. Oura viser deg hva som gir best søvnpoeng for akkurat deg."],
       "Legg fra deg telefonen 30 minutter før du skal sove i kveld."),
    _l("Feire fremgang",
       ["Hjernen trenger belønning for å holde ut. Feir milepælene: 10 alkoholfrie hverdager, de første 5 kiloene, en hel uke med ukemålet nådd.",
        "Velg belønninger som ikke er mat eller alkohol – nytt treningstøy, en opplevelse, noe du har hatt lyst på lenge. Pengene du sparer, kan gå rett dit."],
       "Bestem hva du skal belønne deg med når du når neste milepæl."),
    _l("Veien videre",
       ["Du har lest gjennom hele kurset. Det viktigste å ta med seg: små vaner, planer før du trenger dem, ingen skam etter en glipp, og at søvn, mat og alkohol henger sammen.",
        "Coachen fortsetter som før. Les gjerne en gammel leksjon igjen når du trenger den – særlig nr. 2 (suget) og nr. 14 (glippen)."],
       "Velg den leksjonen som traff deg best, og les den en gang til i dag."),
]

LEKSJONER = [{"nr": i, **l} for i, l in enumerate(_INNHOLD, start=1)]


def opprett_tabell(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kurs_fremgang (
            nr INTEGER PRIMARY KEY,
            lest_dato TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _lest(conn) -> dict:
    return {r["nr"]: r["lest_dato"] for r in conn.execute("SELECT nr, lest_dato FROM kurs_fremgang")}


def _neste_tilgjengelige(lest: dict, i_dag: date):
    """Nummeret som kan leses i dag, eller None når kurset er ferdig."""
    if len(lest) >= len(LEKSJONER):
        return None
    siste_nr = max(lest) if lest else 0
    if lest and lest[siste_nr] >= i_dag.isoformat():
        return siste_nr  # allerede lest i dag – ny i morgen
    return siste_nr + 1


def status(conn, i_dag: date) -> dict:
    lest = _lest(conn)
    lest_i_dag = any(d == i_dag.isoformat() for d in lest.values())
    neste = _neste_tilgjengelige(lest, i_dag)
    if neste is None:
        dagens = None
    elif lest_i_dag:
        dagens = LEKSJONER[max(nr for nr, d in lest.items() if d == i_dag.isoformat()) - 1]
    else:
        dagens = LEKSJONER[neste - 1]
    return {
        "dagens": dagens,
        "lest_i_dag": lest_i_dag,
        "antall_lest": len(lest),
        "totalt": len(LEKSJONER),
        "fullfort": len(lest) >= len(LEKSJONER),
        "leste": [{"nr": nr, "tittel": LEKSJONER[nr - 1]["tittel"]} for nr in sorted(lest)],
    }


def marker_lest(conn, nr: int, i_dag: date) -> None:
    lest = _lest(conn)
    if nr in lest:
        return  # å lese en gammel leksjon på nytt er alltid greit
    if nr != _neste_tilgjengelige(lest, i_dag) or (lest and max(lest.values()) >= i_dag.isoformat()):
        raise ValueError("Den leksjonen er ikke låst opp ennå.")
    conn.execute("INSERT INTO kurs_fremgang (nr, lest_dato) VALUES (?, ?)", (nr, i_dag.isoformat()))
    conn.commit()


def hent_leksjon(conn, nr: int, i_dag: date):
    lest = _lest(conn)
    if nr in lest or nr == _neste_tilgjengelige(lest, i_dag):
        return LEKSJONER[nr - 1] if 1 <= nr <= len(LEKSJONER) else None
    return None


def dagens_tittel_hvis_lest(conn, i_dag: date):
    for r in conn.execute("SELECT nr FROM kurs_fremgang WHERE lest_dato = ?", (i_dag.isoformat(),)):
        return LEKSJONER[r["nr"] - 1]["tittel"]
    return None
