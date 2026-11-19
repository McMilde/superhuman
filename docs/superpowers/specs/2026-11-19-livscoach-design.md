# Superhuman 2.0 → Livscoach — design

Dato: 2026-11-19 · Status: til godkjenning hos Eivin

## Hvorfor
Eivin har skadet seg og klarer ikke å følge den faste treningsplanen lenger. Han vil endre hele livsstilen: gå ned 20 kg og slutte å drikke på hverdager, med noen få enheter i helgene. Han trenger en coach som sier hva han skal gjøre og minner ham på det gjennom dagen. Treningen styrer han selv. Appen skal bare si *når* han skal trene.

Han sier selv at han har vanskelig for å stoppe når han først har begynt å drikke. Alkoholdelen må derfor hjelpe ham *før* han begynner, ikke prøve å bremse ham mens han drikker.

## Mål
- Hver morgen en beskjed fra coachen: om det er treningsdag, hva han bør spise i dag og en kort oppmuntring basert på dataene hans.
- En avkrysning per dag: **Fastet · Alkohol (+ antall enheter) · Trent · Syk**.
- Sunn og rask mat som barn på 5 og 10 år også spiser: ukemeny, handleliste, lunsj som lages på forhånd, og lunsjtips med surdeigsbrød.
- Alkoholoppfølging: hverdager uten alkohol (med telling av dager på rad), en helgeplan som legges fredag mens han er edru, oppsummering søndag og knappen «Det er vanskelig nå».
- Coachen bestemmer treningsdagene.
- Ekte varsler på iPhone.
- **Beholdes uendret:** Withings, Oura, Oversikt-dashboardet, vekt og målvekt, historikk, sikkerhetskopi og innlogging.

## Ikke-mål
- Ingen nedtelling eller tidsur for fasten. Han vet selv når fasten er ferdig.
- Ingen treningsøvelser, faser eller treningsprogram.
- Ingen kaloritelling for brukeren.

## Anti-mål (dette ville vært en fiasko selv om alt virket)
- Coachen moraliserer, skammer ham eller kjefter etter en dårlig helg.
- Varsler som maser om noe han allerede har gjort.
- Medisinske råd eller behandling av alkoholproblemer. Coachen kan rolig nevne fastlegen eller RUSinfo (915 08588) når det passer, men aldri ofte og aldri belærende.

## Tilnærminger som ble vurdert
| | Hva | Avveining |
|---|---|---|
| A | Fast, regelstyrt opplegg med en oppskriftsbank | Gratis og forutsigbart, men upersonlig og kan ikke svare på spørsmål |
| B | Ren KI-coach (Claude) | Personlig og kan svare, men koster litt og har ingenting å falle tilbake på hvis den feiler |
| **C (valgt av Eivin)** | **Fast grunnmur + Claude skriver daglige beskjeder, menyer og svar** | Personlig og robust. Hvis KI-en feiler, brukes tekstene fra grunnmuren. Koster noen titalls kroner i måneden |

## Hvordan (avgjørelser)
- **Bygges inn i eksisterende Superhuman 2.0** (Flask + SQLite på Railway, trening.flibber.no, GitHub McMilde/superhuman). Samme adresse og innlogging, og samme kobling til Withings og Oura. *(Mitt valg: det er der dataene og koblingene allerede ligger.)*
- **Treningsplanen tas ut av appen:** okt_mal, øvelser, fysio og styrke-logg fjernes fra skjermbildene. Tabellene i databasen slettes ikke (prosjektets regel: aldri slett data). Gamle dagslogg-rader vises fortsatt i Historikk.
- **Faner (mitt forslag):** I dag (coachens beskjed + avkrysning + dagens middag) · Mat (ukemeny, handleliste, lunsj) · Oversikt · Vekt · Historikk. Chat med coachen ligger som en knapp på I dag-siden.
- **Ny avkrysning per dag:** fastet, alkohol, antall enheter (vises bare når alkohol er krysset av), trent og syk. Valgfritt notat.
- **KI:** Claude via Anthropic API. Coachen får kun et kort sammendrag: siste 14 dagers avkrysninger, vektutviklingen, målvekt, Oura-søvn og -restitusjon, og ukens plan. Eivin må opprette en konto på console.anthropic.com med betalingskort og en API-nøkkel, som legges inn på Railway som `ANTHROPIC_API_KEY`. Helsedata sendes da til Anthropic, og det godtar han ved å velge C.
- **Treningsdager:** søndag legger coachen ukeplanen (forslag: 3 treningsdager i starten, som kan økes når det går bra). Om morgenen kan coachen flytte en treningsdag hvis Oura-restitusjonen er lav, eller hvis forrige dag er krysset av som «syk». Coachen sier bare «I DAG ER DET TRENINGSDAG», ikke hva han skal trene.
- **Mat:** ukemenyen lages søndag (5 raske middager for hele familien), med handleliste og én lunsj som lages på forhånd og holder i 4–5 dager (f.eks. kjøttdeig og grønnsaker). Knappen «bytt» gir et nytt middagsforslag. Lunsjtips med surdeigsbrød fokuserer på pålegg som metter godt. Vekttap-tempo: rundt 0,5 kg i uka. Det styrer porsjonsrådene, uten at han må telle kalorier.
- **Alkohol:**
  - Hverdager: målet er null, og appen teller dager på rad.
  - Fredag ettermiddag: «Hvor mange enheter denne helgen?» Han legger inn tallet, og coachen gir 2–3 konkrete råd (kjøp bare inn det antallet, vann annenhver gang, et sluttidspunkt).
  - Søndag: planlagt mot faktisk antall, nøytralt og fremoverlent.
  - «Det er vanskelig nå»: et kort, konkret alternativ med en gang (fra Claude, med faste tekster som reserve).
- **Varsler:** web-push til appen på iPhonens hjemskjerm (krever iOS 16.4 eller nyere, som han har). Standardtider, som kan endres i innstillinger:
  - 07:00 morgenbeskjed
  - 15:30 middagsforslag
  - fredag 15:00 helgeplan
  - 21:00 avkrysning, kun hvis dagen ikke er registrert
  - søndag 18:00 ny ukemeny og ukeplan
- **Reserveløsning:** hvis Claude ikke svarer, brukes regelstyrte tekster og en fast middagsliste, slik at appen aldri står tom.

## Overlates til den som bygger
- Hvordan varslene planlegges og sendes på Railway (planlegger inni appen eller Railway cron), inkludert lagring av push-abonnementet.
- Nøyaktig hvilken Claude-modell som brukes og ordlyden i instruksene til den. Tonen skal være varm, direkte, kort og på norsk.
- Datamodell for dagssjekk, ukeplan og meny, med migrering i prosjektets vanlige stil (ALTER TABLE ADD, aldri DROP av brukerdata).
- Test mot en kopi av databasen, aldri den ekte. Sjekk med Playwright i lys og mørk modus på iPhone-størrelse.

## Åpent hos Eivin
- Den planlagte e-posten «Trenings-dytt» kl. 14 blir overflødig når push-varslene virker. Mitt forslag er å skru den av da.
