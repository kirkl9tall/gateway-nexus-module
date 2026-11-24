# UI design arena: Overview, Machines, Check

Three design directions competed for the doctor-facing pages. Each was scored against the persona in [SPRINT-UI-SIMPLE.md](../SPRINT-UI-SIMPLE.md): a GP or medical assistant who is not technical and opens the gateway only to ask "is it working?".

## The contenders

**A: Control room.** A grid of six gauges (uptime, P95, errors, queue, results, breakers), a 24-hour chart and live logs. This is the classic monitoring dashboard.

**B: The sample's path.** The page draws the route a result takes: *Machines → Gateway → Practice software*. Each of the three stations is big and shows its state as a word, an icon and a colour. Below that come today's count (with a ring gauge for "delivered"), a 7-day bar chart, and one card per machine and per practice software.

**C: One answer.** One huge sentence ("Everything works") and a checklist of rows, with no visuals.

## Scoring (0–3 per criterion, × weight)

| Criterion | Weight | A | B | C |
|---|---|---|---|---|
| Answers "are results arriving?" in 5 seconds | 3 | 1 | 3 | 3 |
| Shows *where* the data goes (Tomedo, …) | 2 | 1 | 3 | 1 |
| Shows each machine up or down | 2 | 2 | 3 | 2 |
| No jargon | 2 | 1 | 3 | 3 |
| Visual stats/gauges (requested) | 1 | 3 | 2 | 0 |
| Still clear with 10 machines | 1 | 2 | 2 | 3 |
| Light enough for a Raspberry Pi (no chart library) | 1 | 1 | 3 | 3 |
| Works on a tablet at the bench | 1 | 1 | 3 | 3 |
| **Total (max 39)** | | **18** | **37** | **30** |

**Winner: B**, topped with C's one-sentence headline. A's metrics are useful to the technician, so they move to a collapsed **"For the technician"** section at the **bottom** of each page, visible to the admin only.

## Design tokens

- **Typeface:** Atkinson Hyperlegible, regular and bold. It was designed by the Braille Institute for readers with low vision, and its letters are hard to confuse (1/l/I, 0/O). It's served from the Pi (`webui/static/fonts/`) because practices are often offline. A single family is used for everything, and numbers are tabular.
- **Size:** base 18 px; headline 40 px; station values 28 px; buttons ≥ 48 px.
- **Colours:**

  | Name | Value | Use |
  |---|---|---|
  | page | `#F3F6F7` | Cool clinical grey page |
  | card | `#FFFFFF` | Cards |
  | ink | `#17202A` | Main text |
  | ink-2 | `#4B5763` | Secondary text |
  | ink-3 | `#5F6B77` | Muted text |
  | line | `#D5DCE1` | Borders and lines |
  | brand / data | `#2C5F8A` | Buttons and the single data series |

- **Status colours:** each status always comes with its own icon *shape* and a word.

  | Status | Colour | Icon |
  |---|---|---|
  | good | `#1E7A46` | ✓ in a circle |
  | warning | fill `#E9A820`, text `#8A5A00` | ! in a triangle |
  | critical | `#B42318` | ✕ in an octagon |
  | neutral / paused | `#5F6B77` | ‖ in a circle |

  The dataviz validator confirms that green and red fall under ΔE 8 for deuteranopes, which is true of every green/red pair. That's why colour never carries the meaning alone.
- **Contrast (WCAG):** every text colour is ≥ 4.5:1 on white and on the page grey. Measured: good 5.35, warning text 5.9, critical 6.57, brand 6.75.

## The one bold element

The **path line** between the three stations:
- **Data moved in the last 10 minutes:** small dots travel along it, the only animation on the page.
- **Gateway off:** the line is grey and still.
- **Practice software unreachable:** a red break mark appears exactly where the path is broken.

Everything else is quiet: flat white cards, one radius (10 px), no shadows, no gradients.

## Rules kept from the sprint

- **No jargon on doctor screens:** no port, MLLP, HL7, DLQ, P95 or uptime.
- **Every problem says what to do** and offers one button.
- **One rendering path:** the server renders the live area translated (`/overview/live`), and the browser swaps it every 15 s. No strings are built in JavaScript.
- **Reduced motion respected,** visible keyboard focus, layout down to 360 px.
