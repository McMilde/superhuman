const TYPE_NAVN = {
  gange: "Gange",
  styrke: "Styrke",
  roing: "Roing",
  hvile: "Hvile",
  valgfritt: "Valgfritt",
};

function $(id) {
  return document.getElementById(id);
}

let ovelseBibliotek = null;

async function lastOvelseBibliotek() {
  if (ovelseBibliotek) return ovelseBibliotek;
  const res = await fetch("/api/ovelser");
  ovelseBibliotek = await res.json();
  return ovelseBibliotek;
}

function renderOvelseChips(container, idListe) {
  container.innerHTML = idListe
    .map((id) => {
      const o = ovelseBibliotek.ovelser[id];
      if (!o) return "";
      return `<button type="button" class="ovelse-chip" data-id="${id}">${escapeHtml(o.navn)}</button>`;
    })
    .join("");
  container.querySelectorAll(".ovelse-chip").forEach((btn) => {
    btn.addEventListener("click", () => apneOvelseModal(btn.dataset.id));
  });
}

// Animerer strekfigur-illustrasjonene: hvert element med et data-anim-attributt
// ("attributt:posisjon_a:posisjon_b ...") beveges frem og tilbake mellom de to
// posisjonene med requestAnimationFrame - kjøres kun mens øvelsesmodalen er åpen.
function jevn(t) {
  return t * t * (3 - 2 * t); // smoothstep, gir en mykere start/stopp enn lineær bevegelse
}

function startOvelseAnimasjon(svgEl) {
  const elementer = Array.from(svgEl.querySelectorAll("[data-anim]")).map((el) => ({
    el,
    deler: el
      .getAttribute("data-anim")
      .split(" ")
      .map((del) => {
        const [attributt, a, b] = del.split(":");
        return { attributt, a: parseFloat(a), b: parseFloat(b) };
      }),
  }));
  if (elementer.length === 0) return null;

  const varighetMs = 1600;
  let start = null;
  let rafId = null;

  function tick(ts) {
    if (start === null) start = ts;
    const syklus = ((ts - start) % (varighetMs * 2)) / varighetMs; // 0 -> 2
    const retning = syklus <= 1 ? syklus : 2 - syklus; // 0 -> 1 -> 0
    const fase = jevn(retning);
    for (const { el, deler } of elementer) {
      for (const { attributt, a, b } of deler) {
        el.setAttribute(attributt, a + (b - a) * fase);
      }
    }
    rafId = requestAnimationFrame(tick);
  }
  rafId = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(rafId);
}

function visOvelserForOkt(okt, blokkEl, tittelEl, listeEl) {
  if (okt && okt.type === "styrke") {
    blokkEl.classList.remove("hidden");
    tittelEl.textContent = "Øvelser (trykk for instruksjoner)";
    renderOvelseChips(listeEl, ovelseBibliotek.styrke_ider);
  } else if (okt && (okt.type === "roing" || okt.type === "valgfritt")) {
    blokkEl.classList.remove("hidden");
    tittelEl.textContent = "Teknikk (trykk for instruksjoner)";
    renderOvelseChips(listeEl, ovelseBibliotek.roing_ider);
  } else {
    blokkEl.classList.add("hidden");
  }
}

let apenOvelseId = null;
let stoppOvelseAnimasjon = null;

