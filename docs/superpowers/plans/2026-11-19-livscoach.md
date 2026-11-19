# Livscoach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Superhuman 2.0 from a fixed training plan into a life coach: daily check-off (fastet/alkohol/trent/syk), Claude-written daily message, weekly family menu + shopping list, coach-chosen training days, alcohol support and real iPhone push notifications — keeping Withings, Oura, Oversikt, vekt/målvekt, historikk, backup and login.

**Architecture:** Same Flask + SQLite app on Railway (`app.py` keeps all routes, matching the existing pattern). New logic lives in three focused modules that take a `sqlite3.Connection` and never import `app`: `livsstil.py` (check-offs, week plans, training-day rules, streaks), `coach.py` (all Claude calls + rule-based reserve texts), `varsler.py` (web push + an in-process minute-tick scheduler). Frontend stays vanilla JS in `static/`.

**Tech Stack:** Python 3 / Flask / SQLite, `anthropic` SDK (structured outputs via `messages.parse`), `pywebpush` (+ `py_vapid`), pytest, Playwright (already installed ad hoc) for UI checks.

**Spec:** `docs/superpowers/specs/2026-11-19-livscoach-design.md`

## Global Constraints

- All user-facing text in Norwegian (bokmål). Tone: warm, direct, short. Never moralizing, never shaming after a bad weekend.
- Never DROP a table or column that may hold user data (`dagslogg`, `vektlogg`, `fysio_ovelser`, `styrke_logg`, `withings_*`, `oura_*`, `innstillinger`). New columns via `ALTER TABLE ADD COLUMN`; new tables via `CREATE TABLE IF NOT EXISTS`.
- Claude model: `claude-opus-5-5` (skill default). `output_config.effort`: `"low"` for daily message, chat, «vanskelig», helg tips; `"medium"` for the weekly plan. Use server-side refusal fallback (`betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`) — check `python/claude-api/README.md` § Refusal Fallbacks in the claude-api skill for the exact Python binding before writing it. Always check `stop_reason` before reading content.
- Every Claude call has a rule-based reserve: missing `ANTHROPIC_API_KEY`, any exception, refusal, or parse failure → reserve text/data. The app must never show an empty card.
- Data sent to Claude: only the compact summary from `coach.lag_sammendrag` (last 14 days check-offs, weight trend + målvekt, Oura søvn/restitusjon last 7 days, this week's plan). No passwords, tokens, or names other than "Eivin".
- Timezone for all scheduling and "today": `ZoneInfo("Europe/Oslo")`.
- Default notification times (editable): morgen `07:00`, middag `15:30`, helg fredag `15:00`, kveld `21:00`, søndag `18:00`. A job only fires within 90 minutes after its time, and at most once per date (`varsel_logg` UNIQUE).
- Training days: start 3 per week, clamp 2–5. Coach only says *that* it is a training day, never what to train.
- Weight-loss pace target communicated to Claude: ~0.5 kg/week, no calorie counting for the user.
- Dinners: max ~30 min, family with kids aged 5 and 10, Eivin tolerates everything. Lunch eaten 11:30 at work, often partner's sourdough bread; dinner ~17:30.
- When appropriate (rarely), coach may mention fastlegen or RUSinfo (915 08588); never in every message.
- VAPID `sub` claim: `"https://trening.flibber.no"` (no email address).
- Tests never touch the real `trening.db`: `tests/conftest.py` points `DB_PATH` at a tmp file before importing `app`, sets `PLANLEGGER=0`, and unsets `ANTHROPIC_API_KEY` and `APP_PASSORD`.
- After any local server run, kill stray `python.exe` processes via PowerShell `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` (known gotcha on this PC).
- Every new color goes into both the light `:root` block and the dark `@media` override in `style.css`. Reuse the existing component set: segmented toggle, `.ios-switch`, pill chips, cards, bottom tab bar.

## Review Focus

1. **App restarts / redeploys around a scheduled time** — a Railway redeploy at 07:20 must still send the morning push once, and a restart at 23:00 must not send the morning push late. (Task 7 tests: within-window fires once; outside-window never fires; second tick same day no-op.)
2. **Claude unavailable or out of credit** — balance runs out (auto-reload is off) → every card, push, menu, chat still renders from reserve. (Task 4 tests with the Claude function raising.)
3. **Week with no ukeplan yet** (first week after deploy, or Sunday job missed) — opening I dag / Mat mid-week must create a plan on demand, not crash. (Task 3 test `test_hent_eller_lag_ukeplan_lager_ved_behov`.)
4. **Push subscription expired** (iPhone app removed/re-added) — push service answers 404/410 → subscription deleted, other subscriptions still get the push, scheduler keeps running. (Task 6 test.)
5. **Old history** — days logged only in the old `dagslogg` must still appear in Historikk and Oversikt's 7-day strip as "trent" when `gjennomfort=1`. (Task 2 test.)

---

### Task 1: Test harness + remove the fixed training plan backend

**Files:**
- Create: `tests/conftest.py`, `tests/test_opprydding.py`
- Modify: `app.py` (delete training-plan constants/routes; `init_db`; login exemptions), `requirements.txt` (add `anthropic>=0.121`, `pywebpush`, `pytest`)

**Interfaces:**
- Produces: pytest fixtures `client` (Flask test client) and `db` (`sqlite3.Connection` to the tmp DB, `row_factory=sqlite3.Row`) used by all later tasks.

- [ ] **Step 1: Install deps locally**: `python -m pip install anthropic pywebpush pytest`. If the PC's application control blocks `cryptography`'s compiled parts (see project memory about AppLocker/WDAC), say so and keep tests that need it mocked; Railway installs them fine.
- [ ] **Step 2: Write `tests/conftest.py`**: set env `DB_PATH=<tmp_path_factory file>`, `PLANLEGGER=0`, pop `ANTHROPIC_API_KEY`, `APP_PASSORD`; then `import app`; fixture `client` = `app.app.test_client()`; fixture `db` yields a fresh connection and, after each test, deletes rows from all non-config tables created in this plan plus `dagslogg`, `vektlogg`.
- [ ] **Step 3: Write failing tests in `tests/test_opprydding.py`**:
```python
@pytest.mark.parametrize("url", ["/api/dag", "/api/uke", "/api/ovelser", "/api/fysio", "/api/varsel", "/api/styrke-logg/kneboy"])
def test_treningsplan_ruter_er_fjernet(client, url):
    assert client.get(url).status_code == 404

def test_oversikt_og_backup_virker_fortsatt(client):
    assert client.get("/api/oversikt?dager=30").status_code == 200
    assert client.get("/api/backup").status_code == 200

def test_init_db_lar_gamle_tabeller_sta(db):
    navn = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"dagslogg", "vektlogg", "innstillinger"} <= navn
```
- [ ] **Step 4: Run** `python -m pytest tests -v` → expect FAIL (routes still 200).
- [ ] **Step 5: Implement**: delete `STYRKE_OVELSER`, `ROING_TEKNIKK`, SVG helpers, `OVELSER`, `STYRKE_ID_LISTE`, `FASER`, `OKT_MAL`, `QUOTES`, `hent_fase`, `hent_mal`, `dagens_sitat`, `hent_aktive_fysio`, routes `api_ovelser`, `api_dag`, `api_varsel`, `api_uke`, `api_lagre_dagslogg`, all `/api/fysio*`, `/api/styrke-logg*`. In `init_db` stop creating/rebuilding `faser` and `okt_mal` (leave existing tables alone; do **not** keep the `DROP TABLE okt_mal`). Remove `"api_varsel"` from `krev_innlogging` exemptions. Keep `uke_og_dag` only if still referenced after Task 2; otherwise delete it there. `beregn_streak_uker`/`beregn_innsikt`/`api_historikk` will break here — stub them minimally so `/api/oversikt` returns 200 (`streak_uker: 0`, `innsikt: {"nok_data": False}`); Task 2 replaces them.
- [ ] **Step 6: Run tests** → PASS. Also `python -c "import app"` succeeds.
- [ ] **Step 7: Commit** on branch `livscoach`: `git checkout -b livscoach` (first task only), `git add -A`, `git commit -m "Fjern fast treningsplan, legg til testoppsett"`.

---

### Task 2: Daily check-off (dagssjekk), Historikk and Oversikt rewiring

**Files:**
- Create: `livsstil.py`, `tests/test_dagssjekk.py`
- Modify: `app.py` (`init_db`, new routes, `api_historikk`, `api_oversikt`, replace `beregn_streak_uker`/`beregn_innsikt`)

**Interfaces:**
- Produces in `livsstil.py`:
  - `opprett_tabeller(conn) -> None` (called from `init_db`; creates every table this plan adds — `dagssjekk`, `ukeplan`, `helgeplan`, `dagsmelding`, `chat`, `push_abonnement`, `varsel_logg` — and adds `innstillinger.varsel_tider TEXT`, `innstillinger.vapid_privat TEXT`, `innstillinger.vapid_offentlig TEXT`)
  - `lagre_dagssjekk(conn, dato: str, fastet: bool, alkohol: bool, alkohol_enheter: float|None, trent: bool, syk: bool, notat: str) -> dict`
  - `hent_dagssjekk(conn, dato: str) -> dict|None`
  - `dagsstatus(conn, dato: str) -> dict|None` — dagssjekk row, or derived from old `dagslogg` (`trent = gjennomfort or annen_treningsform`, others False, `kilde: "gammel"`) if no dagssjekk exists
  - `alkoholfrie_hverdager_pa_rad(conn, i_dag: date) -> int` — counts back from yesterday (and today if registered), Mon–Thu only (Fri–Sun skipped, neither break nor count); stops at a weekday with `alkohol=1` or with no registration
- Tables: `dagssjekk(dato TEXT PRIMARY KEY, fastet INT, alkohol INT, alkohol_enheter REAL, trent INT, syk INT, notat TEXT DEFAULT '', oppdatert TEXT)`. Rest defined in later tasks' schema but created here: `ukeplan(uke_start TEXT PRIMARY KEY, treningsdager TEXT, antall_trening INT, middager TEXT, lunsj TEXT, kilde TEXT, laget TEXT)`, `helgeplan(uke_start TEXT PRIMARY KEY, planlagte_enheter INT, tips TEXT, oppsummering TEXT, opprettet TEXT)`, `dagsmelding(dato TEXT PRIMARY KEY, tittel TEXT, tekst TEXT, treningsdag INT, flyttet_fra TEXT, kilde TEXT)`, `chat(id INTEGER PRIMARY KEY AUTOINCREMENT, tid TEXT, rolle TEXT, tekst TEXT)`, `push_abonnement(endpoint TEXT PRIMARY KEY, p256dh TEXT, auth TEXT, opprettet TEXT)`, `varsel_logg(dato TEXT, type TEXT, sendt TEXT, UNIQUE(dato, type))`.
- Routes: `GET /api/dagssjekk?dato=` → `dagsstatus` or `null`; `POST /api/dagssjekk` JSON with the six fields (+`dato`, default today Oslo) → saved row. `alkohol_enheter` is forced to `None` when `alkohol` is false; accepts "2,5".

- [ ] **Step 1: Write failing tests**:
```python
def test_lagre_og_hent_dagssjekk(client):
    r = client.post("/api/dagssjekk", json={"dato": "2026-11-16", "fastet": True, "alkohol": True, "alkohol_enheter": "2,5", "trent": False, "syk": False})
    assert r.status_code == 200 and r.json["alkohol_enheter"] == 2.5
    assert client.get("/api/dagssjekk?dato=2026-11-16").json["fastet"] == 1

def test_enheter_nullstilles_uten_alkohol(client):
    r = client.post("/api/dagssjekk", json={"dato": "2026-11-17", "alkohol": False, "alkohol_enheter": 4})
    assert r.json["alkohol_enheter"] is None

def test_gammel_dagslogg_vises_som_trent(client, db):
    db.execute("INSERT INTO dagslogg (dato, gjennomfort) VALUES ('2026-08-22', 1)"); db.commit()
    assert client.get("/api/dagssjekk?dato=2026-08-22").json["trent"] == 1
    dager = client.get("/api/historikk").json["dager"]
    assert any(d["dato"] == "2026-08-22" and d["trent"] for d in dager)

def test_alkoholfrie_hverdager_hopper_over_helg(db):
    # Thu 2026-11-12 alkohol, Fri-Sun alkohol, Mon 16 + Tue 17 fri; today Wed 18
    ...  # insert via livsstil.lagre_dagssjekk
    assert livsstil.alkoholfrie_hverdager_pa_rad(db, date(2026, 11, 18)) == 2
```
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `livsstil.py` functions above and the two routes. Rewrite `api_historikk`: union of dates from `dagssjekk` and `dagslogg`, newest first, each item `dagsstatus` + `ukedag_navn`; stats `{totalt_registrert, fastedager, treningsdager, alkoholfrie_hverdager_prosent}` over the last 30 days. In `api_oversikt`: `trening_uke[].gjennomfort` = `dagsstatus(...)["trent"]` (None if no row); replace `streak_uker` with `alkoholfri_rekke: alkoholfrie_hverdager_pa_rad(...)`; replace `beregn_innsikt` with weeks grouped by alcohol-free days (≥5 of 7 vs fewer) → same output shape (`nok_data`, `uker_hoy`, `uker_lav`, `snitt_delta_hoy`, `snitt_delta_lav`). Delete `uke_og_dag` if now unused.
- [ ] **Step 4: Run all tests** → PASS.
- [ ] **Step 5: Commit** `"Daglig avkrysning: fastet, alkohol, trent, syk"`.

---

### Task 3: Week plan and training-day rules (no AI yet)

**Files:**
- Modify: `livsstil.py`
- Create: `tests/test_ukeplan.py`

**Interfaces:**
- Consumes: tables from Task 2.
- Produces in `livsstil.py`:
  - `mandag_for(d: date) -> date`
  - `RESERVE_MIDDAGER: list[dict]` — 12 family dinners, each `{"navn": str, "minutter": int, "beskrivelse": str, "ingredienser": list[str]}`; `RESERVE_LUNSJ: dict` same shape (kjøttdeig + grønnsaker meal-prep, 5 porsjoner) plus `"brodtips": list[str]` (4 sourdough toppings that keep you full)
  - `velg_treningsdager(uke_start: date, antall: int) -> list[str]` — spread evenly, deterministic: 2→[Tue,Thu], 3→[Mon,Wed,Fri], 4→[Mon,Tue,Thu,Sat], 5→[Mon,Tue,Wed,Fri,Sat]; clamp antall to 2..5
  - `neste_antall_trening(conn, uke_start: date) -> int` — previous week's `antall_trening` (default 3); +1 if every planned day last week has `trent=1`, −1 if fewer than half; clamp 2..5
  - `lagre_ukeplan(conn, uke_start: date, treningsdager: list[str], middager: list[dict], lunsj: dict, kilde: str) -> dict`
  - `hent_eller_lag_ukeplan(conn, uke_start: date, lag_plan=None) -> dict` — returns stored plan; if none, calls `lag_plan(conn, uke_start)` (Task 4 injects the Claude version) or, when `lag_plan is None`, builds a reserve plan (`velg_treningsdager(uke_start, neste_antall_trening(...))`, 5 dinners rotated from `RESERVE_MIDDAGER` by ISO week number, `RESERVE_LUNSJ`), saves and returns it. Returned dict: `{uke_start, treningsdager, antall_trening, middager: [{dag: "YYYY-MM-DD", ...middag}], lunsj, handleliste: list[str], kilde}`; dinners Mon–Fri.
  - `handleliste(plan: dict) -> list[str]` — union of all dinner + lunsj ingredients, de-duplicated case-insensitively, original order kept
  - `er_treningsdag_i_dag(conn, i_dag: date, restitusjon: float|None) -> tuple[bool, str|None]` — reads the plan; if today is planned and (`restitusjon is not None and restitusjon < 70` or yesterday's dagssjekk `syk=1`), moves it to the next later day this week that is not already a training day (updates the stored `treningsdager`) and returns `(False, "<reason>")`; if today is planned otherwise → `(True, None)`; if a previous move put it on today → `(True, None)`.

- [ ] **Step 1: Write failing tests**: `test_velg_treningsdager_tre` (`2026-11-16` → `["2026-11-16","2026-11-18","2026-11-20"]`); `test_antall_okes_etter_full_uke`; `test_antall_minskes_og_klemmes`; `test_hent_eller_lag_ukeplan_lager_ved_behov` (empty DB → plan with 5 middager, 3 treningsdager, kilde `"reserve"`, second call returns same `laget`); `test_handleliste_uten_duplikater` (`"Løk"` and `"løk"` → one); `test_lav_restitusjon_flytter_treningsdag` (Mon planned, restitusjon 55 → `(False, reason)` and Tue now in `treningsdager`); `test_syk_i_gar_flytter`; `test_ingen_ledig_dag_senere_i_uka` (Sunday planned + low restitution → `(False, reason)`, nothing added).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the functions.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `"Ukeplan med treningsdager og reservemeny"`.

---

### Task 4: Claude coach with reserve texts

**Files:**
- Create: `coach.py`, `tests/test_coach.py`

**Interfaces:**
- Consumes: `livsstil.*` from Tasks 2–3.
- Produces in `coach.py`:
  - `MODELL = "claude-opus-5-5"`
  - `sporr_claude(system: str, melding: str, utdata: type[BaseModel] | None, effort: str) -> BaseModel | str` — the only function that touches the SDK; raises `CoachUtilgjengelig` when no key, on any API error, refusal, or missing parsed output. Tests monkeypatch this.
  - `lag_sammendrag(conn, i_dag: date) -> str` — compact Norwegian text block (see Global Constraints for content)
  - `SYSTEM_PROMPT: str` — Eivin's context from the spec: goals (−20 kg, no alcohol on weekdays, few units on weekends, finds it hard to stop once started), 16–18 h fasting most days, meals 11:30 / 17:30, sourdough at lunch, family with kids 5 and 10, trains himself, tone rules, RUSinfo rule, "never more than ~80 words unless asked"
  - Pydantic output models: `Dagsmelding(tittel: str, tekst: str)`, `Middag(navn, minutter: int, beskrivelse, ingredienser: list[str])`, `Ukemeny(middager: list[Middag] (exactly 5), lunsj: Middag, brodtips: list[str], antall_trening: int)`, `HelgTips(tips: list[str])`
  - `lag_dagsmelding(conn, i_dag: date, treningsdag: bool, flytt_grunn: str|None, middag: dict|None) -> dict` — `{tittel, tekst, kilde}`; tittel is `"I DAG ER DET TRENINGSDAG 💪"` when `treningsdag` (enforced in code, not left to Claude), otherwise Claude's; reserve: fixed set of 14 rotating texts that mention dinner and the alcohol-free streak
  - `lag_ukeplan_med_claude(conn, uke_start: date) -> dict` — matches the `lag_plan` hook of `hent_eller_lag_ukeplan`; asks for `Ukemeny` (effort medium), clamps `antall_trening` to `neste_antall_trening ± 1` and 2..5, saves via `lagre_ukeplan(..., kilde="claude")`; on `CoachUtilgjengelig` falls back to the reserve plan
  - `bytt_middag(conn, uke_start: date, dag: str) -> dict` — new `Middag` different from the week's other dinners; reserve: next unused `RESERVE_MIDDAGER` entry; updates the stored plan and returns it with recomputed `handleliste`
  - `svar_chat(conn, tekst: str) -> str` — stores user + assistant rows in `chat`; sends the summary + last 20 chat rows; reserve: `"Coachen er ikke tilgjengelig akkurat nå. Prøv igjen litt senere."`
  - `vanskelig_na(conn) -> str` — ≤60 words, one concrete thing to do right now; reserve: random from 10 fixed alternatives (e.g. alkoholfri øl/kullsyrevann med sitron, 10 min gåtur, dusj, ring noen, spis noe salt)
  - `helg_tips(conn, planlagte_enheter: int) -> list[str]` — 2–3 tips; reserve: fixed 3 (kjøp bare inn antallet, vann annenhver gang, bestem sluttidspunkt)
  - `helg_oppsummering(conn, uke_start: date) -> str` — planned vs actual sum of `alkohol_enheter` Fri–Sun, neutral and forward-looking; reserve is a template with the two numbers

- [ ] **Step 1: Write failing tests** (all with `sporr_claude` monkeypatched):
```python
def test_dagsmelding_reserve_uten_nokkel(db):
    m = coach.lag_dagsmelding(db, date(2026,11,18), True, None, {"navn": "Kyllingwok"})
    assert m["tittel"] == "I DAG ER DET TRENINGSDAG 💪" and m["kilde"] == "reserve" and m["tekst"]

def test_dagsmelding_bruker_claude(db, monkeypatch):
    monkeypatch.setattr(coach, "sporr_claude", lambda *a, **k: coach.Dagsmelding(tittel="God morgen", tekst="Hei"))
    m = coach.lag_dagsmelding(db, date(2026,11,19), False, None, None)
    assert m == {"tittel": "God morgen", "tekst": "Hei", "kilde": "claude"}

def test_ukeplan_claude_klemmer_antall(db, monkeypatch): ...  # Claude says 9 → stored antall_trening == 4 (3+1)
def test_ukeplan_faller_tilbake(db, monkeypatch): ...  # sporr_claude raises → kilde "reserve"
def test_bytt_middag_gir_ny_og_oppdatert_handleliste(db, monkeypatch): ...
def test_chat_lagrer_begge_roller(db, monkeypatch): ...
def test_sammendrag_inneholder_rekke_og_malvekt(db): ...  # contains "alkoholfrie hverdager på rad" and målvekt value
def test_sammendrag_sender_ikke_hemmeligheter(db): ...  # insert fake withings token → token string not in summary
```
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement `sporr_claude`** with `anthropic.Anthropic()` and `client.messages.parse(model=MODELL, max_tokens=16000, system=..., messages=[...], output_format=utdata, output_config={"effort": effort})` (plain `messages.create` when `utdata is None`) plus the refusal fallback per Global Constraints; client `timeout=60`, `max_retries=2`.
- [ ] **Step 4: Implement the rest** of `coach.py`.
- [ ] **Step 5: Run** → PASS.
- [ ] **Step 6: Commit** `"Claude-coach med reservetekster"`.

---

### Task 5: Coach / mat / helg API routes

**Files:**
- Modify: `app.py`
- Create: `tests/test_api_coach.py`

**Interfaces:**
- Consumes: Tasks 2–4.
- Produces routes (all behind login):
  - `GET /api/i-dag` → `{dato, ukedag_navn, dagssjekk, melding: {tittel, tekst, kilde}, treningsdag: bool, flytt_grunn, middag, alkoholfri_rekke, helg: {planlagte_enheter, tips, oppsummering}|null, er_fredag_til_sondag: bool}`. Uses stored `dagsmelding` for today, or builds it (via `livsstil.er_treningsdag_i_dag` with today's Oura restitusjon from `oura_malinger`, then `coach.lag_dagsmelding`) and stores it.
  - `GET /api/mat` → current week plan (`hent_eller_lag_ukeplan(conn, mandag, lag_plan=coach.lag_ukeplan_med_claude)`) incl. `handleliste` and `lunsj.brodtips`
  - `POST /api/mat/bytt` `{dag}` → updated plan (400 if `dag` not one of the plan's dinner days)
  - `GET /api/coach/chat` → last 30 rows; `POST /api/coach/chat` `{tekst}` → `{svar}` (400 on empty)
  - `POST /api/coach/vanskelig` → `{tekst}`
  - `POST /api/helg` `{planlagte_enheter}` → `{planlagte_enheter, tips}` (int 0..30, else 400; stored in `helgeplan` for current week)

- [ ] **Step 1: Write failing tests**: `test_i_dag_uten_nokkel_gir_reserve`, `test_i_dag_lagres_og_gjenbrukes` (second call doesn't call `coach.lag_dagsmelding` again — monkeypatch counter), `test_mat_lager_plan_ved_behov`, `test_bytt_ugyldig_dag_400`, `test_chat_tom_tekst_400`, `test_helg_lagrer_og_gir_tips`, `test_helg_ugyldig_antall_400`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `"API for coach, mat og helgeplan"`.

---

### Task 6: Web push (keys, subscribe, service worker, send)

**Files:**
- Create: `varsler.py`, `static/sw.js`, `tests/test_push.py`
- Modify: `app.py` (routes, `krev_innlogging` exemption for `service_worker`), `static/manifest.json` (ensure `"display": "standalone"`, `"start_url": "/"`)

**Interfaces:**
- Produces in `varsler.py`:
  - `hent_eller_lag_vapid(conn) -> tuple[str, str]` — `(privat_pem, offentlig_b64url_uncompressed_point)`; generated once with `py_vapid.Vapid01`, stored in `innstillinger`
  - `lagre_abonnement(conn, sub: dict) -> None` (upsert on endpoint; validates `endpoint`, `keys.p256dh`, `keys.auth`, raises `ValueError`)
  - `send_til_alle(conn, tittel: str, tekst: str, url: str = "/", sender=None) -> int` — sends JSON `{tittel, tekst, url}` via `pywebpush.webpush(..., vapid_claims={"sub": "https://trening.flibber.no"})` (or the injected `sender(sub_info, data)` in tests); deletes subscriptions whose send raises with HTTP 404/410; other errors logged and skipped; returns number delivered
- Routes: `GET /api/push/nokkel` → `{offentlig}`; `POST /api/push/abonner` (subscription JSON) → 201 / 400; `POST /api/push/test` → sends "Varsler virker! 🎉" and returns `{sendt}`; `GET /sw.js` (endpoint name `service_worker`, served from `static/sw.js` with `Content-Type: application/javascript` and `Service-Worker-Allowed: /`).
- `sw.js`: `push` → `showNotification(tittel, {body: tekst, data: {url}, icon: "/static/icon-192.png"})`; `notificationclick` → focus an open client or `clients.openWindow(url)`.

- [ ] **Step 1: Write failing tests**: `test_vapid_lages_en_gang` (two calls equal), `test_abonner_ugyldig_400`, `test_send_sletter_utlopt_abonnement` (sender raises an exception carrying `response.status_code == 410` for one endpoint, succeeds for another → returns 1, only the good one remains), `test_sw_js_uten_innlogging` (with `APP_PASSORD` patched on → `/sw.js` is 200, `/api/push/nokkel` redirects).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `"Push-varsler til iPhone"`.

---

### Task 7: Scheduler (morning, dinner, Friday, evening, Sunday)

**Files:**
- Modify: `varsler.py`, `app.py` (start thread at import when `os.environ.get("PLANLEGGER", "1") == "1"`; settings routes)
- Create: `tests/test_planlegger.py`

**Interfaces:**
- Consumes: Tasks 3–6; existing `withings_synk()` and `oura_synk()` in `app.py` (passed in as callables to avoid importing `app`).
- Produces in `varsler.py`:
  - `STANDARD_TIDER = {"morgen": "07:00", "middag": "15:30", "helg": "15:00", "kveld": "21:00", "sondag": "18:00"}`
  - `hent_tider(conn) -> dict` / `lagre_tider(conn, tider: dict) -> dict` (validate `HH:MM`, unknown keys ignored, missing keys default)
  - `kjor_planlagte_jobber(conn, naa: datetime, synk=None, sender=None) -> list[str]` — returns the job types that fired. For each job whose time is ≤ `naa` < time+90 min, whose weekday rule matches (helg: Friday; sondag: Sunday; others daily), and whose `(dato, type)` is not in `varsel_logg`: insert into `varsel_logg` **first** (INSERT OR IGNORE; skip if not inserted), then run it:
    - morgen: call `synk()` (errors ignored), build today's `dagsmelding` like `/api/i-dag`, push its tittel + first sentence of tekst
    - middag: push `"Middag i dag: <navn> (<minutter> min)"`; skip on Sat/Sun (plan has Mon–Fri dinners)
    - helg: push `"Helgeplan"` / `"Hvor mange enheter skal du ha i helgen? Bestem det nå, mens du er edru."`, url `/#helg`
    - kveld: only if today has no `dagssjekk` → push `"Kryss av dagen"` / `"Fastet, alkohol, trent, syk – tar 5 sekunder."`
    - sondag: create next week's plan with `coach.lag_ukeplan_med_claude`, store `helg_oppsummering` for this week in `helgeplan.oppsummering`, push `"Ny uke klar"` / `"Ukemeny, handleliste og treningsdager er klare."` url `/#mat`
  - `start_planlegger(db_path, synk) -> threading.Thread` — daemon thread; every 60 s opens its own connection, calls `kjor_planlagte_jobber(conn, datetime.now(ZoneInfo("Europe/Oslo")), synk)`, catches and prints any exception, never dies
- Routes: `GET /api/innstillinger/varsler` → tider; `POST` → saved tider (400 on bad format).

- [ ] **Step 1: Write failing tests** (fake `sender` collecting calls, `sporr_claude` raising):
```python
def test_morgen_sendes_en_gang_i_vinduet(db):
    t = datetime(2026,11,18,7,20,tzinfo=OSLO)
    assert "morgen" in varsler.kjor_planlagte_jobber(db, t, synk=lambda: None, sender=fake)
    assert "morgen" not in varsler.kjor_planlagte_jobber(db, t + timedelta(minutes=1), synk=lambda: None, sender=fake)

def test_morgen_sendes_ikke_for_sent(db):
    assert "morgen" not in varsler.kjor_planlagte_jobber(db, datetime(2026,11,18,23,0,tzinfo=OSLO), sender=fake)

def test_kveld_hoppes_over_nar_dagen_er_krysset_av(db): ...
def test_helg_bare_fredag(db): ...           # Thursday 15:10 → not fired; Friday 15:10 → fired
def test_sondag_lager_neste_ukeplan(db): ... # Sunday 2026-11-22 18:05 → ukeplan row for 2026-11-23 exists
def test_synk_feil_stopper_ikke_morgen(db): ...  # synk raises → morgen still fired
def test_ugyldig_tid_400(client): ...
```
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `"Planlagte varsler"`.

---

### Task 8: Frontend

**Files:**
- Modify: `static/index.html`, `static/app.js`, `static/style.css`
- Create (scratchpad only, not committed): Playwright check script

**Interfaces:**
- Consumes: routes from Tasks 2, 5, 6, 7; existing Oversikt/Vekt code untouched (`tegnGraf`, `tellOpp`, card pattern).

Load the `frontend-design` skill before this task. Bottom tabs: **I dag · Mat · Oversikt · Historikk** (Fysio and all exercise UI/modals removed; Vekt stays inside Oversikt as today).

- **I dag**: coach card (tittel big; when `treningsdag`, an accent-colored banner "I DAG ER DET TRENINGSDAG"); dagssjekk card with four pill toggles `Fastet · Alkohol · Trent · Syk` (save on tap, no save button; when Alkohol is on, a number field "Antall enheter" appears; optional note field, saved on blur); "Alkoholfrie hverdager på rad: N"; dagens middag card (tap → Mat tab); helg card (Fri–Sun, or `#helg` hash): if no plan → number input + "Lagre plan" → shows tips; on Sunday after oppsummering exists → shows it; buttons "Spør coachen" (opens chat bottom-sheet using the existing modal pattern) and "Det er vanskelig nå" (shows the text in a calm card).
- **Mat**: 5 dinner cards (dag, navn, minutter, beskrivelse, ingredients collapsed) each with "Bytt"; lunsj-prep card + brødtips; handleliste with tap-to-strike checkboxes (strike state kept in `localStorage` per week, try/catch).
- **Historikk**: list of `dagsstatus` with four small badges + enheter + notat; stats tiles from Task 2.
- **Varsler**: on I dag, if `Notification.permission !== "granted"`, a card "Slå på varsler" → registers `/sw.js`, requests permission (must be in the tap handler), subscribes with the VAPID key, POSTs to `/api/push/abonner`, then calls `/api/push/test`. If `PushManager` is missing (not opened from home screen), show: "Åpne appen fra hjemskjermen for å få varsler." Small "Varseltider" settings link opens a sheet with five time inputs → `POST /api/innstillinger/varsler`.
- Handle hash `#helg` / `#mat` on load to jump to the right place.

- [ ] **Step 1: Implement** HTML/JS/CSS.
- [ ] **Step 2: Run locally** against a disposable DB copy: `$env:DB_PATH="<scratchpad>\test.db"; $env:PLANLEGGER="0"; python app.py`, seed 3 weeks of dagssjekk + vekt via API.
- [ ] **Step 3: Playwright check** at 402×874 in light and dark: each tab screenshot, zero console errors, toggling Alkohol shows the units field and survives reload, Bytt changes a dinner, chat sheet opens and returns the reserve reply, last card not hidden by the tab bar (scroll + viewport screenshot, not full-page). Look at every screenshot.
- [ ] **Step 4: Kill stray python processes** (PowerShell), **commit** `"Nytt grensesnitt: I dag, Mat, Historikk, varsler"`.

---

### Task 9: Ship

**Files:**
- Modify: `README.md` (plain-language: what the app does now, `ANTHROPIC_API_KEY`, how to turn on notifications, costs)

- [ ] **Step 1: Full test run** `python -m pytest tests -v` → all PASS.
- [ ] **Step 2: Ask Eivin** to download a backup from the app first (existing backup button) and confirm `ANTHROPIC_API_KEY` is set on Railway.
- [ ] **Step 3: Merge and push**: `git checkout main && git merge --no-ff livscoach && git push`. Railway auto-deploys.
- [ ] **Step 4: Verify live** (poll; allow ~60 s): `https://trening.flibber.no/sw.js` → 200; logged-in `/api/i-dag` returns `kilde: "claude"`; `/api/oversikt` still shows his real Withings/Oura data; old history visible in `/api/historikk`.
- [ ] **Step 5: Walk Eivin through** on the iPhone: open from home screen → "Slå på varsler" → allow → test notification arrives.
- [ ] **Step 6: Update project memory** (`project_treningsapp.md`) with the new shape of the app.
