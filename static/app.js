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
      if (btn.dataset.tab === "withings") { lastWithingsStatus(); lastWithingsData(); }
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

async function lastWithingsStatus() {
  const boks = $("withingsBoks");
  const tekst = $("withingsStatusTekst");
  const kobleBtn = $("withingsKobleBtn");
  const synkBtn = $("withingsSynkBtn");

  const res = await fetch("/api/withings/status");
  const data = await res.json();
  boks.classList.remove("hidden");

  if (!data.tilkoblet) {
    tekst.textContent = "Ikke koblet til Withings ennå.";
    kobleBtn.classList.remove("hidden");
    synkBtn.classList.add("hidden");
    return;
  }

  kobleBtn.classList.add("hidden");
  synkBtn.classList.remove("hidden");
  tekst.textContent = data.sist_synket
    ? `Koblet til Withings. Sist synket: ${new Date(data.sist_synket).toLocaleString("no-NO", { dateStyle: "short", timeStyle: "short" })}`
    : "Koblet til Withings.";
}

async function lastWithingsData() {
  const res = await fetch("/api/withings/data");
  const data = await res.json();
  const liste = $("withingsDataListe");

  if (data.length === 0) {
    liste.innerHTML = `<li class="tom">Ingen data fra Withings ennå.</li>`;
    return;
  }

  liste.innerHTML = data
    .map((d) => {
      const badges = d.malinger
        .map(
          (m) =>
            `<span class="badge">${escapeHtml(m.navn)}: ${m.verdi.toString().replace(".", ",")} ${escapeHtml(m.enhet)}</span>`
        )
        .join("");
      return `
        <li class="historikk-rad">
          <div class="historikk-rad-header">
            <span class="historikk-dato">${formaterDato(d.dato)}</span>
          </div>
          <div class="historikk-badges">${badges}</div>
        </li>`;
    })
    .join("");
}

async function synkroniserWithings() {
  const synkBtn = $("withingsSynkBtn");
  const tekst = $("withingsStatusTekst");
  synkBtn.disabled = true;
  tekst.textContent = "Synkroniserer …";
  const res = await fetch("/api/withings/synk", { method: "POST" });
  const data = await res.json();
  synkBtn.disabled = false;
  if (!res.ok) {
    tekst.textContent = `Kunne ikke synkronisere: ${data.error || "ukjent feil"}`;
    return;
  }
  await lastWithingsStatus();
  await lastWithingsData();
  if (data.nye > 0) lastVekt();
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
  $("withingsSynkBtn").addEventListener("click", synkroniserWithings);
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
