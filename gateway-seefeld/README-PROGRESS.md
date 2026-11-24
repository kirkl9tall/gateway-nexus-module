# What we have done: Web UI redesign (November 2026)

This file records the work done on the gateway's web interface between **23 and 24 November 2026**: what changed, why, how to try it, and what is still open.

| Document | What it covers |
|---|---|
| [README-RELIABILITY.md](README-RELIABILITY.md) | The core reliability problems. **Still open, next step** |
| [SPRINT-UI-SIMPLE.md](SPRINT-UI-SIMPLE.md) | The full UI sprint plan |
| [docs/UI-DESIGN-ARENA.md](docs/UI-DESIGN-ARENA.md) | How the design was chosen, and the design tokens |

---

## Quick start: copy and paste

All commands run from the `gateway-seefeld` folder:

```bash
cd ~/Desktop/nexus-gateway/gateway-seefeld
```

### 1. Install, once

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. Start the web UI on localhost

```bash
.venv/bin/python -m flask --app webui.app run --host=127.0.0.1 --port=8088 --debug
```

- **Open http://127.0.0.1:8088.** The first time, the setup wizard asks you to create the admin password.
- **This terminal stays busy** while the web UI runs. Stop it with **Ctrl+C**.
- **"Address already in use"** means the web UI is already running: just open the address above.
- **On the Raspberry Pi** the service uses `.venv/bin/python -m webui.serve` instead (port 8080, and 8443 for HTTPS).

### 3. Start the simulation (fake machines + simulated Tomedo)

Open a **second terminal**:

```bash
cd ~/Desktop/nexus-gateway/gateway-seefeld
demo/demo.sh start
```

This starts:

| What | Detail |
|---|---|
| Simulated **Tomedo** | receives the results on `127.0.0.1:12575` and answers "accepted" |
| The **real gateway** (`main.py`) | with the test config `config/gateway.yaml` |
| Fake **Seamaty SMT-120** | sends a real HL7 result every 20 s (port 6000) |
| Fake **Horiba Microsemi CRP** | sends a real HL7 result every 35 s (port 5004) |

The test config also contains two machines that show the other states:

- **Seamaty SD3:** configured but silent, shows "Never heard from"
- **UC-1000:** points to a USB cable that isn't plugged in, shows "Cable not detected"

The Overview updates by itself every 15 s.

### 4. Try things during the simulation

```bash
demo/demo.sh status        # what is running
demo/demo.sh tomedo-down   # Tomedo unreachable: the Overview turns red, results wait in "To resend"
demo/demo.sh tomedo-up     # Tomedo back
```

You can also use the **on/off switch** in the **Gateway** box of the Overview (operator or admin user) to turn the gateway off, on, or restart it.

Logs:

| Log | File |
|---|---|
| Simulators | `demo/logs/` |
| Gateway started by the switch or the script | `logs/gateway.stdout.log` |
| Gateway's own log | `logs/gateway.log` |

### 5. Stop everything

```bash
demo/demo.sh stop          # fake machines, gateway, simulated Tomedo
```

Then press **Ctrl+C** in the web UI terminal.

> **Before installing on a real Raspberry Pi:**
> - **Replace `config/gateway.yaml`.** It is the test config created for this simulation.
> - **Turn off `config/devices/sysmex_uf1000i.yaml`** (`enabled: false`). It was switched on while testing the "Add a machine" page.

---

## 1. The goal

The gateway is used by **doctors and medical assistants who are not technical**. The interface had to become:

- **simple and big:** 18 px text, buttons at least 48 px high, plain words
- **in their language:** Italian, German, French and English, all equally complete
- **honest:** say what is wrong and what to do, with one button
- **two levels:** doctors see only what they need, and every technical detail moves to a **"For the technician"** section at the **bottom** of each page, visible to the admin only

---

## 2. What changed, page by page

### Language (all pages)

- **Before:** about 8 % of the text was translated, by a JavaScript dictionary. Login, setup and the wizard always stayed in Italian, so changing page "fell back" to Italian.
- **Now:**
  - **Server-side translation** ([webui/i18n.py](webui/i18n.py)): pages arrive already translated.
  - **The language is stored in a cookie**, so it holds on every page and after login.
  - **Without a chosen language:** the practice language from the wizard is used, then the browser's language.
  - **The picker shows full names** (Italiano / Deutsch / Français / English) on every page, including login and the wizard.
  - **The wizard's "interface language" now really changes the interface.**
  - **Catalogs:** [webui/locale/de.json](webui/locale/de.json), `fr.json`, `en.json`, with **583 phrases each**, all complete.
- **Fixed:** a bug in the fallback translator ([webui/static/i18n.js](webui/static/i18n.js)) that froze the browser tab ("Page unresponsive").

### Look and layout (all pages)

- **Font:** Atkinson Hyperlegible, designed for low-vision readers. It is **stored on the Pi** (`webui/static/fonts/`), so it works offline; Google Fonts was removed.
- **Status colours** always come with an **icon shape and a word**, never colour alone. Every text colour meets WCAG AA contrast.
- **Menu:**
  - doctors see 4 items: **Overview, Machines, Check installation, Results**
  - technician tools sit below, for the admin only
  - Frame Inspector moved there
