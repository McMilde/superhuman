function $(id) {
  return document.getElementById(id);
}

async function hentJson(url, valg) {
  const res = await fetch(url, valg);
  if (!res.ok) {
    let melding = "Noe gikk galt. Prøv igjen.";
    try {
      melding = (await res.json()).error || melding;
    } catch (e) {}
    throw new Error(melding);
  }
  return res.json();
}

function postJson(url, data) {
  return hentJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data || {}),
  });
}

const UKEDAG = ["søndag", "mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag"];
const MANED = ["januar", "februar", "mars", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "desember"];

function langDato(iso) {
  const d = new Date(`${iso}T12:00:00`);
  const uke = UKEDAG[d.getDay()];
  return `${uke[0].toUpperCase()}${uke.slice(1)} ${d.getDate()}. ${MANED[d.getMonth()]}`;
}

function kortUkedag(iso) {
  const d = new Date(`${iso}T12:00:00`);
  const uke = UKEDAG[d.getDay()];
  return `${uke[0].toUpperCase()}${uke.slice(1)}`;
}

function idagDato() {
  const d = new Date();
  const mnd = String(d.getMonth() + 1).padStart(2, "0");
  const dag = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mnd}-${dag}`;
}

function lagreLokalt(nokkel, verdi) {
  try {
    localStorage.setItem(nokkel, JSON.stringify(verdi));
  } catch (e) {}
}

function hentLokalt(nokkel, standard) {
  try {
    const v = localStorage.getItem(nokkel);
    return v ? JSON.parse(v) : standard;
  } catch (e) {
    return standard;
  }
}

// ---- Faner ----

function visFane(navn) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === navn));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${navn}`));
  if (navn === "mat") lastMat();
  if (navn === "oversikt") lastOversikt();
  if (navn === "historikk") lastHistorikk();
  window.scrollTo(0, 0);
}

function settOppFaner() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => visFane(btn.dataset.tab));
  });
}

// ---- I dag ----

let dagData = null;
let sjekk = { fastet: false, alkohol: false, alkohol_enheter: "", trent: false, syk: false, notat: "" };

async function lastIdag() {
  $("toppDato").textContent = langDato(idagDato());
  try {
    dagData = await hentJson("/api/i-dag");
  } catch (e) {
    $("coachTittel").textContent = "Fikk ikke kontakt med appen";
    $("coachTekst").textContent = "Sjekk nettet og dra ned for å prøve igjen.";
    return;
  }
  $("toppDato").textContent = langDato(dagData.dato);
  visCoach(dagData);
  if (!valgtDato || valgtDato === sisteIdag) valgtDato = dagData.dato;
  sisteIdag = dagData.dato;
  visSjekk(dagData.dagssjekk);
  velgDato(valgtDato);
  visHelg(dagData);
  visUkemal(dagData.ukemal);
  visMiddag(dagData.middag);
  lastAlkoholInnsikt();
  lastKurs();
}

function visCoach(d) {
  const kort = $("coachKort");
  kort.classList.toggle("coach-trening", d.treningsdag);
  $("coachTittel").textContent = d.melding.tittel;
  $("coachTekst").textContent = d.melding.tekst;
  const flytt = $("coachFlytt");
  flytt.textContent = d.flytt_grunn || "";
  flytt.classList.toggle("hidden", !d.flytt_grunn || d.melding.tekst.includes(d.flytt_grunn));
}

function visSjekk(s) {
  sjekk = {
    fastet: !!(s && s.fastet),
    alkohol: !!(s && s.alkohol),
    alkohol_enheter: s && s.alkohol_enheter != null ? String(s.alkohol_enheter).replace(".", ",") : "",
    trent: !!(s && s.trent),
    syk: !!(s && s.syk),
    notat: (s && s.notat) || "",
  };
  document.querySelectorAll("#sjekkGrid .sjekk-rute").forEach((btn) => {
    btn.setAttribute("aria-pressed", sjekk[btn.dataset.felt] ? "true" : "false");
  });
  $("enheterRad").classList.toggle("hidden", !sjekk.alkohol);
  $("alkoholEnheter").value = sjekk.alkohol_enheter;
  $("sjekkNotat").value = sjekk.notat;
}

// ---- Bla mellom dager ----

const MAKS_DAGER_TILBAKE = 30;
let valgtDato = null;
let sisteIdag = null;

function flyttDato(iso, dager) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + dager);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function datoEtikett(iso) {
  if (iso === sisteIdag) return "I dag";
  if (iso === flyttDato(sisteIdag, -1)) return "I går";
  const d = new Date(`${iso}T12:00:00`);
  return `${UKEDAG[d.getDay()][0].toUpperCase()}${UKEDAG[d.getDay()].slice(1)} ${d.getDate()}. ${MANED[d.getMonth()].slice(0, 3)}`;
}

async function lastDagDetaljer(dato) {
  const d = await hentJson(`/api/dag-detaljer?dato=${dato}`).catch(() => null);
  if (!d || dato !== valgtDato) return;
  visSjekk(d.dagssjekk);
  const tellende = d.oura_okter.filter((o) => o.teller);
  if (!d.dagssjekk && tellende.length && !sjekk.trent) {
    sjekk.trent = true;
    document.querySelector('.sjekk-rute[data-felt="trent"]').setAttribute("aria-pressed", "true");
  }
  const okt = $("ouraOkt");
  okt.textContent = d.oura_okter.length
    ? "Oura: " + d.oura_okter.map((o) => `${o.aktivitet} ${o.minutter} min`).join(", ")
    : "";
  okt.classList.toggle("hidden", !d.oura_okter.length);
  $("ouraTilgang").classList.toggle("hidden", d.oura_okt_tilgang !== false);
}

function velgDato(dato) {
  const tidligste = flyttDato(sisteIdag, -MAKS_DAGER_TILBAKE);
  if (dato > sisteIdag || dato < tidligste) return;
  valgtDato = dato;
  $("datoEtikett").textContent = datoEtikett(dato);
  $("sjekkKort").classList.toggle("annen-dag", dato !== sisteIdag);
  $("nesteDagBtn").disabled = dato >= sisteIdag;
  $("forrigeDagBtn").disabled = dato <= tidligste;
  lastDagDetaljer(dato);
}

let lagretTimer = null;

async function lagreSjekk() {
  try {
    const rad = await postJson("/api/dagssjekk", { ...sjekk, dato: valgtDato || (dagData ? dagData.dato : idagDato()) });
    const hint = $("sjekkLagret");
    hint.textContent = valgtDato === sisteIdag ? "Lagret" : `Lagret for ${datoEtikett(valgtDato).toLowerCase()}`;
    hint.classList.remove("hidden");
    clearTimeout(lagretTimer);
    lagretTimer = setTimeout(() => hint.classList.add("hidden"), 1500);
    if (dagData && valgtDato === sisteIdag) dagData.dagssjekk = rad;
    lastAlkoholInnsikt();
  } catch (e) {
    const hint = $("sjekkLagret");
    hint.textContent = "Ble ikke lagret – prøv igjen";
    hint.classList.remove("hidden");
  }
}

function veksleSjekk(felt) {
  sjekk[felt] = !sjekk[felt];
  if (felt === "alkohol" && !sjekk.alkohol) sjekk.alkohol_enheter = "";
  visSjekk(sjekk);
  if (felt === "alkohol" && sjekk.alkohol) $("alkoholEnheter").focus();
  lagreSjekk();
}

function tall(n, desimaler = 0) {
  return Number(n).toLocaleString("nb-NO", { minimumFractionDigits: desimaler, maximumFractionDigits: desimaler });
}

function kortDato(iso) {
  const d = new Date(`${iso}T12:00:00`);
  return `${d.getDate()}. ${MANED[d.getMonth()]}`;
}

function effektRad(navn, med, uten) {
  if (med == null || uten == null) return "";
  const diff = med - uten;
  const tekst = diff < 0 ? `${tall(Math.abs(diff))} poeng lavere` : diff > 0 ? `${tall(diff)} poeng høyere` : "ingen forskjell";
  return `
    <div class="effekt-topp"><span>${navn}</span><strong class="${diff < 0 ? "effekt-ned" : ""}">${tekst}</strong></div>
    <div class="effekt-stolpe"><span class="effekt-etikett">Etter alkohol</span><span class="effekt-bar effekt-bar-med" style="--v:${med}%"></span><span class="effekt-verdi">${med}</span></div>
    <div class="effekt-stolpe"><span class="effekt-etikett">Uten</span><span class="effekt-bar" style="--v:${uten}%"></span><span class="effekt-verdi">${uten}</span></div>`;
}

let innsiktData = null;

