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
      if (btn.dataset.tab === "hendelser") lastHendelser();
      if (btn.dataset.tab === "vekt") lastVekt();
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

  const hendelserBlokk = $("hendelserBlokk");
  if (data.hendelse_typer.length > 0) {
    hendelserBlokk.classList.remove("hidden");
    const valgt = new Set((data.logg && data.logg.hendelser) || []);
    renderToggleChips($("hendelserListe"), data.hendelse_typer, valgt);
  } else {
    hendelserBlokk.classList.add("hidden");
  }

  const logg = data.logg;
  settGjennomfortValg(logg ? (logg.gjennomfort ? "1" : "0") : "");
  $("fysioGjort").checked = !!(logg && logg.fysio_gjort);
  $("dagsloggNotater").value = (logg && logg.notater) || "";
}

function settGjennomfortValg(verdi) {
  $("gjennomfort").value = verdi;
  document.querySelectorAll("#gjennomfortToggle .segment").forEach((btn) => {
    btn.classList.toggle("aktiv", btn.dataset.val === verdi);
  });
}

function renderToggleChips(container, typer, valgteIder) {
  container.innerHTML = typer
    .map(
      (t) =>
        `<button type="button" class="toggle-chip ${valgteIder.has(t.id) ? "valgt" : ""}" data-id="${t.id}">${escapeHtml(t.navn)}</button>`
    )
    .join("");
  container.querySelectorAll(".toggle-chip").forEach((btn) => {
    btn.addEventListener("click", () => btn.classList.toggle("valgt"));
  });
}

