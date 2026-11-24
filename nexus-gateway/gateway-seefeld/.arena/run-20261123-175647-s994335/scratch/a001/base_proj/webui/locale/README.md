# Internationalization (i18n)

Web UI strings are localized with **Babel/gettext**. Supported locales
map to the Swiss / DACH market:

| Code | Language | Status |
|------|----------|--------|
| `en` | English (fallback) | complete |
| `de` | Deutsch (DE/AT/CH-DE) | complete |
| `it` | Italiano (CH-IT) | complete |
| `fr` | Français (CH-FR) | complete |

## Layout

```
webui/locale/
├── messages.pot                    # extraction template
├── de/LC_MESSAGES/messages.po      # translations
├── it/LC_MESSAGES/messages.po
├── fr/LC_MESSAGES/messages.po
└── en/LC_MESSAGES/messages.po
```

## Adding a new string

1. Wrap in `gettext("...")` or `_("...")` in Python / Jinja.
2. Extract:
   ```bash
   pybabel extract -F babel.cfg -o webui/locale/messages.pot .
   ```
3. Update the four `.po` files:
   ```bash
   pybabel update -i webui/locale/messages.pot -d webui/locale
   ```
4. Translate the new `msgid`/`msgstr` pairs in each `.po`.
5. Compile:
   ```bash
   pybabel compile -d webui/locale
   ```

## Locale selection at runtime

Order of precedence:
1. `?lang=fr` query parameter (session-scoped).
2. User profile setting (`users.json` `preferred_locale`).
3. `Accept-Language` header from the browser.
4. Fallback `en`.

CI enforces that every `.po` has 100% of the keys in `messages.pot`.
