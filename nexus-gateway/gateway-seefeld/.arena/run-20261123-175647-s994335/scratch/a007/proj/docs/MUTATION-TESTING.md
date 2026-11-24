# Mutation testing

We use `mutmut` to measure whether the test suite actually detects small
changes in the code. If a mutant survives, our tests have a blind spot.

## Run

```bash
pip install mutmut
mutmut run           # takes ~30-60 min on the current codebase
mutmut results       # summary
mutmut show 42       # inspect surviving mutant #42
mutmut show-diff 42  # see what mutant would have been made
```

## Targets

Configured in `setup.cfg`:

- `src/hl7/`      -- builder, validator, rewrites, fhir_builder
- `src/transport/` -- dispatcher, circuit breaker, MLLP
- `src/common/`   -- backpressure, dead_letter, history, alerting

Adapters, discovery, and webui are excluded (too much I/O to mutate cheaply).

## Passing bar

- **Green**: ≥ 90 % of mutants killed on src/hl7/
- **Yellow**: 75-90 %
- **Red**:   < 75 %

Report on each PR that touches the mutated paths.

## Fast preset (CI-friendly)

```bash
mutmut run --paths-to-mutate src/hl7/validator.py
```

Runs in ~2 min on validator alone.