- **Responsive** from phone (360 px) to large screens. On small screens the menu becomes a row you can swipe sideways.
- **Dark mode** redesigned: every text is readable, minimum contrast 5.2:1.

### Overview ([dashboard.html](webui/templates/dashboard.html), [webui/overview.py](webui/overview.py))

1. **One sentence** answers "is it working?", for example "Everything works" or "Tomedo is not receiving results", with one button ("Find the problem", "Turn the gateway on"…).
2. **The path of a result:** Machines (e.g. "4 of 5 active", one bar per machine) → **Gateway on/off** → each **practice software** (Tomedo…) with its own status. Dots move along the arrows while data flows; a red break shows where the chain stops.
3. **Today:** a ring gauge (analyses received / delivered), and a bar chart of **analyses per day for the last 7 days**.
4. **Your machines:** one card per machine. States are **Connected**, **Waiting for analyses**, **Never heard from**, **Cable not detected**, **Gateway off**, with today's count and the time of the last result.
5. **Where results go:** each practice software with how many were delivered today and the last delivery.
6. **For the technician (bottom, closed):** errors, total, uptime, latency, 24 h chart, recent events, start/stop, updates, USB devices to assign.

7. **On/off switch** in the Gateway box (operator and admin): turn the gateway on or off, or restart it. Turning off asks for confirmation. Read-only doctor accounts only see the state.

The live part refreshes every 15 s.

### Machines ([analyzers.html](webui/templates/analyzers.html))

- **The machine cards**, same as on the Overview.
- **A large "Connect a new machine" panel** with 3 big steps and an **"Add a machine"** button.
- **For the technician (bottom, closed), built from the real configuration:**
  - USB cables the gateway sees, each with a "Set up a machine" button
  - configured machines in a table: status, cable/port, protocol, last result, **Edit** and **Turn off**
  - values each machine sends, chosen from a dropdown
- **Removed:**
  - the 10 hard-coded cards, whose "Inattivo" label overlapped the text
  - the duplicate tabs
  - the 33-card catalogue
  - the old pop-up form

### Add a machine ([device_form.html](webui/templates/device_form.html))

1. **Which machine?** Big tiles for every analyzer in the catalogue, plus a search box and an "Another machine" tile. A machine just plugged in by USB is **suggested automatically**.
2. **How is it connected?** USB or network, **pre-selected from the machine's profile**.
   - **USB:** choose from the cables the gateway really sees.
   - **Network:** the address and port to type on the analyzer are shown in large text with a Copy button. The port is **chosen automatically** so it never clashes with another machine.
3. **Name:** pre-filled.

Protocol, ID, baud rate and listen address are filled in automatically and kept under "Advanced settings". After saving, the gateway restarts and the page says "Now run a test analysis".

**Also fixed:** saving no longer wipes a machine's protocol settings (e.g. the Sysmex `astm_mode`). The new endpoint `POST /api/devices/<id>/connect` merges instead of replacing, and refuses ports already in use and non-`/dev/` paths.

### Check installation ([verifica.html](webui/templates/verifica.html), [webui/check_view.py](webui/check_view.py))

- **A big "Check now" button.**
- **The answer comes as 5 plain questions,** each with **Yes/No** and a **"What to do"**:
  - Is the gateway on?
  - Can the machines reach it?
  - Does the practice software answer?
  - Do results reach the right patient?
  - Is there room to keep results?
- **The original technical list** (with commands) is in the bottom technician section.
- **Doctors can now run the check:** the viewer role is allowed, and it changes nothing.

### Results ([results.html](webui/templates/results.html), [webui/results_view.py](webui/results_view.py))

- **The list:**
  - big search by patient or sample ID
  - big filter buttons: Today / Yesterday / 7 days / 30 days / All; All / Delivered / Not delivered; plus a machine dropdown
  - one large row per result: time, patient, machine, number of values, "Sent to Tomedo" / "Not sent"
- **Click a row** and a panel opens (full screen on phones) with:
  - patient, machine, time received
  - **where it was sent**: ✓ received / ✕ not received, with the reason
  - **the values**: name, value + unit, reference range, **↑ high / ↓ low** markers
  - **"Send again"** if a delivery failed (operator and admin)
  - for the admin: the exact HL7 message sent

### Technician pages (menu section "For the technician")

All technician pages now share the same design, are translated into the 4 languages, and are guarded by `tests/test_i18n.py`:

