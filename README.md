# Superhuman 2.0 – livsstilscoach

Din personlige coach på telefonen. Målet er å gå ned rundt 20 kilo og drikke mindre: ingen alkohol på hverdager, og få enheter i helgene. Coachen sier fra når det er treningsdag, foreslår sunn og rask mat hele familien kan spise, og minner deg på ting gjennom dagen. Selve treningen styrer du selv.

Appen ligger på internett på **https://trening.flibber.no** (driftes hos Railway). Den beskyttes med passord, og du legger den til på hjemskjermen som en vanlig app.

## Hva appen gjør

- **I dag:** Hver dag starter med en beskjed fra coachen. På treningsdager står det med store bokstaver **«I DAG ER DET TRENINGSDAG»**. Under beskjeden krysser du av for dagen: **Fastet**, **Alkohol** (med antall enheter), **Trent** og **Syk**. Du ser også hvor mange alkoholfrie hverdager du har hatt på rad, og hva det blir til middag.
  - **Spør coachen:** Still et spørsmål, f.eks. «Hva kan jeg spise til kvelds?»
  - **Det er vanskelig nå:** Trykk når du får lyst på alkohol. Da får du med en gang én konkret ting du kan gjøre i stedet.
  - **Helgeplan** (fredag til søndag): Bestem antall enheter for helgen mens du er edru, og få noen tips til å holde planen. Søndag kveld får du en kort oppsummering av hvordan det gikk.
- **Mat:** Ukens fem middager (mandag til fredag) er raske og barnevennlige. Du får også en lunsj du lager på søndag og tar med i bokser, tips til pålegg på surdeigsbrød og en handleliste du kan krysse av i butikken. Trykk **«Bytt»** for å få en annen middag.
- **Oversikt:** Vekt fra Withings og søvn, restitusjon og aktivitet fra Oura, som før.
- **Historikk:** Alle dagene du har krysset av, med tall for de siste 30 dagene.

**Treningsdager:** Coachen bestemmer dem selv. Du starter med 3 i uka, og antallet går opp når du klarer alle og ned når mange glipper (minst 2 og maks 5). Viser Oura lav restitusjon, eller krysset du av «Syk» dagen før, flyttes økta til neste ledige dag.

## Påminnelser på telefonen

Standardtidene er disse. Du kan endre dem under **«Varseltider»** nederst på I dag-siden.

| Når | Hva |
|---|---|
| Hver morgen 07:00 | Dagens beskjed (og «I DAG ER DET TRENINGSDAG» når det gjelder) |
| Hverdager 15:30 | Dagens middag |
| Fredag 15:00 | Lag helgeplanen |
| Hver kveld 21:00 | Kryss av dagen (bare hvis du ikke har gjort det) |
| Søndag 18:00 | Ny ukemeny, handleliste og treningsdager er klare |

**Slik slår du på varslene (én gang):** Åpne appen fra **ikonet på hjemskjermen** (ikke fra Safari), trykk **«Slå på varsler»** og deretter **«Tillat»**. Du får et testvarsel med en gang. Har du fjernet appen fra hjemskjermen og lagt den til på nytt, må du gjøre dette igjen.

## Coachen (Claude)

Beskjedene, menyene og svarene skrives av Claude, en KI fra selskapet Anthropic. Appen sender bare et kort sammendrag til Claude: vekten, målvekten, avkrysningene de siste 14 dagene og Oura-tallene for søvn og restitusjon.

- Det koster omtrent 1–2 dollar i måneden. Betalingen går fra kreditten på console.anthropic.com.
- Nøkkelen ligger på Railway som `ANTHROPIC_API_KEY`.
- Er nøkkelen borte eller kreditten tom, bruker appen faste reservetekster og en fast middagsliste. Da står ingenting tomt, men det blir mindre personlig.

## For den som jobber videre med koden

- Python/Flask med SQLite. `app.py` har alle sidene, `livsstil.py` har avkrysning og ukeplan, `coach.py` har alt som snakker med Claude, og `varsler.py` har push-varsler og klokka som sender dem.
- Testene kjøres med `python -m pytest tests`. De bruker en egen midlertidig database og rører aldri den ekte.
- Kjøre lokalt: dobbeltklikk **«Start appen.bat»**. Påminnelsene sendes bare fra den ekte appen på internett.
- Endringer settes i drift med `git push` til `main`. Railway oppdaterer appen automatisk etter omtrent ett minutt.