async function lagreDagslogg(e) {
  e.preventDefault();
  const valgteHendelser = Array.from($("hendelserListe").querySelectorAll(".toggle-chip.valgt")).map((btn) =>
    Number(btn.dataset.id)
  );
  const body = {
    dato: idagDato(),
    gjennomfort: $("gjennomfort").value === "1",
    fysio_gjort: $("fysioGjort").checked,
    hendelser: valgteHendelser,
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

// ---- Hendelser ----

let hendelseCache = [];

async function lastHendelser() {
  const res = await fetch("/api/hendelser");
  hendelseCache = await res.json();
  const liste = $("hendelseListe");
  if (hendelseCache.length === 0) {
    liste.innerHTML = `<li class="tom">Ingen hendelsestyper lagt til ennå.</li>`;
    return;
  }
  liste.innerHTML = hendelseCache
    .map(
      (h) => `
      <li class="fysio-rad ${h.aktiv ? "" : "inaktiv"}" data-id="${h.id}">
        <div><strong>${escapeHtml(h.navn)}</strong>${h.pauser_plan ? '<div class="fysio-beskrivelse">Pauser treningsplanen</div>' : ""}</div>
        <span class="badge">${h.aktiv ? "Aktiv" : "Av"}</span>
      </li>`
    )
    .join("");

  liste.querySelectorAll(".fysio-rad").forEach((el) => {
    el.addEventListener("click", () => apneHendelseModal(Number(el.dataset.id)));
  });
}

function apneHendelseModal(id) {
  const h = id ? hendelseCache.find((x) => x.id === id) : null;
  $("hendelseModalTitle").textContent = h ? "Rediger hendelsestype" : "Ny hendelsestype";
  $("hendelseId").value = h ? h.id : "";
  $("hendelseNavn").value = h ? h.navn : "";
  $("hendelseAktiv").checked = h ? !!h.aktiv : true;
  $("hendelsePauserPlan").checked = h ? !!h.pauser_plan : false;
  $("hendelseDeleteBtn").classList.toggle("hidden", !h);
  $("hendelseModalOverlay").classList.remove("hidden");
}

function lukkHendelseModal() {
  $("hendelseModalOverlay").classList.add("hidden");
}

async function lagreHendelse(e) {
  e.preventDefault();
  const id = $("hendelseId").value;
  const body = {
    navn: $("hendelseNavn").value,
    aktiv: $("hendelseAktiv").checked,
    pauser_plan: $("hendelsePauserPlan").checked,
  };
  if (id) {
    await fetch(`/api/hendelser/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } else {
    await fetch("/api/hendelser", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }
  lukkHendelseModal();
  lastHendelser();
  lastDag();
}

async function slettHendelse() {
  const id = $("hendelseId").value;
  if (!id) return;
  if (!confirm("Slette denne hendelsestypen?")) return;
  await fetch(`/api/hendelser/${id}`, { method: "DELETE" });
  lukkHendelseModal();
  lastHendelser();
  lastDag();
}

// ---- Vekt ----

async function lastVekt() {
  const res = await fetch("/api/vekt");
  const data = await res.json();

  const liste = $("vektListe");
  if (data.length === 0) {
    liste.innerHTML = `<li class="tom">Ingen vekt registrert ennå.</li>`;
  } else {
    liste.innerHTML = [...data]
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
    liste.querySelectorAll(".slett-lenke").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await fetch(`/api/vekt/${btn.dataset.id}`, { method: "DELETE" });
        lastVekt();
      });
    });
  }

  tegnVektGraf(data);
}

function formaterDato(isoDato) {
  const [aar, mnd, dag] = isoDato.split("-");
  return `${dag}.${mnd}.${aar}`;
}

function tegnVektGraf(data) {
  const wrap = $("vektGrafWrap");
  const svg = $("vektGraf");
  if (data.length < 2) {
    wrap.classList.add("hidden");
    svg.innerHTML = "";
    return;
  }
  wrap.classList.remove("hidden");

  const bredde = 600;
  const hoyde = 220;
  const marg = 30;

  const vekter = data.map((v) => v.vekt_kg);
  const min = Math.min(...vekter);
  const max = Math.max(...vekter);
  const spenn = max - min || 1;

  const punkter = data.map((v, i) => {
    const x = marg + (i / (data.length - 1)) * (bredde - marg * 2);
    const y = hoyde - marg - ((v.vekt_kg - min) / spenn) * (hoyde - marg * 2);
    return [x, y];
  });

  const linje = punkter.map(([x, y]) => `${x},${y}`).join(" ");
  const prikker = punkter
    .map(([x, y]) => `<circle cx="${x}" cy="${y}" r="4" fill="#1f7a5c" />`)
    .join("");

  svg.innerHTML = `
    <polyline points="${linje}" fill="none" stroke="#1f7a5c" stroke-width="3" />
    ${prikker}
  `;
}

async function leggTilVekt(e) {
  e.preventDefault();
  const body = {
    dato: $("vektDato").value,
    vekt_kg: $("vektKg").value,
  };
  const res = await fetch("/api/vekt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    $("vektKg").value = "";
    lastVekt();
  }
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
  renderTreningUke(data.trening_uke);
  renderOversiktKort(data.kort, data.tilkoblinger);
}

function renderTreningUke(uke) {
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
}

function renderOversiktKort(kortListe, tilkoblinger) {
  const container = $("oversiktKort");

  container.innerHTML = kortListe
    .map((k, i) => {
      const meta = OVERSIKT_META[k.id];
      const fargeVar = `--metrikk-${k.id}`;
      const ikonSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${meta.ikon}</svg>`;
      const stil = `style="--kort-forsinkelse:${i * 70}ms"`;

      if (!tilkoblinger[meta.kilde]) {
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

      if (k.siste === null) {
        return `
        <div class="oversikt-kort" ${stil}>
          <div class="oversikt-kort-header">
            <div class="oversikt-kort-ikon" style="color:var(${fargeVar})">${ikonSvg}</div>
            <div class="oversikt-kort-titler"><h3>${meta.navn}</h3></div>
          </div>
          <p class="hint">Ingen data ennå. Trykk synk-knappen øverst for å hente.</p>
        </div>`;
      }

      const desimaler = k.enhet === "kg" || k.enhet === "%" ? 1 : 0;
      const deltaHtml =
        k.delta_7d == null || k.delta_7d === 0
          ? ""
          : `<span class="oversikt-kort-delta ${k.delta_7d > 0 ? "opp" : "ned"}">${k.delta_7d > 0 ? "↑" : "↓"} ${Math.abs(k.delta_7d).toFixed(desimaler).replace(".", ",")}${k.enhet}</span>`;
      const sekundaerHtml = k.sekundaer
        ? `<p class="oversikt-kort-sekundaer">${escapeHtml(k.sekundaer.navn)}: ${k.sekundaer.verdi.toString().replace(".", ",")}${k.sekundaer.enhet ? " " + escapeHtml(k.sekundaer.enhet) : ""}</p>`
        : "";

      return `
        <div class="oversikt-kort" ${stil} data-kort="${k.id}">
          <div class="oversikt-kort-header">
            <div class="oversikt-kort-ikon" style="color:var(${fargeVar})">${ikonSvg}</div>
            <div class="oversikt-kort-titler">
              <h3>${meta.navn}</h3>
              ${sekundaerHtml}
            </div>
            <div class="oversikt-kort-verdi-blokk">
              <span class="oversikt-kort-verdi" data-til="${k.siste}" data-desimaler="${desimaler}">0</span><span class="oversikt-kort-enhet">${escapeHtml(k.enhet)}</span>
              ${deltaHtml}
            </div>
          </div>
          <div class="oversikt-graf-wrap">
            <div class="graf-tooltip"></div>
          </div>
        </div>`;
    })
    .join("");

  kortListe.forEach((k) => {
    const kortEl = container.querySelector(`[data-kort="${k.id}"]`);
    if (!kortEl) return;
    const verdiEl = kortEl.querySelector(".oversikt-kort-verdi");
    tellOpp(verdiEl, Number(verdiEl.dataset.til), Number(verdiEl.dataset.desimaler));
    tegnGraf(kortEl.querySelector(".oversikt-graf-wrap"), k.serie, `--metrikk-${k.id}`);
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

function tegnGraf(wrapEl, serie, fargeVar) {
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
    <path d="${linjeSti}" fill="none" stroke="var(${fargeVar})" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="graf-linje"></path>
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
  const hendelseTiles = Object.entries(stats.hendelse_antall)
    .map(([navn, antall]) => `<div class="stat-tile"><strong>${antall}</strong><span>${escapeHtml(navn)}</span></div>`)
    .join("");
  statsWrap.innerHTML = `
    <div class="stat-tile"><strong>${stats.gjennomfort_prosent}%</strong><span>gjennomført</span></div>
    <div class="stat-tile"><strong>${stats.gjennomfort_antall}</strong><span>av ${stats.totalt_registrert} registrerte dager</span></div>
    ${hendelseTiles}
  `;

  const liste = $("historikkListe");
  if (data.dager.length === 0) {
    liste.innerHTML = `<li class="tom">Ingen dager registrert ennå. Kryss av i "I dag" for å begynne å bygge historikk.</li>`;
    return;
  }
  liste.innerHTML = data.dager
    .map((d) => {
      const hendelseBadges = d.hendelser.map((h) => `<span class="badge">${escapeHtml(h.navn)}</span>`).join("");
      return `
        <li class="historikk-rad">
          <div class="historikk-rad-header">
            <span class="historikk-dato">${formaterDato(d.dato)} · ${d.ukedag_navn}</span>
            <span class="uke-dag-status ${d.gjennomfort ? "status-ferdig" : "status-uferdig"}">${d.gjennomfort ? "Gjennomført" : "Ikke gjennomført"}</span>
          </div>
          <div class="historikk-okt">${d.okt_tittel ? escapeHtml(d.okt_tittel) : ""}</div>
          ${hendelseBadges ? `<div class="historikk-badges">${hendelseBadges}</div>` : ""}
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
  $("vektDato").value = idagDato();

  $("dagsloggForm").addEventListener("submit", lagreDagslogg);
  document.querySelectorAll("#gjennomfortToggle .segment").forEach((btn) => {
    btn.addEventListener("click", () => settGjennomfortValg(btn.dataset.val));
  });
  $("vektForm").addEventListener("submit", leggTilVekt);
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
  $("nyHendelseBtn").addEventListener("click", () => apneHendelseModal(null));
  $("hendelseForm").addEventListener("submit", lagreHendelse);
  $("hendelseCancelBtn").addEventListener("click", lukkHendelseModal);
  $("hendelseDeleteBtn").addEventListener("click", slettHendelse);
  $("hendelseModalOverlay").addEventListener("click", (e) => {
    if (e.target.id === "hendelseModalOverlay") lukkHendelseModal();
  });

  lastDag();
  lastUke();
}

document.addEventListener("DOMContentLoaded", main);