async function apneOvelseModal(id) {
  const o = ovelseBibliotek.ovelser[id];
  if (!o) return;
  lukkDagModal(); // lukk dag-detaljer bak seg om øvelsen ble åpnet derfra
  apenOvelseId = id;
  $("ovelseModalTittel").textContent = o.navn;
  $("ovelseModalSvg").innerHTML = `<svg viewBox="0 0 160 160">${o.svg}</svg>`;
  $("ovelseModalSteg").innerHTML = o.instruks.map((steg) => `<li>${escapeHtml(steg)}</li>`).join("");
  $("ovelseModalFokus").textContent = o.fokus;
  $("ovelseModalOverlay").classList.remove("hidden");

  if (stoppOvelseAnimasjon) stoppOvelseAnimasjon();
  stoppOvelseAnimasjon = startOvelseAnimasjon($("ovelseModalSvg").querySelector("svg"));

  const loggBlokk = $("ovelseModalLoggBlokk");
  if (ovelseBibliotek.styrke_ider.includes(id)) {
    loggBlokk.classList.remove("hidden");
    $("ovelseModalLoggStatus").classList.add("hidden");
    $("ovelseModalVekt").value = "";
    $("ovelseModalReps").value = "";
    $("ovelseModalSistBrukt").textContent = "Henter …";

    const res = await fetch(`/api/styrke-logg/${id}?dato=${idagDato()}`);
    const data = await res.json();
    if (apenOvelseId !== id) return; // modalen ble byttet mens vi ventet

    if (data.i_dag) {
      $("ovelseModalVekt").value = data.i_dag.vekt_kg ?? "";
      $("ovelseModalReps").value = data.i_dag.reps ?? "";
    }
    if (data.forrige) {
      const delerTekst = [
        data.forrige.vekt_kg != null ? `${data.forrige.vekt_kg} kg` : null,
        data.forrige.reps != null ? `${data.forrige.reps} reps` : null,
      ]
        .filter(Boolean)
        .join(" × ");
      $("ovelseModalSistBrukt").textContent = delerTekst
        ? `Sist brukt: ${delerTekst} (${formaterDato(data.forrige.dato)})`
        : "Ikke registrert tidligere.";
    } else {
      $("ovelseModalSistBrukt").textContent = "Ikke registrert tidligere.";
    }
  } else {
    loggBlokk.classList.add("hidden");
  }
}

function lukkOvelseModal() {
  $("ovelseModalOverlay").classList.add("hidden");
  apenOvelseId = null;
  if (stoppOvelseAnimasjon) {
    stoppOvelseAnimasjon();
    stoppOvelseAnimasjon = null;
  }
}

