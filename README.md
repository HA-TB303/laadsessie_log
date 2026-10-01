# Laadsessie log

> [!WARNING]
> **Dit is een persoonlijk hobbyproject zonder enige onderhoudsgarantie.** Het wordt in mijn vrije tijd gemaakt en gebruikt; er is geen toezegging dat issues, pull requests of feature-verzoeken worden opgepakt, en reactietijden kunnen (zeer) lang zijn of uitblijven. Gebruik op eigen risico — bekijk de code en test grondig voordat je het op je eigen Home Assistant-installatie draait.

Home Assistant-integratie die laadsessies van je laadpaal per kwartier logt tegen een dynamisch stroomtarief (bijv. Zonneplan) en maandelijks een PDF- en CSV-laadrapport maakt, bijvoorbeeld voor declaratie bij je werkgever.

## Functies

- Logt per kwartier de geladen energie (kWh) en het bijbehorende tarief (EUR/kWh).
- Gebruikt optioneel de sessie-energiemeter van de laadpaal om het totaal per sessie te corrigeren.
- Maakt per maand een PDF- en CSV-rapport in `www/laadrapporten` (bereikbaar via `/local/laadrapporten`).
- Ingebouwd dashboard **Laadsessies** in de zijbalk met maandtotalen, rapportenoverzicht en PDF-viewer (uit te zetten in de opties).
- Ingebouwde PDF-viewer.
- Tekstvelden voor naam, adres en kenteken die op het rapport worden afgedrukt.
- Service `laadsessie_log.genereer_rapport` om een rapport (opnieuw) te genereren.

## Installatie via HACS

1. Open HACS → menu (⋮) → **Custom repositories**.
2. Voeg `https://github.com/HA-TB303/laadsessie_log` toe met categorie **Integration**.
3. Zoek **Laadsessie log**, installeer en herstart Home Assistant.
4. Ga naar **Instellingen → Apparaten & diensten → Integratie toevoegen** en kies **Laadsessie log**.

## Handmatige installatie

Kopieer `custom_components/laadsessie_log` naar `<config>/custom_components/` en herstart Home Assistant.

## Configuratie

| Veld | Omschrijving |
|------|--------------|
| Laadvermogen | Sensor met het actuele laadvermogen (kW of W). |
| Laadpaalstatus | Sensor of binaire sensor die aangeeft of de auto is aangesloten. |
| Sessie-energie (optioneel) | Energiemeter van de huidige laadsessie (kWh of Wh). |
| Kwartiertarief | Sensor met het actuele stroomtarief in EUR/kWh. |
| Naam tariefbron | Naam van de leverancier in rapporten en meldingen. |
| Statussen 'niet aangesloten' | Komma-gescheiden statuswaarden waarbij de auto niet is aangesloten. |
| Dashboard 'Laadsessies' in de zijbalk | Toont het ingebouwde dashboard (`/laadsessie-log`). Het wordt automatisch opgebouwd uit de gekozen sensoren en is alleen-lezen; wil je het aanpassen, zet dit dan uit en maak een eigen dashboard. |

## Service

```yaml
action: laadsessie_log.genereer_rapport
data:
  jaar: 2026
  maand: 9
  # alle: true   # alle rapporten opnieuw maken
```

## Licentie

MIT. De meegeleverde PDF.js-bestanden (`viewer/pdf*.js`) vallen onder de Apache 2.0-licentie van Mozilla.
