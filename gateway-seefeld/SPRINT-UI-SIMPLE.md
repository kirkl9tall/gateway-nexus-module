# Sprint UI-1: A gateway a doctor can use alone

**Goal:** a doctor or medical assistant with no technical training can connect an analyzer, see that results arrive, and fix the common problems, in their own language, without calling a technician.

**Duration:** 3 weeks, 3 milestones (one per week, each one shippable).
**After this sprint:** the core reliability work in [README-RELIABILITY.md](README-RELIABILITY.md).

---

## 0. Already done (before the sprint)

**Story 0: the language holds on every page** ✅

- **Before:** about 8% of the text was translated, by a JavaScript dictionary. Login, setup and the wizard never loaded it, so pages fell back to Italian.
- **Now:**
  - The server renders every page translated ([webui/i18n.py](webui/i18n.py)).
  - The language is stored in a cookie, so it holds on every page.
  - If no language has been chosen: practice language (wizard step 1), then the browser's language, then Italian.
  - One catalog per language: [webui/locale/de.json](webui/locale/de.json), `fr.json`, `en.json`.
  - The picker shows full language names (Italiano / Deutsch / Français / English) on every page, including login and the wizard.
  - The wizard's "interface language" choice now actually changes the interface.
- **Fully translated now:** menu, header, login, setup, wizard frame, Overview (including messages built in JavaScript).
- **Guard:** [tests/test_i18n.py](tests/test_i18n.py) fails if a key has no DE/FR/EN translation, if placeholders differ, or if a converted page contains hard-coded text.
- **Tool:** `python tools/i18n_keys.py` lists the missing translations.

**Rule for every story below:** a page counts as done only when it's added to `CONVERTED` in `tests/test_i18n.py` and the test passes.

---

## 1. Who we design for

**Persona: Dr. Anna, GP, and Marco, medical assistant (MPA)**
- Uses the practice software and email every day. Has never heard of "port", "MLLP", "HL7" or "DLQ".
- Opens the gateway page only when something seems wrong, or when a new analyzer arrives.
- Works on a practice PC with a 22–24" screen, sometimes a tablet at the lab bench.
- Reads German, French or Italian; sometimes English.
- **Question 1:** "Are today's results arriving in my software?"
- **Question 2:** "If not, what do I do?"
- **Question 3:** "How do I connect the new machine?"

**The technician** (installer / Jerumed support) still needs every detail: ports, protocols, traces, config. That moves to **Technician mode** (story H1) and doesn't need translating.

---

## 2. Design rules (apply to every screen)

| Rule | Concretely |
|---|---|
| **Big** | Base text 18 px (today 15 px), headings ≥ 28 px, buttons ≥ 48 px high, clickable areas ≥ 44×44 px |
| **One thing per screen** | One clear title stating the situation, one primary (blue) button. Secondary actions are plain links |
| **Traffic light** | Every status is 🟢 *works* / 🟠 *needs attention* / 🔴 *not working*, always with **words** next to the color (color-blind users) |
| **No jargon** | Use the glossary below. Technical terms only in Technician mode |
| **Say what to do** | Every problem message = what happened + what to do + one button. Never just "Error" |
| **Nothing is lost** | Always reassure when it's true: "No result is lost" |
| **Works offline** | No Google Fonts or other external files: the Pi in a practice is often offline. Fonts are stored on the Pi |
| **Readable** | WCAG AA contrast (4.5:1), visible keyboard focus, `lang` attribute correct |
| **4 languages** | All text through `t()`/`T()`. German, French and English checked by a native speaker before release |

### Glossary: words the doctor sees

| Technical / today | Doctor sees (IT) | DE | FR | EN |
|---|---|---|---|---|
| Gestionale / PIS / LIS | Software dello studio | Praxissoftware | Logiciel du cabinet | Practice software |
| DLQ / coda morta | Risultati da rispedire | Noch zu sendende Ergebnisse | Résultats à renvoyer | Results waiting to be sent |
| Device / analizzatore | Apparecchio | Gerät | Appareil | Machine |
| MLLP / TCP / porta | *(hidden)* | | | |
| Servizio attivo/fermo | Il gateway funziona / è fermo | | | |
| Frame / trace / log | *(Technician mode only)* | | | |
| Uptime, P95, breaker | *(Technician mode only)* | | | |

---

## 3. New structure (navigation)

**Doctor mode** has 4 menu entries, big and with icons:

```
┌─────────────────────────────────────────────────────────────────────┐
│  JerumedNexus           🟢 All good          Deutsch ▾    Anna ⎋   │
├──────────────┬──────────────────────────────────────────────────────┤
│              │                                                      │
│  🏠 Home     │                                                      │
│              │                                                      │
│  🩸 Machines │                                                      │
│              │                                                      │
│  📄 Results  │                                                      │
│              │                                                      │
│  ❓ Help     │                                                      │
│              │                                                      │
│  ─────────   │                                                      │
│  🔧 Technician                                                      │
└──────────────┴──────────────────────────────────────────────────────┘
```

