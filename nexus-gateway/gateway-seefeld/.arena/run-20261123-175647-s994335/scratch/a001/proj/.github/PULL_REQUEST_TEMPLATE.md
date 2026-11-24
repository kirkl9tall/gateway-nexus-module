# Pull Request

## Cosa cambia
<!-- Riassunto in 1-3 frasi -->

## Perché
<!-- Che problema risolve? Riferisci un issue: closes #123 -->

## Come testarlo
<!-- Comandi + risultati attesi -->

## Checklist

- [ ] Tutti i test passano (`pytest`)
- [ ] Ruff/lint pulito (`ruff check`)
- [ ] Nuova documentazione aggiornata se applicabile
- [ ] CHANGELOG entry aggiunta sotto `[Unreleased]`
- [ ] Se tocca la sicurezza/config sensibile: security lead è in review
- [ ] Se tocca un adapter: c'è un test in `tests/test_adapters.py`
- [ ] Se cambia il DB history o breaker state: migrazione documentata
- [ ] Se aggiunge una feature user-facing: screenshot allegato

## Screenshot (se UI)

## Regolatorio
- [ ] La modifica cambia classificazione IVDR? (se sì: valuta con QM)
- [ ] La modifica introduce un nuovo hazard? (se sì: risk analysis update)