async function lastAlkoholInnsikt() {
  innsiktData = await hentJson("/api/alkohol-innsikt").catch(() => null);
  if (!innsiktData) return;
  const d = innsiktData;
  $("rekkeNa").textContent = d.rekke;
  $("rekkeBeste").textContent = Math.max(d.beste_rekke, d.rekke);
  $("rekkeForklaring").textContent = d.frikort_brukt
    ? "Frikortet er brukt: rekka lever videre, men en ny glipp de neste dagene nullstiller den."
    : "Én glipp er lov uten at rekka nullstilles. To innen en uke, og den starter på nytt.";
  $("rekkeForklaring").classList.toggle("frikort-brukt", !!d.frikort_brukt);

  const e = d.effekt;
  $("effektVisning").classList.toggle("hidden", !e.nok_data);
  $("effektVenter").classList.toggle("hidden", e.nok_data);
  if (e.nok_data) {
    $("effektRestitusjon").innerHTML = effektRad("Restitusjon (Oura)", e.restitusjon_med, e.restitusjon_uten);
    $("effektSovn").innerHTML = effektRad("Søvn (Oura)", e.sovn_med, e.sovn_uten);
    $("effektGrunnlag").textContent = `Snitt av dine egne tall: ${e.dager_med} dager etter alkohol og ${e.dager_uten} dager uten.`;
  } else {
    const mangler = [];
    if (e.trengs_uten > 0) mangler.push(`${e.trengs_uten} ${e.trengs_uten === 1 ? "kveld" : "kvelder"} uten alkohol`);
    if (e.trengs_med > 0) mangler.push(`${e.trengs_med} med alkohol`);
    $("effektVenter").textContent =
      `Her får du se hvordan alkohol påvirker søvnen og restitusjonen din, målt med Oura. ` +
      `Appen trenger minst 5 kvelder av hver for å sammenligne – det mangler ${mangler.join(" og ")}. Bare kryss av som vanlig.`;
  }

  const s = d.spart;
  const harUtgangspunkt = !!d.utgangspunkt;
  $("spartSkjema").classList.toggle("hidden", harUtgangspunkt);
  $("spartVisning").classList.toggle("hidden", !harUtgangspunkt);
  if (harUtgangspunkt) {
    if (!s) {
      $("spartHoved").textContent = "Kryss av noen dager, så regner appen ut hva du sparer.";
      $("spartUnder").textContent = "";
    } else if (s.enheter_spart > 0) {
      $("spartHoved").textContent = `${tall(s.kr)} kr og ${tall(s.kalorier)} kalorier`;
      $("spartUnder").textContent =
        `Siden ${kortDato(s.fra_dato)}: ${tall(s.enheter_spart, s.enheter_spart % 1 ? 1 : 0)} færre enheter enn før – omtrent ${tall(s.kg, 1)} kg fett.`;
    } else {
      $("spartHoved").textContent = "Ingen besparelse ennå";
      $("spartUnder").textContent = `Siden ${kortDato(s.fra_dato)} har du drukket omtrent som før. Hver alkoholfrie dag teller fra nå.`;
    }
  }
}

async function lagreUtgangspunkt() {
  const feil = $("utgangspunktFeil");
  feil.classList.add("hidden");
  try {
    await postJson("/api/alkohol-innsikt/utgangspunkt", {
      enheter_per_uke: $("utgangspunktEnheter").value.trim(),
      kr_per_enhet: $("utgangspunktKr").value.trim(),
    });
    await lastAlkoholInnsikt();
  } catch (e) {
    feil.textContent = e.message;
    feil.classList.remove("hidden");
  }
}

function visMiddag(m) {
  if (!m) {
    $("middagNavn").textContent = "Ingen plan i dag";
    $("middagInfo").textContent = "Helg – spis noe godt og enkelt med familien.";
    return;
  }
  $("middagNavn").textContent = m.navn;
  $("middagInfo").textContent = `${m.minutter} min · ${m.beskrivelse}`;
}

let valgtePlaner = new Set();
let planForslag = [];

function visHelg(d) {
  const kort = $("helgKort");
  const viaLenke = location.hash === "#helg";
  const helg = d.helg;
  const harOppsummering = helg && helg.oppsummering;
  kort.classList.toggle("hidden", !(d.er_fredag_til_sondag || viaLenke || harOppsummering));
  const harPlan = helg && helg.planlagte_enheter != null;
  $("helgSkjema").classList.toggle("hidden", harPlan);
  $("helgPlanvalg").classList.add("hidden");
  $("helgVisning").classList.toggle("hidden", !harPlan);
  if (harPlan) {
    visTeller(helg, d.er_fredag_til_sondag);
    $("helgTips").innerHTML = helg.tips.map((t) => `<li>${escapeHtml(t)}</li>`).join("");
    $("planerVisning").classList.toggle("hidden", !helg.planer.length);
    $("helgPlaner").innerHTML = helg.planer.map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  }
  const opps = $("helgOppsummering");
  opps.textContent = harOppsummering ? helg.oppsummering : "";
  opps.classList.toggle("hidden", !harOppsummering);
}

function visTeller(helg, iHelgen) {
  const brukt = helg.brukt || 0;
  const plan = helg.planlagte_enheter;
  $("helgBrukt").textContent = tall(brukt, brukt % 1 ? 1 : 0);
  $("helgTall").textContent = plan;
  const andel = plan > 0 ? Math.min(100, (brukt / plan) * 100) : brukt > 0 ? 100 : 0;
  $("tellerFyll").style.width = `${andel}%`;
  $("tellerFyll").classList.toggle("over", brukt > plan);
  $("helgSluttTekst").textContent = helg.sluttid ? `Kvelden er over kl. ${helg.sluttid} – du får et varsel da.` : "";
  $("tellerKnapper").classList.toggle("hidden", !iHelgen);
  const melding = $("tellerMelding");
  let tekst = "";
  if (brukt > 0 && brukt === plan) tekst = "Det var planen din. Bytt til vann eller alkoholfritt nå – du klarte det.";
  else if (brukt > plan) tekst = "Du er over planen. Det er helt greit å stoppe her – et glass vann nå hjelper.";
  melding.textContent = tekst;
  melding.classList.toggle("hidden", !tekst);
}

async function endreEnhet(endring) {
  const btn = $("plussEnhetBtn");
  btn.disabled = true;
  try {
    const r = await postJson("/api/dagssjekk/enhet", { endring });
    if (valgtDato === sisteIdag) visSjekk(r.dagssjekk || null);
    dagData.helg.brukt = r.brukt_i_helgen;
    visTeller(dagData.helg, true);
    lastAlkoholInnsikt();
  } catch (e) {
    $("tellerMelding").textContent = e.message;
    $("tellerMelding").classList.remove("hidden");
  } finally {
    btn.disabled = false;
  }
}

async function lagreHelg() {
  const feil = $("helgFeil");
  feil.classList.add("hidden");
  const btn = $("helgLagreBtn");
  btn.disabled = true;
  btn.textContent = "Lagrer …";
  try {
    const r = await postJson("/api/helg", {
      planlagte_enheter: $("helgEnheter").value.trim(),
      sluttid: $("helgSluttid").value || "22:00",
    });
    const tidligerePlaner = (dagData.helg && dagData.helg.planer) || [];
    dagData.helg = { ...r, planer: tidligerePlaner };
    planForslag = r.planforslag || [];
    valgtePlaner = new Set(tidligerePlaner.filter((p) => planForslag.includes(p)));
    $("egenPlan").value = tidligerePlaner.find((p) => !planForslag.includes(p)) || "";
    visPlanvalg();
  } catch (e) {
    feil.textContent = e.message;
    feil.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = "Lagre plan";
  }
}

function visPlanvalg() {
  $("helgSkjema").classList.add("hidden");
  $("helgVisning").classList.add("hidden");
  $("helgPlanvalg").classList.remove("hidden");
  $("planForslag").innerHTML = planForslag
    .map((p, i) => `<button type="button" class="plan-valg" aria-pressed="${valgtePlaner.has(p)}" data-plan="${i}">${escapeHtml(p)}</button>`)
    .join("");
}

async function lagrePlaner() {
  const planer = [...valgtePlaner];
  const egen = $("egenPlan").value.trim();
  if (egen) planer.push(egen);
  const btn = $("planerLagreBtn");
  btn.disabled = true;
  try {
    const r = await postJson("/api/helg/planer", { planer });
    dagData.helg.planer = r.planer;
  } catch (e) {}
  btn.disabled = false;
  visHelg(dagData);
}

// ---- Minikurs ----

let kursData = null;

function avsnitt(liste) {
  return liste.map((t) => `<p>${escapeHtml(t)}</p>`).join("");
}