**Technician mode** (admin role, or support PIN): today's full menu. That's Configuration, Users, Licence, Logs and trace, Frame Inspector, Wire Replay, Topology, Fleet, Compare, Updates and service control.

---

## 4. Milestone 1 (week 1): Foundations and Home

### A1: Bigger, clearer design tokens · 3 pts
- **What:**
  - `base.html`: `html { font-size: 18px }`.
  - New button sizes (`.btn` min-height 48 px, `.btn-lg` 56 px).
  - Status colors with AA contrast: green `#2e7d4f`, orange `#b35c00`, red `#b3261e`.
  - Visible focus ring 3 px.
- **Acceptance:** all text is readable at 1 m from a 24" screen. Contrast checker passes AA on every color pair.
- **Files:** `webui/templates/base.html`, `login.html`, `wizard/base.html`

### A2: Fonts and assets stored on the Pi · 2 pts
- **What:**
  - Download Barlow and Barlow Condensed (OFL licence) into `webui/static/fonts/` and use `@font-face`.
  - Remove `fonts.googleapis.com` from base, login, setup and wizard.
- **Acceptance:** with the network unplugged, pages look the same. No external request in the browser's network tab.

### A3: Shared UI components · 5 pts
- **What:** Jinja macros in `webui/templates/_ui.html`:
  - `status_banner(level, title, text, button)`: the big traffic-light sentence
  - `big_number(value, label)`
  - `todo_item(level, title, text, button)`
  - `step_guide(steps)`: numbered steps with picture and text
  - `big_button(label, href, primary=True)`
- **Acceptance:** Home, Machines and Help are built only from these macros. They look identical in all 4 languages (long German words must not overflow, so use `hyphens: auto` and `overflow-wrap`).

### H1: Doctor mode / Technician mode · 3 pts
- **What:**
  - Doctors (viewer/operator role) see only the 4-item menu.
  - Admin sees a "Technician" switch. Technician pages return 403 for doctors, not just hidden.
  - **Bug today:** Frame Inspector is visible to doctors. Move it to technician mode.
- **Acceptance:**
  - A viewer opening `/inspect`, `/replay`, `/topology`, `/logs` or `/config` directly gets a friendly "This page is for the technician" page with a "Back to Home" button.
  - Test in `tests/test_portali_medico_tecnico.py`.

### B1: New Home for doctors · 5 pts
**What it shows:**
```
  🟢  Everything works.                       ← one sentence, 36 px
      Last result 10:42 from Sysmex XQ-320

  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │     23       │ │     23       │ │      0       │
  │ results today│ │ sent to your │ │ waiting to   │
  │              │ │ software     │ │ be sent      │
  └──────────────┘ └──────────────┘ └──────────────┘

  To do                                         ← only if something to do
  🟠 2 results could not be sent to Tomedo.        [ Send again ]
     No result is lost. We'll keep trying.
  🔵 A new machine was plugged in (USB).           [ Set it up ]

  Today's results                               ← patient ID, machine, time, ✓/✗
```

**States the headline must cover**, each with its own sentence and button:
1. Everything works.
2. Results waiting to be sent: "Send again".
3. A machine has been silent for a long time: "Check the machine".
4. Gateway stopped: "Start the gateway". The doctor is allowed to start it.
5. Practice software unreachable: "What to check".
6. New USB machine detected: "Set it up" (links to the C flow).
7. First start, no machine yet: "Connect your first machine".

**Moves to Technician mode:** uptime, P95, 24h chart, service stop/restart, update check, raw events.

**Acceptance:**
- Each state is covered by a test that fakes `status.json`.
- Works in all 4 languages.
- `dashboard.html` stays in `CONVERTED`.

### Milestone 1 demo
A doctor logs in in German, sees "Alles funktioniert", unplugs the network to the practice software and sees an orange "Ergebnisse warten" with one button.

---

## 5. Milestone 2 (week 2): Connect a machine alone

This is the heart of the sprint: **"Connect a machine" in at most 4 screens**, with the gateway doing the technical work.

### C1: Connection guides in the device catalog · 5 pts
- **What:** extend each `config/devices/*.yaml` (33 profiles) with a `guide:` block:
  ```yaml
  guide:
    cable: usb | network | serial_usb     # which picture to show
    picture: sysmex_xq320.svg             # line drawing, webui/static/devices/
    steps:                                # Italian source text, translated via catalog
      - "Sull'apparecchio apri Menu → Impostazioni → Comunicazione."
      - "Come indirizzo host scrivi {gateway_ip}, come porta {port}."
      - "Salva e riavvia l'apparecchio."
    test: "Misura un campione di controllo o premi «Invia di nuovo» sull'ultimo risultato."
  ```