async function lagreOvelseLogg() {
  if (!apenOvelseId) return;
  const body = {
    dato: idagDato(),
    ovelse_id: apenOvelseId,
    vekt_kg: $("ovelseModalVekt").value,
    reps: $("ovelseModalReps").value,
  };
  await fetch("/api/styrke-logg", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const status = $("ovelseModalLoggStatus");
  status.classList.remove("hidden");
  setTimeout(() => status.classList.add("hidden"), 2000);
}

function idagDato() {
  const d = new Date();
  const mnd = String(d.getMonth() + 1).padStart(2, "0");
  const dag = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mnd}-${dag}`;
}

// ---- Faner ----

function settOppFaner() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`tab-${btn.dataset.tab}`).classList.add("active");
      if (btn.dataset.tab === "fysio") lastFysio();
      if (btn.dataset.tab === "oversikt") lastOversikt();
      if (btn.dataset.tab === "historikk") lastHistorikk();
    });
  });
}

// ---- I dag ----

async function lastDag() {
  const [res] = await Promise.all([fetch(`/api/dag?dato=${idagDato()}`), lastOvelseBibliotek()]);
  const data = await res.json();

  $("faseTagline").textContent = `Uke ${data.uke_nummer} · Fase ${data.fase.fase}: ${data.fase.navn}`;
  $("dagensSitat").textContent = `"${data.sitat}"`;

  const okt = data.okt;
  $("oktDagNavn").textContent = `${data.ukedag_navn}: ${okt ? okt.tittel : "Ingen økt planlagt"}`;
  $("oktType").textContent = okt ? (TYPE_NAVN[okt.type] || okt.type) : "";
  $("oktBeskrivelse").textContent = okt ? okt.beskrivelse : "";

  visOvelserForOkt(okt, $("oktOvelserBlokk"), $("oktOvelserTittel"), $("oktOvelserListe"));

  const fysioBlokk = $("fysioIdagBlokk");
  const fysioRow = $("fysioGjortRow");
  if (data.fysio_ovelser.length > 0) {
    fysioBlokk.classList.remove("hidden");
    fysioRow.classList.remove("hidden");
    $("fysioIdagListe").innerHTML = data.fysio_ovelser
      .map((o) => `<li><strong>${escapeHtml(o.navn)}</strong>${o.beskrivelse ? " – " + escapeHtml(o.beskrivelse) : ""}</li>`)
      .join("");
  } else {
    fysioBlokk.classList.add("hidden");
    fysioRow.classList.add("hidden");
  }

  const logg = data.logg;
  let status = "";
  if (logg) {
    if (logg.annen_treningsform) status = "annet";
    else if (logg.gjennomfort) status = "gjennomfort";
    else status = "ikke_gjennomfort";
  }
  settGjennomfortValg(status);
  $("treningsformBegrunnelse").value = (logg && logg.treningsform_begrunnelse) || "";
  $("ikkeGjennomfortBegrunnelse").value = (logg && logg.ikke_gjennomfort_begrunnelse) || "";
  $("fysioGjort").checked = !!(logg && logg.fysio_gjort);
  $("dagsloggNotater").value = (logg && logg.notater) || "";
}

function settGjennomfortValg(verdi) {
  $("gjennomfort").value = verdi;
  document.querySelectorAll("#gjennomfortToggle .segment").forEach((btn) => {
    btn.classList.toggle("aktiv", btn.dataset.val === verdi);
  });
  $("annenTreningsformBlokk").classList.toggle("hidden", verdi !== "annet");
  $("ikkeGjennomfortBlokk").classList.toggle("hidden", verdi !== "ikke_gjennomfort");
}

async function lagreDagslogg(e) {
  e.preventDefault();
  const valg = $("gjennomfort").value;
  const body = {
    dato: idagDato(),
    gjennomfort: valg === "gjennomfort" || valg === "annet",
    annen_treningsform: valg === "annet",
    treningsform_begrunnelse: $("treningsformBegrunnelse").value,
    ikke_gjennomfort_begrunnelse: $("ikkeGjennomfortBegrunnelse").value,
    fysio_gjort: $("fysioGjort").checked,
    notater: $("dagsloggNotater").value,
  };
  await fetch("/api/dagslogg", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const status = $("dagsloggStatus");
  status.textContent = "Lagret!";
  status.classList.remove("hidden");
  setTimeout(() => status.classList.add("hidden"), 2000);
  lastUke();
}

// ---- Uken ----

let ukeDagerCache = [];

async function lastUke() {
  const res = await fetch(`/api/uke?dato=${idagDato()}`);
  const data = await res.json();
  ukeDagerCache = data.dager;
  const grid = $("ukeGridMini");
  grid.innerHTML = data.dager
    .map((d) => {
      const okt = d.okt;
      const tittel = okt ? okt.tittel : "–";
      const type = okt ? TYPE_NAVN[okt.type] || okt.type : "";
      let statusKlasse = "status-uferdig";
      let statusTekst = "Ikke gjennomført";
      if (okt && okt.type === "hvile") {
        statusKlasse = "status-hvile";
        statusTekst = "Hviledag";
      }
      if (d.gjennomfort) {
        statusKlasse = "status-ferdig";
        statusTekst = "Gjennomført";
      }
      return `
        <div class="uke-dag uke-dag-trykkbar ${d.er_i_dag ? "i-dag" : ""}" data-dato="${d.dato}">
          <div class="uke-dag-navn">${d.ukedag_navn}</div>
          <div class="uke-dag-okt">${tittel}${type && type !== tittel ? " · " + type : ""}</div>
          <div class="uke-dag-status ${statusKlasse}">${statusTekst}</div>
        </div>`;
    })
    .join("");

  grid.querySelectorAll(".uke-dag-trykkbar").forEach((el) => {
    el.addEventListener("click", () => apneDagModal(el.dataset.dato));
  });
}

function apneDagModal(dato) {
  const d = ukeDagerCache.find((x) => x.dato === dato);
  if (!d) return;
  const okt = d.okt;

  $("dagModalTittel").textContent = `${d.ukedag_navn} · ${formaterDato(dato)}`;
  $("dagModalType").textContent = okt ? TYPE_NAVN[okt.type] || okt.type : "";
  $("dagModalBeskrivelse").textContent = okt ? okt.beskrivelse : "Ingen økt planlagt.";
  visOvelserForOkt(okt, $("dagModalOvelserBlokk"), $("dagModalOvelserTittel"), $("dagModalOvelserListe"));
  $("dagModalOverlay").classList.remove("hidden");
}

function lukkDagModal() {
  $("dagModalOverlay").classList.add("hidden");
}

// ---- Fysio-øvelser ----

let fysioCache = [];

async function lastFysio() {
  const res = await fetch("/api/fysio");
  fysioCache = await res.json();
  const liste = $("fysioListe");
  if (fysioCache.length === 0) {
    liste.innerHTML = `<li class="tom">Ingen øvelser lagt til ennå. Legg til når du har vært hos fysioterapeuten.</li>`;
    return;
  }
  liste.innerHTML = fysioCache
    .map(
      (o) => `
      <li class="fysio-rad ${o.aktiv ? "" : "inaktiv"}" data-id="${o.id}">
        <div>
          <strong>${escapeHtml(o.navn)}</strong>
          ${o.beskrivelse ? `<div class="fysio-beskrivelse">${escapeHtml(o.beskrivelse)}</div>` : ""}
        </div>
        <span class="badge">${o.aktiv ? "Aktiv" : "Av"}</span>
      </li>`
    )
    .join("");

  liste.querySelectorAll(".fysio-rad").forEach((el) => {
    el.addEventListener("click", () => apneFysioModal(Number(el.dataset.id)));
  });
}

function apneFysioModal(id) {
  const o = id ? fysioCache.find((x) => x.id === id) : null;
  $("fysioModalTitle").textContent = o ? "Rediger øvelse" : "Ny øvelse";
  $("fysioId").value = o ? o.id : "";
  $("fysioNavn").value = o ? o.navn : "";
  $("fysioBeskrivelse").value = o ? o.beskrivelse : "";
  $("fysioAktiv").checked = o ? !!o.aktiv : true;
  $("fysioDeleteBtn").classList.toggle("hidden", !o);
  $("modalOverlay").classList.remove("hidden");
}

function lukkFysioModal() {
  $("modalOverlay").classList.add("hidden");
}

async function lagreFysio(e) {
  e.preventDefault();
  const id = $("fysioId").value;
  const body = {
    navn: $("fysioNavn").value,
    beskrivelse: $("fysioBeskrivelse").value,
    aktiv: $("fysioAktiv").checked,
  };
  if (id) {
    await fetch(`/api/fysio/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } else {
    await fetch("/api/fysio", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }
  lukkFysioModal();
  lastFysio();
  lastDag();
}