async function lastKurs() {
  kursData = await hentJson("/api/kurs").catch(() => null);
  if (!kursData) return;
  const kort = $("kursKort");
  kort.classList.remove("hidden");
  const d = kursData.dagens;
  $("kursInnhold").classList.add("hidden");
  if (!d) {
    $("kursDag").textContent = "Minikurs fullført";
    $("kursTittel").textContent = "Du har lest alle 30 leksjonene 🎉";
    $("kursLesBtn").classList.add("hidden");
    return;
  }
  $("kursDag").textContent = kursData.lest_i_dag
    ? `Dag ${d.nr} av ${kursData.totalt} · lest ✓ · ny leksjon i morgen`
    : `Dagens leksjon · dag ${d.nr} av ${kursData.totalt}`;
  $("kursTittel").textContent = d.tittel;
  $("kursTekst").innerHTML = avsnitt(d.tekst);
  $("kursProv").textContent = d.prov;
  $("kursLesBtn").textContent = kursData.lest_i_dag ? "Les igjen" : "Les (2 min)";
  $("kursLesBtn").classList.remove("hidden");
  $("kursFerdigBtn").classList.toggle("hidden", kursData.lest_i_dag);
  kort.classList.toggle("kurs-lest", kursData.lest_i_dag);
}

function apneKursLeksjon() {
  $("kursInnhold").classList.remove("hidden");
  $("kursLesBtn").classList.add("hidden");
}

async function ferdigLest() {
  const btn = $("kursFerdigBtn");
  btn.disabled = true;
  try {
    await postJson("/api/kurs/lest", { nr: kursData.dagens.nr });
    await lastKurs();
  } catch (e) {
    btn.textContent = e.message;
  } finally {
    btn.disabled = false;
  }
}

function apneKursListe() {
  $("kursModalTittel").textContent = "Leksjoner du har lest";
  $("kursModalLeksjon").classList.add("hidden");
  const liste = $("kursListe");
  liste.classList.remove("hidden");
  liste.innerHTML = kursData.leste.length
    ? kursData.leste.map((l) => `<li><button type="button" class="kurs-rad" data-leksjon="${l.nr}"><span>${l.nr}.</span> ${escapeHtml(l.tittel)}</button></li>`).join("")
    : `<li class="tom">Du har ikke lest noen leksjoner ennå. Start med dagens!</li>`;
  $("kursOverlay").classList.remove("hidden");
}

async function visGammelLeksjon(nr) {
  const l = await hentJson(`/api/kurs/leksjon/${nr}`).catch(() => null);
  if (!l) return;
  $("kursModalTittel").textContent = `${l.nr}. ${l.tittel}`;
  $("kursModalTekst").innerHTML = avsnitt(l.tekst);
  $("kursModalProv").textContent = l.prov;
  $("kursListe").classList.add("hidden");
  $("kursModalLeksjon").classList.remove("hidden");
}

// ---- Ukemål ----

let valgtUkemal = null;

function statRute(tall_, tekst) {
  return `<div class="uke-stat-rute"><strong>${tall_}</strong><span>${tekst}</span></div>`;
}

function visUkemal(m, tvingValg = false) {
  if (!m) return;
  const harMal = !!m.mal;
  const visValg = !harMal || tvingValg;
  $("ukemalStrip").classList.toggle("hidden", visValg || m.gjelder === "neste");
  $("ukemalKort").classList.toggle("hidden", !visValg);
  if (harMal) $("ukemalTekst").textContent = m.mal;
  if (!visValg) return;

  $("ukemalTittel").textContent = m.gjelder === "neste" ? "Uka som gikk – og målet for neste uke" : "Velg ukemål for denne uka";
  const st = m.statistikk;
  const stEl = $("ukeStat");
  if (st && st.registrerte_dager > 0) {
    const ruter = [
      statRute(`${st.alkoholfrie_hverdager}/${st.registrerte_hverdager}`, "alkoholfrie hverdager"),
      statRute(st.fastedager, "dager fastet"),
      statRute(st.planlagte_treningsdager ? `${st.treningsdager}/${st.planlagte_treningsdager}` : st.treningsdager, "treningsdager"),
    ];
    if (st.vekt_endring != null) ruter.push(statRute(`${st.vekt_endring > 0 ? "+" : ""}${tall(st.vekt_endring, 1)} kg`, "vekt"));
    else ruter.push(statRute(tall(st.helg_enheter, st.helg_enheter % 1 ? 1 : 0), "enheter i helgen"));
    stEl.innerHTML = ruter.join("");
    stEl.classList.remove("hidden");
  } else {
    stEl.classList.add("hidden");
  }
  valgtUkemal = m.forslag.includes(m.mal) ? m.mal : null;
  $("egetUkemal").value = harMal && !m.forslag.includes(m.mal) ? m.mal : "";
  $("ukemalForslag").innerHTML = m.forslag
    .map((f, i) => `<button type="button" class="plan-valg" aria-pressed="${f === valgtUkemal}" data-ukemal="${i}">${escapeHtml(f)}</button>`)
    .join("");
}

async function lagreUkemal() {
  const m = dagData.ukemal;
  const mal = $("egetUkemal").value.trim() || valgtUkemal;
  const feil = $("ukemalFeil");
  feil.classList.add("hidden");
  if (!mal) {
    feil.textContent = "Trykk på et av forslagene, eller skriv ditt eget mål.";
    feil.classList.remove("hidden");
    return;
  }
  try {
    const r = await postJson("/api/ukemal", { uke_start: m.uke_start, mal });
    m.mal = r.mal;
    visUkemal(m);
  } catch (e) {
    feil.textContent = e.message;
    feil.classList.remove("hidden");
  }
}