- **First 8 devices with a full guide:** the ones in use or in the dashboard. That's LOC-200, Sysmex XP-300, Sysmex XQ-320, pocH-100i, Horiba Microsemi CRP, UC-1000, Seamaty SMT-120, Cobas b101.
- **The other 25:** a generic guide ("Ask your supplier to set host {gateway_ip} port {port}").
- **Acceptance:** `tests/test_registry_legge_il_catalogo.py` checks every profile has a valid `guide`, and the guide texts are in the catalogs.

### C2: Screen 1, "Which machine?" · 3 pts
```
  Connect a machine                                   Step 1 of 4

  Which machine do you want to connect?
  [ 🔍 Search: "sysmex"                ]

  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
  │ [image] │ │ [image] │ │ [image] │ │ [image] │
  │ Sysmex  │ │ Sysmex  │ │ pocH-   │ │ Horiba  │
  │ XQ-320  │ │ XP-300  │ │ 100i    │ │ CRP     │
  └─────────┘ └─────────┘ └─────────┘ └─────────┘
  My machine is not in the list →  (opens Help with the support number)
```
- **What:**
  - Big tiles with a picture and name, plus a search box.
  - If a USB device was just detected, it is **suggested first**: "We found a new machine: Sysmex XP-300?" [Yes] [No].

### C3: Screen 2, "How is it connected?" · 3 pts
- **What:**
  - Two big pictures: **USB cable** / **Network cable (LAN)**. Only the options the device supports are shown, from the catalog.
  - **USB:** "Plug the cable into the grey box now." The page waits and turns green when the gateway detects it, reusing `/api/devices/discovered`.
  - **Network:** the gateway picks a free port by itself. The doctor never types a port.

### C4: Screen 3, "Set up the machine" · 3 pts
- **What:** the catalog steps as big numbered cards, with the Pi's IP and the port **pre-filled in large type** and a "Copy" button.
  ```
  1  On the machine, open  Menu → Settings → Communication
  2  Host address:   192.168.1.50      Port:  5006
  3  Save and restart the machine
                                                [ I've done it → ]
  ```
- **The gateway does the rest by itself:**
  - Saves the device in `config/devices/`.
  - Opens the port in the firewall (see C6).
  - Restarts the reader. The doctor never presses "Restart service".

### C5: Screen 4, "Send a test result" · 5 pts
```
  Send a test result from the machine now.
  ⏳ Waiting for the first result…   (animated, up to 5 minutes)

  → 🟢 It works! We received a result at 10:42
       and sent it to Tomedo.                     [ Done ]

  → 🔴 Nothing arrived after 5 minutes.
       Let's check together:
       ☐ Is the cable plugged in on both sides?
       ☐ Is the address on the machine exactly 192.168.1.50 : 5006?
       ☐ Is the machine switched on?
       [ Try again ]     [ Call support · code 4F2A ]
```
- **What:**
  - Uses `connected` / `last_seen` from `status.json`.
  - New API `GET /api/devices/<id>/first-result`.
  - The support code is a short ID of an automatic diagnostic snapshot (reuse `verifica_impianto.py`), so support sees the problem without asking questions.
- **Acceptance:** end-to-end test with `tests/mock_lis.py` and a fake analyzer: from screen 1 to 🟢 without touching YAML or the terminal.

### C6: Firewall opens by itself · 3 pts
- **Today:** a new network device needs `sudo firewall-sync.sh` run by hand. The web UI has no root rights, so the machine "sends but nothing arrives".
- **What:** a systemd `.path` unit watches `config/devices/` and runs `firewall-sync.sh` as root when it changes. No sudo from the web UI.
- **Also:** make `firewall-sync.sh` find the venv next to the script (also fixes 5 of the failing tests).
- **Files:** `scripts/jerumednexus-firewall-sync.path`, `.service`, `debian/postinst`

### D1: "Machines" page for doctors · 3 pts
- **What:** one card per machine, with no ports or protocols visible.
  ```
  🟢 Sysmex XQ-320         Last result 10:42                    [ Test ]
  🟠 LOC-200               No results since yesterday 17:05    [ Check ]
  ⚪ Cobas b101            Not connected                        [ Connect ]
                                          [ + Connect a new machine ]
  ```
- **Technician mode:** today's full `analyzers.html` (USB scan, edit form, ports).
- **Acceptance:** `analyzers.html` doctor part in `CONVERTED`. "Check" opens screen 4 (C5) for that machine.

### Milestone 2 demo
Marco connects a (simulated) Sysmex over the network in French in under 5 minutes. Nobody helps, there's no terminal, and he types no port.

---

## 6. Milestone 3 (week 3): Results, first start, help, polish

