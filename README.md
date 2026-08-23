# Superhuman 2.0

Personlig trenings- og oppfølgingsapp: viser dagens økt, holder styr på fremgang, og lar deg logge vekt. Designet for å ligge på hjemskjermen og føles som en vanlig iPhone-app — meny nederst, store trykkeflater, og følger automatisk om telefonen din er satt til lys eller mørk modus.

## Hvordan bruke det

1. Dobbeltklikk på **"Start appen.bat"**
2. Et svart vindu (terminalen) åpner seg og en nettleser-fane åpner appen automatisk
3. Under **"I dag"** ser du et motiverende sitat, dagens planlagte økt, og hele ukens plan rett under. Under "Registrer dagen" trykker du enten **"Gjennomført"** eller **"Ikke gjennomført"**, krysser eventuelt av hendelser som skjedde den dagen, og lagrer. Trykk på en annen dag i ukelisten for å se hva den dagen inneholder — nyttig på hviledager, når du vil sjekke en kommende øvelse på forhånd
4. Under **"Fysio-øvelser"** legger du inn øvelsene du får av fysioterapeuten. De dukker da automatisk opp under "I dag" hver dag
5. Under **"Hendelser"** styrer du hvilke hendelsestyper (f.eks. "Alkohol", "Syk") som skal kunne krysses av i den daglige loggen — legg gjerne til flere selv
6. Under **"Vekt"** logger du vekten din — appen tegner en enkel graf når du har registrert minst to ganger
7. Under **"Historikk"** ser du tilbake på tidligere dager: hvor stor andel du har gjennomført, hvor ofte hver hendelsestype er registrert, og en liste over hver enkelt dag

Alt lagres automatisk i en fil som heter `trening.db` i denne mappen. Ikke slett den.

For å avslutte: lukk nettleser-fanen og lukk det svarte terminalvinduet.

## Bruk appen på mobilen (som en vanlig app)

1. Start appen på PC-en som vanlig (**"Start appen.bat"**)
2. I det svarte terminalvinduet står det en linje som f.eks. `For å åpne appen på mobilen (samme wifi): http://192.168.1.23:5003` — skriv akkurat den adressen inn i Safari på iPhonen (samme wifi som PC-en)
3. Trykk på del-ikonet (firkant med pil opp) → "Legg til på Hjem-skjerm"

Nå ligger Superhuman 2.0 som et eget ikon på hjemskjermen. PC-en må stå på og kjøre appen hver gang du vil bruke den fra telefonen.

**Merk:** Siden navnet på appen er endret, må du fjerne det gamle ikonet fra hjemskjermen (trykk og hold → "Fjern app") og legge det til på nytt med stegene over for at det nye navnet skal vises.

## Daglig påminnelse på iPhonen

Appen kan ikke sende varsler helt av seg selv (det krever at appen ligger ute på internett, ikke bare hjemme-wifi). Løsningen er å bruke iPhonens innebygde **"Snarveier"**-app til å hente dagens økt og vise den som et varsel hver dag:

1. Åpne **Snarveier**-appen på iPhonen
2. Trykk på fanen **"Automasjon"** nederst → **"+"** øverst til høyre → **"Opprett personlig automasjon"**
3. Velg **"Tid på dagen"**, sett klokkeslettet du vil bli minnet (f.eks. 08:00), velg **"Daglig"** → **"Neste"**
4. Trykk **"Legg til handling"**, søk opp **"Hent innhold for URL-adresse"**, og lim inn adressen til treningsappen med `/api/varsel` bakerst, f.eks. `http://192.168.1.23:5003/api/varsel` (samme adresse som du brukte da du la appen til på hjemskjermen)
5. Legg til enda en handling: søk opp **"Vis varsel"**. Som tekst — ikke skriv noe selv, trykk på tekstfeltet og velg variabelen som heter noe sånt som **"Innhold for URL-adresse"** (resultatet fra forrige steg)
6. Trykk **"Neste"**, og **skru av "Spør før kjøring"** (viktig — ellers må du bekrefte manuelt hver dag) → **"Ferdig"**

Nå får du et varsel hver dag med akkurat hva slags trening du har, hentet direkte fra appen. **Merk:** PC-en må stå på og ha appen kjørende når varselet skal hentes, og telefonen må være på samme wifi. Hvis PC-ens nettverksadresse noen gang endrer seg, må adressen i steg 4 oppdateres.

## Om treningsopplegget

Planen er delt i tre faser som bygger på hverandre:

- **Fase 1 (uke 1-4):** Bygge vane og kondisjon — kun gange og roing, ingen styrkeøvelser ennå
- **Fase 2 (uke 5-8):** Styrke introduseres, i tillegg til gange og roing
- **Fase 3 (uke 9+):** Videre progresjon

Uke 1 startet automatisk den dagen appen ble tatt i bruk første gang. Appen regner selv ut hvilken uke og fase du er i.

I uke 1-4 er lørdag en ekstra hviledag (i tillegg til onsdag og søndag) — altså 3 hviledager i uken mens du bygger opp vanen. Fra uke 5 kommer den lange gåturen på lørdag tilbake, og tirsdag/fredag går fra gange/roing over til styrkeøkter.

Gange (walkingpad) og roing (rowingpad) har egen fremgang uke for uke gjennom fase 1 og 2 — tid, tempo og stigning økes gradvis. Fra fase 3 (uke 9+) legges uken om med en tredje styrkeøkt.

Trykk på en øvelse (de runde knappene under "Øvelser") for å se en animert strektegning som viser selve bevegelsen, pluss steg-for-steg-instruksjoner og et "Pass på"-punkt med det viktigste å tenke på. På styrkeøvelser kan du også logge vekten og repsene du brukte den dagen — du ser da hva du brukte sist, så du kan prøve å øke litt over tid.

Når du har vært hos fysioterapeut, legger du inn øvelsene deres under "Fysio-øvelser" i appen — de dukker da automatisk opp under "I dag".

**Planen venter på deg ved sykdom:** Hvis du krysser av for en hendelsestype som er merket "pauser treningsplanen" (Syk er satt opp slik som standard), teller ikke den dagen med i ukeberegningen. Blir du syk i noen dager, holder appen deg igjen på samme uke i stedet for å marsjere videre i planen uten deg. Du styrer selv hvilke hendelsestyper som skal ha denne effekten, under "Hendelser".

Kilder planen bygger på:
- [Beginner Dumbbell Program: Full-Body Workout Plan (StrengthLog)](https://www.strengthlog.com/beginner-dumbbell-program/)
- [Walking Workout Plan for Beginners (getsteps.app)](https://getsteps.app/blog/walking-workout-plan-beginners)

## Neste steg (ikke bygget ennå)

- Automatisk henting av søvn/aktivitet fra Oura-ringen
- En omvei for å få data inn i Apple Helse (krever en egen løsning, siden vanlige nettsider ikke har direkte tilgang til Apple Helse)