async function visVanskelig() {
  const btn = $("vanskeligBtn");
  btn.disabled = true;
  try {
    const r = await postJson("/api/coach/vanskelig");
    $("vanskeligTekst").textContent = r.tekst;
    $("vanskeligKort").classList.remove("hidden");
    $("vanskeligKort").scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (e) {
    $("vanskeligTekst").textContent = "Gå en tur rundt kvartalet i ti minutter, og drikk et stort glass vann.";
    $("vanskeligKort").classList.remove("hidden");
  } finally {
    btn.disabled = false;
  }
}

// ---- Chat ----

function chatBoble(rolle, tekst) {
  const div = document.createElement("div");
  div.className = `chat-boble chat-${rolle === "user" ? "meg" : "coach"}`;
  div.textContent = tekst;
  $("chatLogg").appendChild(div);
  $("chatLogg").scrollTop = $("chatLogg").scrollHeight;
  return div;
}

async function apneChat() {
  $("chatOverlay").classList.remove("hidden");
  $("chatLogg").innerHTML = "";
  const historikk = await hentJson("/api/coach/chat").catch(() => []);
  if (historikk.length === 0) chatBoble("assistant", "Hei! Spør meg om mat, trening, alkohol eller hva som helst du lurer på.");
  historikk.forEach((r) => chatBoble(r.rolle, r.tekst));
  setTimeout(() => $("chatTekst").focus(), 50);
}

function lukkChat() {
  $("chatOverlay").classList.add("hidden");
}

async function sendChat(e) {
  e.preventDefault();
  const tekst = $("chatTekst").value.trim();
  if (!tekst) return;
  $("chatTekst").value = "";
  chatBoble("user", tekst);
  const venter = chatBoble("assistant", "Tenker …");
  venter.classList.add("chat-venter");
  $("chatSendBtn").disabled = true;
  try {
    const r = await postJson("/api/coach/chat", { tekst });
    venter.textContent = r.svar;
  } catch (e) {
    venter.textContent = e.message;
  } finally {
    venter.classList.remove("chat-venter");
    $("chatSendBtn").disabled = false;
  }
}

// ---- Mat ----

let matData = null;

async function lastMat() {
  try {
    matData = await hentJson("/api/mat");
  } catch (e) {
    $("middagListe").innerHTML = `<li class="tom">Fikk ikke hentet menyen. Prøv igjen om litt.</li>`;
    return;
  }
  visMat();
}

const TOMMEL_OPP = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v11"/><path d="M15 5.9 14 10h5.8a2 2 0 0 1 2 2.4l-1.4 7A2 2 0 0 1 18.4 21H7V10l4-8a3 3 0 0 1 4 3.9z"/></svg>';
const TOMMEL_NED = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 14V3"/><path d="M9 18.1 10 14H4.2a2 2 0 0 1-2-2.4l1.4-7A2 2 0 0 1 5.6 3H17v11l-4 8a3 3 0 0 1-4-3.9z"/></svg>';

function vurderingFor(navn) {
  const v = matData.vurderinger || { favoritter: [], unnga: [] };
  const n = navn.toLowerCase();
  if (v.favoritter.some((f) => f.toLowerCase() === n)) return 1;
  if (v.unnga.some((f) => f.toLowerCase() === n)) return -1;
  return 0;
}

function visMat() {
  const iDag = idagDato();
  $("middagListe").innerHTML = matData.middager
    .map((m, i) => {
      const v = vurderingFor(m.navn);
      return `
      <li class="middag-rad${m.dag === iDag ? " middag-idag" : ""}">
        <div class="middag-rad-topp">
          <span class="middag-dag">${kortUkedag(m.dag)}${m.dag === iDag ? " – i dag" : ""}</span>
          <span class="middag-handlinger">
            <button type="button" class="tommel${v === 1 ? " valgt" : ""}" aria-pressed="${v === 1}" aria-label="Liker" data-vurder="1" data-i="${i}">${TOMMEL_OPP}</button>
            <button type="button" class="tommel tommel-ned${v === -1 ? " valgt" : ""}" aria-pressed="${v === -1}" aria-label="Liker ikke" data-vurder="-1" data-i="${i}">${TOMMEL_NED}</button>
            <button type="button" class="lenke-knapp${v === -1 ? " bytt-fremhevet" : ""}" data-bytt="${m.dag}">Bytt</button>
          </span>
        </div>
        <strong class="middag-rad-navn">${escapeHtml(m.navn)}</strong>
        <p class="hint">${m.minutter} min · ${escapeHtml(m.beskrivelse)}</p>
        <details><summary>Ingredienser</summary><ul>${m.ingredienser.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></details>
      </li>`;
    })
    .join("");
  const l = matData.lunsj;
  $("lunsjNavn").textContent = l.navn;
  $("lunsjInfo").textContent = `Lag søndag · ${l.minutter} min`;
  $("lunsjBeskrivelse").textContent = l.beskrivelse;
  $("brodtips").innerHTML = (l.brodtips || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  visPrepSteg();
  visHandleliste();
  visSmak();
  $("kjoleskapBrukBtn").classList.toggle("hidden", !matData.middager.some((m) => m.dag === iDag));
}

function prepNokkel() {
  return `prep-${matData.uke_start}`;
}

function visPrepSteg() {
  const ferdig = hentLokalt(prepNokkel(), []);
  $("prepSteg").innerHTML = (matData.lunsj.steg || [])
    .map((s, i) => `<li><button type="button" class="prep-knapp${ferdig.includes(i) ? " ferdig" : ""}" aria-pressed="${ferdig.includes(i)}" data-steg="${i}">${escapeHtml(s)}</button></li>`)
    .join("");
}

function visSmak() {
  const v = matData.vurderinger || { favoritter: [], unnga: [] };
  $("smakKort").classList.toggle("hidden", !v.favoritter.length && !v.unnga.length);
  const rad = (navn) => `<li><span>${escapeHtml(navn)}</span><button type="button" class="lenke-knapp" data-angre="${escapeHtml(navn)}">Fjern</button></li>`;
  $("favorittBlokk").classList.toggle("hidden", !v.favoritter.length);
  $("unngaBlokk").classList.toggle("hidden", !v.unnga.length);
  $("favorittListe").innerHTML = v.favoritter.map(rad).join("");
  $("unngaListe").innerHTML = v.unnga.map(rad).join("");
}

async function vurder(navn, vurdering) {
  try {
    matData.vurderinger = await postJson("/api/mat/vurder", { navn, vurdering });
    visMat();
  } catch (e) {}
}

let kjoleskapMiddag = null;

async function foreslaFraKjoleskap() {
  const tekst = $("kjoleskapTekst").value.trim();
  const feil = $("kjoleskapFeil");
  feil.classList.add("hidden");
  if (!tekst) {
    feil.textContent = "Skriv hva du har først, f.eks. «egg, skinke og paprika».";
    feil.classList.remove("hidden");
    return;
  }
  const btn = $("kjoleskapBtn");
  btn.disabled = true;
  btn.textContent = "Tenker …";
  try {
    kjoleskapMiddag = await postJson("/api/mat/hva-har-vi", { tekst });
    $("kjoleskapNavn").textContent = kjoleskapMiddag.navn;
    $("kjoleskapInfo").textContent = `${kjoleskapMiddag.minutter} min · ${kjoleskapMiddag.beskrivelse}`;
    $("kjoleskapIngredienser").innerHTML = kjoleskapMiddag.ingredienser.map((x) => `<li>${escapeHtml(x)}</li>`).join("");
    $("kjoleskapBrukBtn").textContent = "Bruk som dagens middag";
    $("kjoleskapBrukBtn").disabled = false;
    $("kjoleskapForslag").classList.remove("hidden");
  } catch (e) {
    feil.textContent = e.message;
    feil.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = "Foreslå middag";
  }
}

async function brukKjoleskapMiddag() {
  if (!kjoleskapMiddag) return;
  const btn = $("kjoleskapBrukBtn");
  btn.disabled = true;
  try {
    matData = await postJson("/api/mat/bruk", { dag: idagDato(), middag: kjoleskapMiddag });
    visMat();
    btn.textContent = "Lagt inn som dagens middag";
  } catch (e) {
    btn.textContent = e.message;
    btn.disabled = false;
  }
}

function handlelisteNokkel() {
  return `handleliste-${matData.uke_start}`;
}

function visHandleliste() {
  const kryss = hentLokalt(handlelisteNokkel(), []);
  $("handleliste").innerHTML = matData.handleliste
    .map((v) => {
      const valgt = kryss.includes(v);
      return `<li><button type="button" class="handle-vare${valgt ? " kjopt" : ""}" aria-pressed="${valgt}" data-vare="${escapeHtml(v)}">${escapeHtml(v)}</button></li>`;
    })
    .join("");
}

async function byttMiddag(dag, btn) {
  btn.disabled = true;
  btn.textContent = "Finner ny …";
  try {
    matData = await postJson("/api/mat/bytt", { dag });
    visMat();
  } catch (e) {
    btn.textContent = "Prøv igjen";
    btn.disabled = false;
  }
}

// ---- Varsler ----

function base64TilBytes(b64) {
  const padding = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

function stotterPush() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

async function oppdaterVarselKort() {
  const kort = $("varselKort");
  if (!stotterPush()) {
    $("varselHint").textContent = "Åpne appen fra ikonet på hjemskjermen for å få varsler.";
    $("slaPaVarslerBtn").classList.add("hidden");
    kort.classList.remove("hidden");
    return;
  }
  if (Notification.permission === "granted") {
    const reg = await navigator.serviceWorker.getRegistration("/");
    const sub = reg && (await reg.pushManager.getSubscription());
    kort.classList.toggle("hidden", !!sub);
    return;
  }
  if (Notification.permission === "denied") {
    $("varselHint").textContent = "Varsler er skrudd av. Slå dem på under Innstillinger → Varslinger → Superhuman på iPhonen.";
    $("slaPaVarslerBtn").classList.add("hidden");
  }
  kort.classList.remove("hidden");
}

async function slaPaVarsler() {
  const btn = $("slaPaVarslerBtn");
  btn.disabled = true;
  try {
    const tillatelse = await Notification.requestPermission();
    if (tillatelse !== "granted") throw new Error("Du må trykke «Tillat» for å få varsler.");
    const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    await navigator.serviceWorker.ready;
    const { offentlig } = await hentJson("/api/push/nokkel");
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: base64TilBytes(offentlig) });
    await postJson("/api/push/abonner", sub.toJSON());
    await postJson("/api/push/test");
    $("varselKort").classList.add("hidden");
  } catch (e) {
    $("varselHint").textContent = e.message || "Klarte ikke å slå på varsler. Prøv igjen.";
  } finally {
    btn.disabled = false;
  }
}

async function apneTider() {
  const tider = await hentJson("/api/innstillinger/varsler").catch(() => null);
  if (!tider) return;
  const form = $("tiderForm");
  Object.entries(tider).forEach(([k, v]) => {
    if (form.elements[k]) form.elements[k].value = v;
  });
  $("tiderFeil").classList.add("hidden");
  $("tiderOverlay").classList.remove("hidden");
}

async function lagreTider(e) {
  e.preventDefault();
  const form = $("tiderForm");
  const data = Object.fromEntries(["morgen", "middag", "helg", "kveld", "sondag", "risiko"].map((k) => [k, form.elements[k].value]));
  try {
    await postJson("/api/innstillinger/varsler", data);
    $("tiderOverlay").classList.add("hidden");
  } catch (err) {
    $("tiderFeil").textContent = err.message;
    $("tiderFeil").classList.remove("hidden");
  }
}

async function sendTestvarsel() {
  const btn = $("testVarselBtn");
  btn.disabled = true;
  try {
    const r = await postJson("/api/push/test");
    btn.textContent = r.sendt ? "Sendt!" : "Ingen telefon koblet til";
  } catch (e) {
    btn.textContent = "Feilet";
  }
  setTimeout(() => {
    btn.textContent = "Send testvarsel";
    btn.disabled = false;
  }, 2500);
}

function formaterDato(isoDato) {
  const [aar, mnd, dag] = isoDato.split("-");
  return `${dag}.${mnd}.${aar}`;
}

// ---- Oversikt (samlet dashboard) ----

let oversiktDagerValgt = 30;

const OVERSIKT_META = {
  vekt: {
    navn: "Vekt", kilde: "withings", kobleUrl: "/withings/connect", kobleNavn: "Withings",
    ikon: '<path d="M6 6v12"/><path d="M18 6v12"/><path d="M9 12h6"/><rect x="3" y="9" width="3" height="6" rx="1"/><rect x="18" y="9" width="3" height="6" rx="1"/>',
  },
  sovn: {
    navn: "Søvn", kilde: "oura", kobleUrl: "/oura/connect", kobleNavn: "Oura",
    ikon: '<path d="M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9z"/>',
  },
  restitusjon: {
    navn: "Restitusjon", kilde: "oura", kobleUrl: "/oura/connect", kobleNavn: "Oura",
    ikon: '<path d="M20.8 4.6a4.8 4.8 0 0 0-7 0L12 6.4l-1.8-1.8a4.8 4.8 0 0 0-7 6.6L12 20l8.8-8.8a4.8 4.8 0 0 0 0-6.6z"/>',
  },
  aktivitet: {
    navn: "Aktivitet", kilde: "oura", kobleUrl: "/oura/connect", kobleNavn: "Oura",
    ikon: '<path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z"/>',
  },
};

async function lastOversikt() {
  const res = await fetch(`/api/oversikt?dager=${oversiktDagerValgt}`);
  const data = await res.json();
  renderTreningUke(data.trening_uke, data.alkoholfri_rekke);
  renderOversiktKort(data.kort, data.tilkoblinger);
  renderInnsikt(data.innsikt);
}

function renderTreningUke(uke, alkoholfriRekke) {
  const antall = uke.filter((d) => d.gjennomfort === true).length;
  $("treningUkeAntall").textContent = `${antall} av ${uke.length} dager trent`;
  const iDag = idagDato();
  $("treningUkeStrip").innerHTML = uke
    .map((d) => {
      let status = "ikke-logget";
      if (d.gjennomfort === true) status = "gjort";
      else if (d.gjennomfort === false) status = "ikke-gjort";
      const idagKlasse = d.dato === iDag ? " trening-dag-idag" : "";
      return `<div class="trening-dag trening-dag-${status}${idagKlasse}" title="${formaterDato(d.dato)}"><span>${escapeHtml(d.ukedag_kort)}</span></div>`;
    })
    .join("");

  const rekkeEl = $("streakTekst");
  if (alkoholfriRekke >= 1) {
    rekkeEl.textContent = `${alkoholfriRekke} alkoholfri${alkoholfriRekke === 1 ? "" : "e"} hverdag${alkoholfriRekke === 1 ? "" : "er"} på rad`;
    rekkeEl.classList.remove("hidden");
  } else {
    rekkeEl.classList.add("hidden");
  }
}

function renderInnsikt(innsikt) {
  const kort = $("innsiktCard");
  if (!innsikt || !innsikt.nok_data) {
    kort.classList.add("hidden");
    return;
  }
  const fmt = (v) => `${v > 0 ? "+" : ""}${v.toFixed(1).replace(".", ",")} kg`;
  $("innsiktTekst").textContent =
    `I uker med minst 5 alkoholfrie dager (${innsikt.uker_hoy} uker) endret vekten seg i snitt ${fmt(innsikt.snitt_delta_hoy)}, ` +
    `mot ${fmt(innsikt.snitt_delta_lav)} i ukene med færre (${innsikt.uker_lav} uker).`;
  kort.classList.remove("hidden");
}

function malFremgangHtml(mal) {
  if (!mal) return "";
  const fmt1 = (v) => v.toFixed(1).replace(".", ",");
  const fortsattTekst =
    mal.gjenstaende_kg > 0
      ? `${fmt1(mal.gjenstaende_kg)} kg igjen til ${fmt1(mal.mal_vekt_kg)} kg`
      : `Målet på ${fmt1(mal.mal_vekt_kg)} kg er nådd!`;
  const prosentTekst = mal.prosent_fullfort != null ? ` · ${mal.prosent_fullfort}% av veien` : "";
  const datoTekst = mal.projisert_dato ? ` · ca. ${formaterDato(mal.projisert_dato)} i dagens tempo` : "";
  return `<p class="oversikt-kort-hint oversikt-mal-tekst">${fortsattTekst}${prosentTekst}${datoTekst}</p>`;
}

function renderOversiktKort(kortListe, tilkoblinger) {
  const container = $("oversiktKort");

  container.innerHTML = kortListe
    .map((k, i) => {
      const meta = OVERSIKT_META[k.id];
      const fargeVar = `--metrikk-${k.id}`;
      const ikonSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${meta.ikon}</svg>`;
      const stil = `style="--kort-forsinkelse:${i * 70}ms"`;
      const erVekt = k.id === "vekt";
      const kildeStatus = tilkoblinger[meta.kilde] || { tilkoblet: false, advarsel: false, melding: null };

      // Søvn/restitusjon/aktivitet kommer bare fra Oura og vises helt
      // frakoblet inntil man kobler til. Vekt kan alltid registreres
      // manuelt, så det kortet skal aldri gjemmes bak en tilkobling.
      if (!kildeStatus.tilkoblet && !erVekt) {
        return `
        <div class="oversikt-kort oversikt-kort-frakoblet" ${stil}>
          <div class="oversikt-kort-header">
            <div class="oversikt-kort-ikon" style="color:var(${fargeVar})">${ikonSvg}</div>
            <div class="oversikt-kort-titler"><h3>${meta.navn}</h3></div>
          </div>
          <div class="oversikt-frakoblet-boks">
            <p class="hint">Koble til ${meta.kobleNavn} for å se ${meta.navn.toLowerCase()} her.</p>
            <a href="${meta.kobleUrl}" class="btn">Koble til ${meta.kobleNavn}</a>
          </div>
        </div>`;
      }

      const harData = k.siste !== null;
      const advarselHtml = kildeStatus.tilkoblet && kildeStatus.advarsel
        ? `<p class="oversikt-kort-advarsel">OBS: ${escapeHtml(kildeStatus.melding || "Synkroniseringen har stoppet opp.")}</p>`
        : "";
      const koblingHint = erVekt && !kildeStatus.tilkoblet
        ? `<p class="oversikt-kort-hint">Ikke koblet til Withings - <a href="${meta.kobleUrl}">koble til</a> for å hente vekten automatisk.</p>`
        : "";
      const vektVerktoyHtml = erVekt
        ? `
        <div class="vekt-verktoy">
          <button type="button" class="lenke-knapp" data-vekt-handling="legg-til">+ Registrer vekt</button>
          <button type="button" class="lenke-knapp" data-vekt-handling="mal">Sett målvekt</button>
          <button type="button" class="lenke-knapp" data-vekt-handling="liste">Vis alle registreringer</button>
          ${k.sekundaer.length ? `<button type="button" class="lenke-knapp" data-vekt-handling="detaljer">Se utvikling i fett, muskler m.m.</button>` : ""}
        </div>
        <div class="vekt-inline-boks hidden" data-vekt-boks="legg-til">
          <form class="inline-form" data-vekt-form="legg-til">
            <label>Dato<input type="date" data-vekt-felt="dato" required /></label>
            <label>Vekt (kg)<input type="text" data-vekt-felt="vekt" inputmode="decimal" placeholder="F.eks. 92,4" required /></label>
            <button type="submit" class="btn primary">Lagre</button>
          </form>
        </div>
        <div class="vekt-inline-boks hidden" data-vekt-boks="mal">
          <form class="inline-form" data-vekt-form="mal">
            <label>Målvekt (kg)<input type="text" data-vekt-felt="mal" inputmode="decimal" placeholder="F.eks. 85" value="${k.mal ? k.mal.mal_vekt_kg.toString().replace(".", ",") : ""}" /></label>
            <button type="submit" class="btn primary">Lagre</button>
          </form>
        </div>
        <ul class="vekt-liste hidden" data-vekt-liste></ul>
      `
        : "";

      if (!harData) {
        return `
        <div class="oversikt-kort" ${stil} data-kort="${k.id}">
          <div class="oversikt-kort-header">
            <div class="oversikt-kort-ikon" style="color:var(${fargeVar})">${ikonSvg}</div>
            <div class="oversikt-kort-titler"><h3>${meta.navn}</h3></div>
          </div>
          <p class="hint">${erVekt ? "Ingen vekt registrert ennå." : "Ingen data ennå. Trykk synk-knappen øverst for å hente."}</p>
          ${koblingHint}
          ${vektVerktoyHtml}
        </div>`;
      }

      const desimaler = k.enhet === "kg" || k.enhet === "%" ? 1 : 0;
      const deltaHtml =
        k.delta_7d == null || k.delta_7d === 0
          ? ""
          : `<span class="oversikt-kort-delta ${k.delta_7d > 0 ? "opp" : "ned"}">${k.delta_7d > 0 ? "↑" : "↓"} ${Math.abs(k.delta_7d).toFixed(desimaler).replace(".", ",")}${k.enhet}</span>`;
      const sekundaerHtml = k.sekundaer.length
        ? `<div class="oversikt-kort-sekundaer-rad">${k.sekundaer
            .map(
              (s) =>
                `<span class="badge">${escapeHtml(s.navn)}: ${s.verdi.toString().replace(".", ",")}${s.enhet ? " " + escapeHtml(s.enhet) : ""}</span>`
            )
            .join("")}</div>`
        : "";
      const sekundaerHint =
        erVekt && k.sekundaer.length
          ? `<p class="oversikt-kort-hint">Fettmasse + muskelmasse + beinmasse ≈ vekten. Kroppsvann overlapper med disse (ligger allerede inni fett- og muskelmassen), så det skal ikke legges til.</p>`
          : "";
      const malHtml = erVekt ? malFremgangHtml(k.mal) : "";

      return `
        <div class="oversikt-kort" ${stil} data-kort="${k.id}">
          <div class="oversikt-kort-header">
            <div class="oversikt-kort-ikon" style="color:var(${fargeVar})">${ikonSvg}</div>
            <div class="oversikt-kort-titler">
              <h3>${meta.navn}</h3>
            </div>
            <div class="oversikt-kort-verdi-blokk">
              <span class="oversikt-kort-verdi" data-til="${k.siste}" data-desimaler="${desimaler}">0</span><span class="oversikt-kort-enhet">${escapeHtml(k.enhet)}</span>
              ${deltaHtml}
            </div>
          </div>
          ${sekundaerHtml}
          ${sekundaerHint}
          ${malHtml}
          ${advarselHtml}
          <div class="oversikt-graf-wrap">
            <div class="graf-tooltip"></div>
          </div>
          ${koblingHint}
          ${vektVerktoyHtml}
        </div>`;
    })
    .join("");

  kortListe.forEach((k) => {
    const kortEl = container.querySelector(`[data-kort="${k.id}"]`);
    if (!kortEl) return;
    const verdiEl = kortEl.querySelector(".oversikt-kort-verdi");
    if (verdiEl) {
      tellOpp(verdiEl, Number(verdiEl.dataset.til), Number(verdiEl.dataset.desimaler));
      tegnGraf(kortEl.querySelector(".oversikt-graf-wrap"), k.serie, `--metrikk-${k.id}`, k.id === "vekt");
    }
    if (k.id === "vekt") settOppVektVerktoy(kortEl);
  });
}

function settOppVektVerktoy(kortEl) {
  const knapper = kortEl.querySelectorAll("[data-vekt-handling]");
  if (knapper.length === 0) return;

  const datoFelt = kortEl.querySelector('[data-vekt-felt="dato"]');
  if (datoFelt) datoFelt.value = idagDato();

  const boksFor = {
    "legg-til": kortEl.querySelector('[data-vekt-boks="legg-til"]'),
    mal: kortEl.querySelector('[data-vekt-boks="mal"]'),
  };
  const listeEl = kortEl.querySelector("[data-vekt-liste]");

  knapper.forEach((knapp) => {
    knapp.addEventListener("click", async () => {
      const valg = knapp.dataset.vektHandling;
      if (valg === "detaljer") {
        apneVektDetaljModal();
        return;
      }
      if (valg === "liste") {
        const skjult = listeEl.classList.contains("hidden");
        if (skjult) await lastVektListe(listeEl);
        listeEl.classList.toggle("hidden");
        return;
      }
      const andreBoks = valg === "legg-til" ? boksFor.mal : boksFor["legg-til"];
      andreBoks.classList.add("hidden");
      boksFor[valg].classList.toggle("hidden");
    });
  });

  const leggTilForm = kortEl.querySelector('[data-vekt-form="legg-til"]');
  leggTilForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {
      dato: leggTilForm.querySelector('[data-vekt-felt="dato"]').value,
      vekt_kg: leggTilForm.querySelector('[data-vekt-felt="vekt"]').value,
    };
    const res = await fetch("/api/vekt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) lastOversikt();
  });

  const malForm = kortEl.querySelector('[data-vekt-form="mal"]');
  malForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const verdi = malForm.querySelector('[data-vekt-felt="mal"]').value;
    await fetch("/api/mal-vekt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mal_vekt_kg: verdi }),
    });
    lastOversikt();
  });
}

async function lastVektListe(listeEl) {
  const res = await fetch("/api/vekt");
  const data = await res.json();
  if (data.length === 0) {
    listeEl.innerHTML = `<li class="tom">Ingen vekt registrert ennå.</li>`;
    return;
  }
  listeEl.innerHTML = [...data]
    .reverse()
    .map(
      (v) => `
      <li>
        <span>${formaterDato(v.dato)}</span>
        <strong>${v.vekt_kg.toString().replace(".", ",")} kg</strong>
        <button type="button" class="slett-lenke" data-id="${v.id}">Slett</button>
      </li>`
    )
    .join("");
  listeEl.querySelectorAll(".slett-lenke").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetch(`/api/vekt/${btn.dataset.id}`, { method: "DELETE" });
      lastOversikt();
    });
  });
}

// Fargevariabel per Withings måletype-id (se WITHINGS_MALETYPER i app.py).
const VEKT_DETALJ_FARGE = {
  6: "--metrikk-fett", // Fettprosent
  8: "--metrikk-fett", // Fettmasse
  76: "--metrikk-muskel", // Muskelmasse
  77: "--metrikk-vann", // Kroppsvann
  88: "--metrikk-bein", // Beinmasse
  11: "--metrikk-puls", // Puls
};

async function apneVektDetaljModal() {
  $("vektDetaljModalOverlay").classList.remove("hidden");
  const listeEl = $("vektDetaljListe");
  listeEl.innerHTML = `<p class="hint">Laster …</p>`;
  const res = await fetch(`/api/vekt-detaljer?dager=${oversiktDagerValgt}`);
  const metrikker = await res.json();
  renderVektDetaljListe(metrikker);
}

function lukkVektDetaljModal() {
  $("vektDetaljModalOverlay").classList.add("hidden");
}

function renderVektDetaljListe(metrikker) {
  const listeEl = $("vektDetaljListe");
  if (metrikker.length === 0) {
    listeEl.innerHTML = `<p class="hint">Ingen andre målinger fra Withings-vekten i denne perioden ennå.</p>`;
    return;
  }

  listeEl.innerHTML = metrikker
    .map((m) => {
      const desimaler = m.enhet === "kg" || m.enhet === "%" ? 1 : 0;
      const deltaHtml =
        m.delta_7d == null || m.delta_7d === 0
          ? ""
          : `<span class="oversikt-kort-delta ${m.delta_7d > 0 ? "opp" : "ned"}">${m.delta_7d > 0 ? "↑" : "↓"} ${Math.abs(m.delta_7d).toFixed(desimaler).replace(".", ",")}${m.enhet}</span>`;
      return `
      <div class="vekt-detalj-kort" data-vekt-detalj="${m.id}">
        <div class="oversikt-kort-header">
          <div class="oversikt-kort-titler"><h3>${escapeHtml(m.navn)}</h3></div>
          <div class="oversikt-kort-verdi-blokk">
            <span>${m.siste.toString().replace(".", ",")}</span><span class="oversikt-kort-enhet">${escapeHtml(m.enhet)}</span>
            ${deltaHtml}
          </div>
        </div>
        <div class="oversikt-graf-wrap">
          <div class="graf-tooltip"></div>
        </div>
      </div>`;
    })
    .join("");

  metrikker.forEach((m) => {
    const kortEl = listeEl.querySelector(`[data-vekt-detalj="${m.id}"]`);
    if (!kortEl) return;
    tegnGraf(kortEl.querySelector(".oversikt-graf-wrap"), m.serie, VEKT_DETALJ_FARGE[m.id] || "--metrikk-vekt", true);
  });
}

function tellOpp(el, tilVerdi, desimaler) {
  const varighet = 800;
  const start = performance.now();
  function steg(naa) {
    const t = Math.min((naa - start) / varighet, 1);
    const glidning = 1 - Math.pow(1 - t, 3);
    el.textContent = (tilVerdi * glidning).toFixed(desimaler).replace(".", ",");
    if (t < 1) requestAnimationFrame(steg);
  }
  requestAnimationFrame(steg);
}

const GRAF_B = 300;
const GRAF_H = 84;
const GRAF_PAD = 6;

function glattSti(punkter) {
  if (punkter.length < 2) return "";
  let d = `M ${punkter[0][0]},${punkter[0][1]}`;
  for (let i = 0; i < punkter.length - 1; i++) {
    const p0 = punkter[i === 0 ? 0 : i - 1];
    const p1 = punkter[i];
    const p2 = punkter[i + 1];
    const p3 = punkter[i + 2 < punkter.length ? i + 2 : i + 1];
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C ${c1x.toFixed(2)},${c1y.toFixed(2)} ${c2x.toFixed(2)},${c2y.toFixed(2)} ${p2[0].toFixed(2)},${p2[1].toFixed(2)}`;
  }
  return d;
}

function tegnGraf(wrapEl, serie, fargeVar, visSnitt) {
  const eksisterendeTooltip = wrapEl.querySelector(".graf-tooltip");
  wrapEl.innerHTML = "";
  if (eksisterendeTooltip) wrapEl.appendChild(eksisterendeTooltip);
  else wrapEl.insertAdjacentHTML("beforeend", '<div class="graf-tooltip"></div>');

  if (serie.length < 2) {
    wrapEl.insertAdjacentHTML(
      "beforeend",
      `<p class="graf-tom">${serie.length === 1 ? "Bare én måling i denne perioden" : "Ingen data i denne perioden"}</p>`
    );
    return;
  }

  const tider = serie.map((p) => new Date(p.dato).getTime());
  const verdier = serie.map((p) => p.verdi);
  const tMin = Math.min(...tider);
  const tMax = Math.max(...tider);
  const vMin = Math.min(...verdier);
  const vMax = Math.max(...verdier);
  const vSpenn = (vMax - vMin) || 1;
  const vPad = vSpenn * 0.15;

  const xSkala = (t) => (tMax === tMin ? GRAF_B / 2 : GRAF_PAD + ((t - tMin) / (tMax - tMin)) * (GRAF_B - GRAF_PAD * 2));
  const ySkala = (v) => GRAF_H - GRAF_PAD - ((v - (vMin - vPad)) / (vSpenn + vPad * 2)) * (GRAF_H - GRAF_PAD * 2);

  const punkter = serie.map((p) => [xSkala(new Date(p.dato).getTime()), ySkala(p.verdi)]);
  const linjeSti = glattSti(punkter);
  const arealSti = `${linjeSti} L ${punkter[punkter.length - 1][0].toFixed(2)},${GRAF_H} L ${punkter[0][0].toFixed(2)},${GRAF_H} Z`;
  const gradId = `grad-${Math.random().toString(36).slice(2, 9)}`;
  const siste = punkter[punkter.length - 1];

  // Daglige målinger (spesielt vekt) hopper naturlig litt opp og ned - når
  // visSnitt er på tegnes et jevnere 7-dagers glidende snitt oppå de rå
  // punktene, og selve rålinjen dempes så snittet blir det øyet fanger først.
  const harSnitt = !!visSnitt && serie.some((p) => p.snitt != null);
  const snittSti = harSnitt
    ? glattSti(serie.map((p) => [xSkala(new Date(p.dato).getTime()), ySkala(p.snitt)]))
    : "";

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${GRAF_B} ${GRAF_H}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.classList.add("oversikt-graf-svg");
  svg.innerHTML = `
    <defs>
      <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(${fargeVar})" stop-opacity="0.28" />
        <stop offset="100%" stop-color="var(${fargeVar})" stop-opacity="0" />
      </linearGradient>
    </defs>
    <path d="${arealSti}" fill="url(#${gradId})" stroke="none" class="graf-areal"></path>
    <path d="${linjeSti}" fill="none" stroke="var(${fargeVar})" stroke-width="${harSnitt ? 1.5 : 2}" stroke-linecap="round" stroke-linejoin="round" opacity="${harSnitt ? 0.35 : 1}" class="graf-linje"></path>
    ${harSnitt ? `<path d="${snittSti}" fill="none" stroke="var(${fargeVar})" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="graf-snitt-linje"></path>` : ""}
    <circle cx="${siste[0].toFixed(2)}" cy="${siste[1].toFixed(2)}" r="3.5" fill="var(${fargeVar})" class="graf-siste-punkt"></circle>
    <line class="graf-krysshar" x1="0" y1="0" x2="0" y2="${GRAF_H}" opacity="0"></line>
    <circle class="graf-hover-punkt" r="4" fill="var(${fargeVar})" opacity="0"></circle>
  `;
  wrapEl.insertBefore(svg, wrapEl.firstChild);

  const linje = svg.querySelector(".graf-linje");
  const lengde = linje.getTotalLength();
  linje.style.strokeDasharray = `${lengde}`;
  linje.style.strokeDashoffset = `${lengde}`;
  linje.getBoundingClientRect();
  requestAnimationFrame(() => {
    linje.style.transition = "stroke-dashoffset 900ms cubic-bezier(.22,1,.36,1)";
    linje.style.strokeDashoffset = "0";
  });

  const areal = svg.querySelector(".graf-areal");
  areal.style.opacity = "0";
  requestAnimationFrame(() => {
    areal.style.transition = "opacity 700ms ease 250ms";
    areal.style.opacity = "1";
  });

  const sistePunkt = svg.querySelector(".graf-siste-punkt");
  sistePunkt.style.opacity = "0";
  requestAnimationFrame(() => {
    sistePunkt.style.transition = "opacity 300ms ease 850ms";
    sistePunkt.style.opacity = "1";
  });

  const tooltip = wrapEl.querySelector(".graf-tooltip");
  const krysshar = svg.querySelector(".graf-krysshar");
  const hoverPunkt = svg.querySelector(".graf-hover-punkt");

  function visNaermeste(clientX) {
    const rect = svg.getBoundingClientRect();
    const relX = ((clientX - rect.left) / rect.width) * GRAF_B;
    let naermest = 0;
    let minAvstand = Infinity;
    punkter.forEach((p, i) => {
      const avstand = Math.abs(p[0] - relX);
      if (avstand < minAvstand) { minAvstand = avstand; naermest = i; }
    });
    const p = punkter[naermest];
    const rad = serie[naermest];
    krysshar.setAttribute("x1", p[0]);
    krysshar.setAttribute("x2", p[0]);
    krysshar.setAttribute("opacity", "1");
    hoverPunkt.setAttribute("cx", p[0]);
    hoverPunkt.setAttribute("cy", p[1]);
    hoverPunkt.setAttribute("opacity", "1");
    tooltip.innerHTML = `<strong>${rad.verdi.toString().replace(".", ",")}</strong><span>${formaterDato(rad.dato)}</span>`;
    tooltip.classList.add("synlig");
    const tooltipProsent = Math.min(Math.max((p[0] / GRAF_B) * 100, 18), 82);
    tooltip.style.left = `${tooltipProsent}%`;
  }
  function skjulTooltip() {
    krysshar.setAttribute("opacity", "0");
    hoverPunkt.setAttribute("opacity", "0");
    tooltip.classList.remove("synlig");
  }

  svg.addEventListener("pointermove", (e) => visNaermeste(e.clientX));
  svg.addEventListener("pointerdown", (e) => visNaermeste(e.clientX));
  svg.addEventListener("pointerleave", skjulTooltip);
  svg.addEventListener("pointerup", () => setTimeout(skjulTooltip, 1500));
}

async function synkroniserAlt() {
  const btn = $("oversiktSynkBtn");
  btn.classList.add("roterer");
  btn.disabled = true;
  await Promise.all([
    fetch("/api/withings/synk", { method: "POST" }).catch(() => null),
    fetch("/api/oura/synk", { method: "POST" }).catch(() => null),
  ]);
  await lastOversikt();
  btn.classList.remove("roterer");
  btn.disabled = false;
}

// ---- Historikk ----

const MERKER = [
  ["fastet", "Fastet"],
  ["alkohol", "Alkohol"],
  ["trent", "Trent"],
  ["syk", "Syk"],
];

async function lastHistorikk() {
  const data = await hentJson("/api/historikk").catch(() => null);
  if (!data) return;
  const s = data.stats;
  $("historikkStats").innerHTML = `
    <div class="stat-tile"><strong>${s.alkoholfrie_hverdager_prosent}%</strong><span>alkoholfrie hverdager</span></div>
    <div class="stat-tile"><strong>${s.treningsdager}</strong><span>treningsdager</span></div>
    <div class="stat-tile"><strong>${s.fastedager}</strong><span>fastedager</span></div>
  `;
  const statsHint = document.querySelector("#tab-historikk .card h2");
  if (statsHint) statsHint.textContent = "Siste 30 dager";

  const liste = $("historikkListe");
  if (data.dager.length === 0) {
    liste.innerHTML = `<li class="tom">Ingen dager registrert ennå. Kryss av under «I dag» for å komme i gang.</li>`;
    return;
  }
  liste.innerHTML = data.dager
    .map((d) => {
      const merker = MERKER.filter(([k]) => d[k])
        .map(([k, navn]) => {
          const tekst = k === "alkohol" && d.alkohol_enheter ? `${navn} (${String(d.alkohol_enheter).replace(".", ",")})` : navn;
          return `<span class="merke merke-${k}">${tekst}</span>`;
        })
        .join("");
      return `
        <li class="historikk-rad">
          <div class="historikk-rad-header">
            <span class="historikk-dato">${formaterDato(d.dato)} · ${d.ukedag_navn}</span>
            ${sisteIdag && d.dato >= flyttDato(sisteIdag, -MAKS_DAGER_TILBAKE) ? `<button type="button" class="lenke-knapp" data-endre-dag="${d.dato}">Endre</button>` : ""}
          </div>
          <div class="merke-rad">${merker || '<span class="merke merke-ingen">Ingen avkrysning</span>'}</div>
          ${d.notat ? `<div class="historikk-notater">${escapeHtml(d.notat)}</div>` : ""}
        </li>`;
    })
    .join("");
}

function escapeHtml(tekst) {
  // Trygg både i tekst og inne i attributter (data-…="…"): anførselstegn må også kodes.
  return (tekst == null ? "" : String(tekst))
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ---- Oppstart ----

function lukkVedKlikkUtenfor(id, lukk) {
  $(id).addEventListener("click", (e) => {
    if (e.target.id === id) lukk();
  });
}

function main() {
  settOppFaner();

  document.querySelectorAll("#sjekkGrid .sjekk-rute").forEach((btn) => {
    btn.addEventListener("click", () => veksleSjekk(btn.dataset.felt));
  });
  $("alkoholEnheter").addEventListener("change", () => {
    sjekk.alkohol_enheter = $("alkoholEnheter").value.trim();
    lagreSjekk();
  });
  $("sjekkNotat").addEventListener("blur", () => {
    if ($("sjekkNotat").value.trim() === sjekk.notat) return;
    sjekk.notat = $("sjekkNotat").value.trim();
    lagreSjekk();
  });

  $("helgLagreBtn").addEventListener("click", lagreHelg);
  $("utgangspunktLagreBtn").addEventListener("click", lagreUtgangspunkt);
  $("spartEndreBtn").addEventListener("click", () => {
    const u = innsiktData && innsiktData.utgangspunkt;
    if (u) {
      $("utgangspunktEnheter").value = String(u.enheter_per_uke).replace(".", ",");
      $("utgangspunktKr").value = String(u.kr_per_enhet).replace(".", ",");
    }
    $("spartSkjema").classList.remove("hidden");
    $("spartVisning").classList.add("hidden");
  });
  $("helgEndreBtn").addEventListener("click", () => {
    $("helgEnheter").value = dagData.helg.planlagte_enheter;
    $("helgSluttid").value = dagData.helg.sluttid || "22:00";
    $("helgSkjema").classList.remove("hidden");
    $("helgVisning").classList.add("hidden");
  });
  $("plussEnhetBtn").addEventListener("click", () => endreEnhet(1));
  $("kursLesBtn").addEventListener("click", apneKursLeksjon);
  $("kursFerdigBtn").addEventListener("click", ferdigLest);
  $("kursAlleBtn").addEventListener("click", apneKursListe);
  $("kursLukkBtn").addEventListener("click", () => $("kursOverlay").classList.add("hidden"));
  $("kursTilbakeBtn").addEventListener("click", apneKursListe);
  lukkVedKlikkUtenfor("kursOverlay", () => $("kursOverlay").classList.add("hidden"));
  $("kursListe").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-leksjon]");
    if (btn) visGammelLeksjon(Number(btn.dataset.leksjon));
  });
  $("forrigeDagBtn").addEventListener("click", () => velgDato(flyttDato(valgtDato, -1)));
  $("nesteDagBtn").addEventListener("click", () => velgDato(flyttDato(valgtDato, 1)));
  $("historikkListe").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-endre-dag]");
    if (!btn) return;
    visFane("idag");
    velgDato(btn.dataset.endreDag);
    setTimeout(() => $("sjekkKort").scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  });
  $("ukemalLagreBtn").addEventListener("click", lagreUkemal);
  $("ukemalEndreBtn").addEventListener("click", () => visUkemal(dagData.ukemal, true));
  $("egetUkemal").addEventListener("input", () => {
    if ($("egetUkemal").value.trim()) {
      valgtUkemal = null;
      document.querySelectorAll("#ukemalForslag .plan-valg").forEach((b) => b.setAttribute("aria-pressed", "false"));
    }
  });
  $("ukemalForslag").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-ukemal]");
    if (!btn) return;
    valgtUkemal = dagData.ukemal.forslag[Number(btn.dataset.ukemal)];
    $("egetUkemal").value = "";
    document.querySelectorAll("#ukemalForslag .plan-valg").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
  });
  $("minusEnhetBtn").addEventListener("click", () => endreEnhet(-1));
  $("planerLagreBtn").addEventListener("click", lagrePlaner);
  $("planForslag").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-plan]");
    if (!btn) return;
    const plan = planForslag[Number(btn.dataset.plan)];
    valgtePlaner.has(plan) ? valgtePlaner.delete(plan) : valgtePlaner.add(plan);
    btn.setAttribute("aria-pressed", valgtePlaner.has(plan));
  });
  $("vanskeligBtn").addEventListener("click", visVanskelig);
  $("vanskeligLukk").addEventListener("click", () => $("vanskeligKort").classList.add("hidden"));
  $("middagKort").addEventListener("click", () => visFane("mat"));

  $("sporCoachBtn").addEventListener("click", apneChat);
  $("chatLukkBtn").addEventListener("click", lukkChat);
  $("chatForm").addEventListener("submit", sendChat);
  lukkVedKlikkUtenfor("chatOverlay", lukkChat);

  $("slaPaVarslerBtn").addEventListener("click", slaPaVarsler);
  $("varseltiderBtn").addEventListener("click", apneTider);
  $("tiderForm").addEventListener("submit", lagreTider);
  $("tiderAvbryt").addEventListener("click", () => $("tiderOverlay").classList.add("hidden"));
  $("testVarselBtn").addEventListener("click", sendTestvarsel);
  lukkVedKlikkUtenfor("tiderOverlay", () => $("tiderOverlay").classList.add("hidden"));

  $("middagListe").addEventListener("click", (e) => {
    const bytt = e.target.closest("[data-bytt]");
    if (bytt) return byttMiddag(bytt.dataset.bytt, bytt);
    const tommel = e.target.closest("[data-vurder]");
    if (tommel) {
      const m = matData.middager[Number(tommel.dataset.i)];
      const ny = Number(tommel.dataset.vurder);
      vurder(m.navn, vurderingFor(m.navn) === ny ? 0 : ny);
    }
  });
  $("kjoleskapBtn").addEventListener("click", foreslaFraKjoleskap);
  $("kjoleskapBrukBtn").addEventListener("click", brukKjoleskapMiddag);
  $("prepSteg").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-steg]");
    if (!btn) return;
    const ferdig = new Set(hentLokalt(prepNokkel(), []));
    const i = Number(btn.dataset.steg);
    ferdig.has(i) ? ferdig.delete(i) : ferdig.add(i);
    lagreLokalt(prepNokkel(), [...ferdig]);
    visPrepSteg();
  });
  $("smakKort").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-angre]");
    if (btn) vurder(btn.dataset.angre, 0);
  });
  $("handleliste").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-vare]");
    if (!btn) return;
    const kryss = new Set(hentLokalt(handlelisteNokkel(), []));
    const vare = btn.dataset.vare;
    kryss.has(vare) ? kryss.delete(vare) : kryss.add(vare);
    lagreLokalt(handlelisteNokkel(), [...kryss]);
    visHandleliste();
  });
  $("nullstillHandleliste").addEventListener("click", () => {
    lagreLokalt(handlelisteNokkel(), []);
    visHandleliste();
  });

  $("oversiktSynkBtn").addEventListener("click", synkroniserAlt);
  document.querySelectorAll("#rangeToggle .segment").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#rangeToggle .segment").forEach((b) => b.classList.remove("segment-valgt"));
      btn.classList.add("segment-valgt");
      oversiktDagerValgt = parseInt(btn.dataset.dager, 10);
      lastOversikt();
    });
  });
  $("vektDetaljLukkBtn").addEventListener("click", lukkVektDetaljModal);
  lukkVedKlikkUtenfor("vektDetaljModalOverlay", lukkVektDetaljModal);

  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});

  lastIdag();
  oppdaterVarselKort();
  if (location.hash === "#mat") visFane("mat");
  if (location.hash === "#helg") setTimeout(() => $("helgKort").scrollIntoView({ block: "center" }), 400);

  // Hent ny dag når appen åpnes igjen fra bakgrunnen (f.eks. neste morgen).
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") lastIdag();
  });
}

document.addEventListener("DOMContentLoaded", main);