### E1: Results page · 3 pts
- **What:**
  - Search by **patient ID** or **date** with big fields; today is shown by default.
  - Each row: time, patient ID, machine, ✓ sent / ✗ not sent.
  - Clicking a row shows the values in a readable table, never raw HL7. "Show HL7" stays in Technician mode.

### E2: "Results waiting to be sent" (today: DLQ) · 3 pts
- **What:**
  - Explanation sentence: "These results could not be delivered to {software}. No result is lost."
  - One big button **"Send all again"**, plus a per-row "Send again".
  - After sending: "✓ 5 of 5 sent".
  - The page becomes visible to doctors (today technicians only), because "send again" is a doctor task.
- **Acceptance:** `dlq.html` in `CONVERTED`. Operator role can resend; viewer cannot.

### F1: First start in 4 steps instead of 7 · 5 pts

| Today | New |
|---|---|
| 1 Practice · 2 Admin · 3 Network · 4 Analyzer · 5 Practice software · 6 Backup · 7 Check | **1 Language & practice name** · **2 Your password** · **3 Your practice software** (pick from logos: Tomedo, Vitomed, …; test button) · **4 Done → "Connect your first machine"** (opens the C flow) |

- **Network:** the Pi's IP is detected automatically. Manual IP moves to Technician mode.
- **Backup:** sensible default (local, daily). Settings move to Technician mode.
- **Removed from doctor screens:** MSH-6, GPG key, "kebab-case", timezone (default Europe/Zurich, editable by the technician).
- **Acceptance:**
  - All wizard steps in `CONVERTED`.
  - First start → first test result in under 10 minutes in a usability test.
  - Existing tests `test_configurazione_iniziale.py` and `test_installer_protegge_config.py` still pass.

### G1: Help page · 2 pts
- **What:**
  - Big phone number and email.
  - "Check my installation" button (today: Verifica impianto), with the result in plain sentences and traffic lights.
  - 5 FAQ in plain words: no results arrive / new machine / practice software changed / forgot password / gateway after a power cut.
  - "Support code" for remote help.

### I1: Translation review and clean-up · 3 pts
- **What:**
  - A native speaker reviews DE, FR and EN in the catalogs (Swiss German style: «»; no ß).
  - Remove the legacy fallback in `static/i18n.js` once every doctor page is converted.
  - Delete the unused `webui/locale/*/LC_MESSAGES/*.po/.mo`.
- **Acceptance:** `tools/i18n_keys.py` shows 0 missing. No Italian visible in DE/FR/EN on any doctor page (automated crawl test).

### I2: Usability test with 3 real users · 2 pts
- **What:** one GP, one MPA and one non-Italian speaker each do 3 tasks with no help, while we watch:
  - "Are today's results in your software?"
  - "Connect this machine."
  - "Two results didn't arrive: fix it."
- **Success:** 3/3 tasks completed by each user, under 10 min total, no question to us.
- **After:** findings become stories for the next sprint.

---

## 7. Summary

| Milestone | Stories | Points |
|---|---|---|
| 1: Foundations + Home | A1, A2, A3, H1, B1 | 18 |
| 2: Connect a machine alone | C1, C2, C3, C4, C5, C6, D1 | 25 |
| 3: Results, first start, help, polish | E1, E2, F1, G1, I1, I2 | 18 |
| **Total** | **18 stories** | **61** |

**Definition of Done (each story):**
- [ ] Text through `t()`/`T()`, page in `CONVERTED`, `tests/test_i18n.py` green
- [ ] Checked in all 4 languages at 1280 px and 1024 px (tablet); long German words don't break the layout
- [ ] No jargon from the glossary on doctor screens
- [ ] Every problem message says what to do, with one button
- [ ] Works with the network unplugged (no external assets)
- [ ] Keyboard usable, visible focus, AA contrast
- [ ] Automated test for the new behaviour; full test suite green
- [ ] Tried on a real Raspberry Pi (page load < 1 s on Pi 4 over LAN)

## 8. Risks

| Risk | Mitigation |
|---|---|
| Pictures of analyzers: copyright | Use simple line drawings we make ourselves (SVG), not manufacturer photos |
| Analyzer menus differ by firmware | Guide text says "usually"; a "Can't find it?" link goes to support with the code |
| Firewall change needs root | systemd path unit (C6), never sudo from the web UI |
| Translations sound machine-made | Native review (I1) before release; Swiss terms (Praxissoftware, «»). Note: the DE/FR/EN catalogs written for Story 0 have **not** been native-reviewed yet |
| Doctor mode hides something the doctor needs | Usability test (I2); "Technician" link always present |
| Core still loses data on power cut | Fixed right after this sprint (README-RELIABILITY.md phase 1). UI messages like "No result is lost" become fully true then |