| Page | What changed |
|---|---|
| **To resend** ([dlq.html](webui/templates/dlq.html)) | Big rows like Results; "Rejected by the software" vs "Not reachable"; **"Send all again (n)"**; message preview on demand |
| **Logs** ([logs.html](webui/templates/logs.html)) | Log / Trace as big tabs; translated legends; uses the page colours (also in dark mode) |
| **Frame Inspector** ([index](webui/templates/frame_inspector_index.html), [detail](webui/templates/frame_inspector.html)) | Same table style and status chips; "from the machine → sent" comparison; fixed a template variable that hid the translation function |
| **Configuration** ([config.html](webui/templates/config.html)) | Same form and behaviour (all existing tests kept), numbered sections, plain labels, normal buttons instead of neon ones |
| **Users** ([users.html](webui/templates/users.html)) | Roles in plain words (Doctor or assistant / Practice / Technician); 2FA in a proper dialog; user names escaped |
| **Licence** ([license.html](webui/templates/license.html)) | One status sentence, one card for the gateway, one form for activate **and** renew (was two); server errors shown as text, not HTML |
| **Topology** ([topology.html](webui/templates/topology.html)) | Works in light and dark; names drawn as text, not HTML |
| **Wire Replay** ([wire_replay.html](webui/templates/wire_replay.html)), **Archive** ([device_archive.html](webui/templates/device_archive.html)) | Same table style, readable dates, translated |

### First start, login and setup

- **Login, setup and the wizard frame** are translated and carry the language picker.
- **The wizard steps themselves** are not redesigned yet (see section 6).

---

## 3. Small changes in the core

| Change | Why |
|---|---|
| `src/gateway.py`: on stop, writes `status.json` with `running=false` | The web UI shows "gateway off" immediately, without waiting for the status to age out |
| "Gateway on/off" trusts the gateway's own fresh status when systemd is not available | On a PC (or any install not run as a service) the page wrongly said "off" while it was running |
| `src/common/history.py`: new read-only queries (`daily_counts`, `activity_since`, `list_results`, `get_entry`, …) | Feed the Overview and Results pages |
| Service errors no longer show raw text like "sudo: a terminal is required" to doctors | They get "Switch the grey box off and on again, or call support"; details go to the browser console |
| USB device names in the dashboard are escaped | They were inserted as raw HTML |
| `src/gateway.py`: writes `status.json` as soon as it starts | The page shows "on" right away instead of after the first 5-minute health check |
| New [webui/gateway_process.py](webui/gateway_process.py): when the systemd unit is **not** installed (PC, demo, manual install), the switch starts/stops `main.py` itself, and only the gateway of this folder | On a PC the Start button failed with "sudo: a terminal is required" because there is no service |
| With the systemd unit installed (Raspberry Pi), the switch still uses `systemctl` | No change on real installs |

The **reliability problems** listed in [README-RELIABILITY.md](README-RELIABILITY.md) (results acknowledged before being stored, missing or partial ACK counted as success, partial delivery lost, …) are **not fixed yet**. They are the next step.

---

## 4. How to run it

See **[Quick start](#quick-start-copy-and-paste)** at the top of this file: install, web UI, simulation, stop.

---

## 5. Tests

```bash
.venv/bin/python -m pytest -q
```

- **New test files:**
  - [tests/test_i18n.py](tests/test_i18n.py): every phrase translated, same placeholders, no untranslated text on converted pages, language kept across pages, the freeze cannot come back
  - [tests/test_overview.py](tests/test_overview.py): machine and destination states, headline priorities, Check page grouping, pages render in all languages and roles
  - [tests/test_device_connect.py](tests/test_device_connect.py): connecting a machine keeps protocol settings, ports in use are refused
  - [tests/test_results_page.py](tests/test_results_page.py): filters, detail, high/low, resend rights, translations
  - [tests/test_gateway_switch.py](tests/test_gateway_switch.py): the on/off switch uses systemctl when the service exists and the process otherwise; read-only users cannot switch
- **Result on 24.11.2026:** 439 passed, 11 failed.
- **10 of the failures come from the development PC, not the code:** the folder is not a git repo (`git ls-files`), and `scripts/firewall-sync.sh` looks for the venv only in `/opt/jerumednexus`.
- **1 failure is local test data:** `config/devices/sysmex_uf1000i.yaml` was turned on from the "Add a machine" page while testing. Catalogue profiles must ship turned off: set `enabled: false` (or turn it off in Machines → technician section) before packaging.

### Translating new text

Write Italian in the template inside `{{ t("…") }}` (or `T("…")` in JavaScript), then run:

```bash
.venv/bin/python tools/i18n_keys.py      # lists what is missing in de / fr / en
```

and add the missing entries to `webui/locale/*.json`. `tests/test_i18n.py` fails until they are there.

---

## 6. Still open

| Item | Where |
|---|---|
| **Core reliability fixes**: store before ACK, durable WAL, correct ACK reading, per-target delivery | [README-RELIABILITY.md](README-RELIABILITY.md) |
| Redesign the **first-start wizard** (7 steps → 4) and translate its steps | Sprint story F1 |
| "Send all again" page for doctors (today the resend list is admin only) | Sprint story E2 |
| Help page | Sprint story G1 |
| **Native-speaker review** of the German, French and English texts | Sprint story I1 |
| Test names (Glukose, Kreatinin…) come from the LOINC table, which is German only | to plan |
| Some machine names in the catalogue still contain Italian words ("Chimica", "Emoglobina") | `config/devices/*.yaml` |
| Saving a machine profile rewrites the YAML file without its comments (the settings themselves are kept) | `webui/app.py` |
| Arena tournament on the app shell: paused, state saved in `.arena/` | resume with `.claude/arena-skill/skills/arena/bracket.py next` |