async function slettFysio() {
  const id = $("fysioId").value;
  if (!id) return;
  if (!confirm("Slette denne øvelsen?")) return;
  await fetch(`/api/fysio/${id}`, { method: "DELETE" });
  lukkFysioModal();
  lastFysio();
  lastDag();
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
  renderTreningUke(data.trening_uke, data.streak_uker);
  renderOversiktKort(data.kort, data.tilkoblinger);
  renderInnsikt(data.innsikt);
}

function renderTreningUke(uke, streakUker) {
  const antall = uke.filter((d) => d.gjennomfort === true).length;
  $("treningUkeAntall").textContent = `${antall} av ${uke.length} gjennomført`;
  const iDag = new Date().toISOString().slice(0, 10);
  $("treningUkeStrip").innerHTML = uke
    .map((d) => {
      let status = "ikke-logget";
      if (d.gjennomfort === true) status = "gjort";
      else if (d.gjennomfort === false) status = "ikke-gjort";
      const idagKlasse = d.dato === iDag ? " trening-dag-idag" : "";
      return `<div class="trening-dag trening-dag-${status}${idagKlasse}" title="${formaterDato(d.dato)}"><span>${escapeHtml(d.ukedag_kort)}</span></div>`;
    })
    .join("");

  const streakEl = $("streakTekst");
  if (streakUker >= 1) {
    streakEl.textContent = `${streakUker} ${streakUker === 1 ? "uke" : "uker"} på rad med full gjennomføring`;
    streakEl.classList.remove("hidden");
  } else {
    streakEl.classList.add("hidden");
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
    `Ukene med minst 80% gjennomføring (${innsikt.uker_hoy} uker) endret vekten seg i snitt ${fmt(innsikt.snitt_delta_hoy)}, ` +
    `mot ${fmt(innsikt.snitt_delta_lav)} i ukene med lavere gjennomføring (${innsikt.uker_lav} uker).`;
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

async function lastHistorikk() {
  const res = await fetch("/api/historikk");
  const data = await res.json();

  const statsWrap = $("historikkStats");
  const stats = data.stats;
  statsWrap.innerHTML = `
    <div class="stat-tile"><strong>${stats.gjennomfort_prosent}%</strong><span>gjennomført</span></div>
    <div class="stat-tile"><strong>${stats.gjennomfort_antall}</strong><span>av ${stats.totalt_registrert} registrerte dager</span></div>
  `;

  const liste = $("historikkListe");
  if (data.dager.length === 0) {
    liste.innerHTML = `<li class="tom">Ingen dager registrert ennå. Kryss av i "I dag" for å begynne å bygge historikk.</li>`;
    return;
  }
  liste.innerHTML = data.dager
    .map((d) => {
      let statusKlasse = "status-uferdig";
      let statusTekst = "Ikke gjennomført";
      if (d.annen_treningsform) {
        statusKlasse = "status-annet";
        statusTekst = "Annen økt";
      } else if (d.gjennomfort) {
        statusKlasse = "status-ferdig";
        statusTekst = "Gjennomført";
      }
      const begrunnelse = d.annen_treningsform ? d.treningsform_begrunnelse : d.ikke_gjennomfort_begrunnelse;
      return `
        <li class="historikk-rad">
          <div class="historikk-rad-header">
            <span class="historikk-dato">${formaterDato(d.dato)} · ${d.ukedag_navn}</span>
            <span class="uke-dag-status ${statusKlasse}">${statusTekst}</span>
          </div>
          <div class="historikk-okt">${d.okt_tittel ? escapeHtml(d.okt_tittel) : ""}</div>
          ${begrunnelse ? `<div class="historikk-notater">${escapeHtml(begrunnelse)}</div>` : ""}
          ${d.notater ? `<div class="historikk-notater">${escapeHtml(d.notater)}</div>` : ""}
        </li>`;
    })
    .join("");
}

function escapeHtml(tekst) {
  const div = document.createElement("div");
  div.textContent = tekst || "";
  return div.innerHTML;
}

// ---- Oppstart ----

function main() {
  settOppFaner();

  $("dagsloggForm").addEventListener("submit", lagreDagslogg);
  document.querySelectorAll("#gjennomfortToggle .segment").forEach((btn) => {
    btn.addEventListener("click", () => settGjennomfortValg(btn.dataset.val));
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
  $("nyFysioBtn").addEventListener("click", () => apneFysioModal(null));
  $("fysioForm").addEventListener("submit", lagreFysio);
  $("fysioCancelBtn").addEventListener("click", lukkFysioModal);
  $("fysioDeleteBtn").addEventListener("click", slettFysio);
  $("modalOverlay").addEventListener("click", (e) => {
    if (e.target.id === "modalOverlay") lukkFysioModal();
  });
  $("ovelseLukkBtn").addEventListener("click", lukkOvelseModal);
  $("ovelseModalOverlay").addEventListener("click", (e) => {
    if (e.target.id === "ovelseModalOverlay") lukkOvelseModal();
  });
  $("dagModalLukkBtn").addEventListener("click", lukkDagModal);
  $("dagModalOverlay").addEventListener("click", (e) => {
    if (e.target.id === "dagModalOverlay") lukkDagModal();
  });
  $("ovelseModalLoggLagreBtn").addEventListener("click", lagreOvelseLogg);

  lastDag();
  lastUke();
}

document.addEventListener("DOMContentLoaded", main);
