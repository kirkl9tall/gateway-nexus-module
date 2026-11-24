# Golden-file regression fixtures

**Purpose.** Bit-for-bit regression tests for the 6 devices verified in
real Swiss/DACH production (SD1, SD3, Sysmex XQ-320, Cobas b101, UC-1000,
LOC-200). Any change to a parser must preserve output on these frames.

## Layout

```
tests/fixtures/golden/
├── sd1/
│   ├── 001_normal_cbc.in.txt        # raw bytes the device sends
│   └── 001_normal_cbc.out.hl7       # expected HL7 v2 message emitted
├── sd3/
├── sysmex_xq320/
├── cobas_b101/
├── uc1000/
└── loc200/
```

Each pair `<name>.in.<ext>` + `<name>.out.hl7` is one test case.

## Input file format

- `.in.txt` — decoded ASCII text as the parser sees it (control bytes
  written as `\x02`, `\x03`, `\x05`, `\x06`, `\x04`, `\r`, `\n`).
- `.in.bin` — raw binary bytes verbatim. Use when non-ASCII bytes matter
  (some Sysmex checksums).

## Output file format

Full HL7 v2 message with `\r` segment separator, exactly as our
`hl7_builder` should emit it. Blank lines and leading/trailing whitespace
are compared after `.strip()`, but every segment must match verbatim.

## How to add a new fixture (owner workflow)

1. Capture a real frame from the device — one of:
   - `socat -x -,raw /dev/ttyUSB0,raw,b9600 > capture.txt`
   - The `discovery/probes.py` capture mode from the CLI
   - Copy-paste from the vendor middleware
2. Copy it to `tests/fixtures/golden/<device>/<slug>.in.txt`.
3. Run the current gateway once against that input, capture the emitted
   HL7, save as `<slug>.out.hl7`.
4. `pytest tests/test_golden.py -k <slug>` — should pass.
5. Any future refactor of the parser is now protected.

## Why the folders exist empty

They are pre-created so `pytest` collection does not skip the whole
module. Test files themselves are discovered dynamically — as soon as
the owner drops a real capture in, the test runs.
