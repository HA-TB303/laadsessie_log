# Laadsessie log – werkafspraken voor Claude Code

Home Assistant custom integration (`laadsessie_log`) die laadsessies per kwartier logt
tegen een dynamisch tarief en maandelijks PDF/CSV-laadrapporten maakt.
Gepubliceerd als HACS custom repository: https://github.com/HA-TB303/laadsessie_log

## Werkwijze (verplicht)

- **Elke wijziging via een pull request**, nooit direct committen op `main`:
  1. `git checkout main && git pull`
  2. `git checkout -b <type>/<korte-omschrijving>` (bijv. `fix/tarief-terugval`, `feat/csv-export`)
  3. wijzigen, testen in HA, committen, `git push -u origin <branch>`
  4. `gh pr create --fill` (of met eigen titel/omschrijving, in het Nederlands)
- Wacht tot de GitHub Action **Validate** (hassfest + HACS) groen is: `gh pr checks`.
- Commits op naam van `HA-TB303` met het GitHub noreply-adres, **niet** een werk-e-mailadres:
  `git config user.name HA-TB303`
  `git config user.email "$(gh api user --jq .id)+HA-TB303@users.noreply.github.com"`

## Release (na merge van functionele wijzigingen)

1. In de PR zelf `version` in `custom_components/laadsessie_log/manifest.json` ophogen (semver).
2. Na merge: `git checkout main && git pull && gh release create vX.Y.Z --title vX.Y.Z --generate-notes`
3. HACS toont de update op basis van de GitHub-release (tag `vX.Y.Z`).

Alleen documentatie of CI gewijzigd? Dan geen versie-bump en geen release.

## Opzetten op een (nieuwe) Home Assistant met de Claude Code add-on

```sh
gh auth login                               # GitHub.com, HTTPS, browser
gh auth refresh -h github.com -s workflow   # nodig om .github/workflows te pushen
gh auth setup-git
mkdir -p /share/github && cd /share/github
gh repo clone HA-TB303/laadsessie_log
```

- Lokale clone: `/share/github/laadsessie_log`
- Live code in HA: `/homeassistant/custom_components/laadsessie_log` (geïnstalleerd via HACS)
- Testen: wijziging naar de live map kopiëren
  (`cp -r custom_components/laadsessie_log/. /homeassistant/custom_components/laadsessie_log/`),
  HA herstarten en logs bekijken (`ha core logs 2>&1 | grep -i laadsessie`).
  Na merge + release de update via HACS installeren, zodat de live map weer gelijk is aan de repo.

## Opbouw van de code (`custom_components/laadsessie_log/`)

| Bestand | Inhoud |
|---------|--------|
| `__init__.py` | `LaadLog`: setup, luistert naar state changes, speelt bij start de recorder-historie na (eerste keer 10 dagen), schrijft sessies, maakt rapporten (optioneel los per voertuig, zie `CONF_VOERTUIG`/`async_generate_voertuigen`), migreert eenmalig het oude `gegevens.json`-tekstveldenbestand naar de instellingen (`_migreer_rapportgegevens`), service `genereer_rapport`, retentie 15 maanden. |
| `tracker.py` | `SessionTracker`: pure logica (geen HA-afhankelijkheid) die vermogen/status/sessie-energie/tarief/voertuig per kwartier integreert tot sessies; serialiseerbaar via `to_dict`/`from_dict`. |
| `pdf.py` | `build_report`: genereert de PDF zonder externe libraries (`requirements` is leeg – zo houden). |
| `sensor.py` | Sensoren: energie/kosten deze maand (incl. `per_voertuig`-attribuut), actieve sessie, rapporten, tariefstatus. |
| `dashboard.py` | Ingebouwd alleen-lezen Lovelace-dashboard `/laadsessie-log` (zijbalk "Laadsessies"), bij elke load opgebouwd uit de opties + entity registry (op `unique_id`); toont een Voertuig-kolom zodra `CONF_VOERTUIG` is ingesteld. Gebruikt interne lovelace-API (`LOVELACE_DATA`, `LovelaceConfig`) – na HA-updates controleren. |
| `config_flow.py` | Config- en options-flow (één instantie, `single_config_entry`); incl. naam/adres/kenteken en de optionele voertuig-sensor. |
| `viewer/` | PDF.js-viewer, wordt bij start gekopieerd naar `www/laadrapporten/viewer`. |
| `translations/` | `nl.json` en `en.json` (beide Nederlandstalig); houd ze gelijk en voeg nieuwe velden/services in beide toe. |

Gegevens op de HA-instantie (niet in de repo):
- `/homeassistant/laadsessies/state.json`, `sessies.json`
- `/homeassistant/laadsessies/gegevens.json` (legacy; alleen nog gelezen voor de eenmalige migratie van naam/adres/kenteken naar de instellingen)
- Rapporten: `/homeassistant/www/laadrapporten` → `/local/laadrapporten`

## Conventies

- Code, comments, logteksten en UI-teksten in het **Nederlands**.
- `manifest.json`: sleutels `domain`, `name` eerst, daarna alfabetisch (hassfest eist dit).
- Blokkerende I/O altijd via `hass.async_add_executor_job`.
- Geen persoonsgegevens (naam, adres, kenteken, sessiedata) in de repo committen.
