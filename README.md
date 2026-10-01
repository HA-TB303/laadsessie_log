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
- Instellingen voor naam, adres en kenteken die op het rapport worden afgedrukt.
- Optioneel: losse rapporten per voertuig als je met meerdere auto's op dezelfde laadpaal laadt.
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
| Voertuig (optioneel) | Sensor waarvan de tekstwaarde aangeeft welk voertuig is aangesloten (zie [Voorbeelden](#voorbeelden)). Zonder deze sensor worden sessies niet per voertuig onderverdeeld. |
| Kwartiertarief | Sensor met het actuele stroomtarief in EUR/kWh. |
| Naam tariefbron | Naam van de leverancier in rapporten en meldingen. |
| Statussen 'niet aangesloten' | Komma-gescheiden statuswaarden waarbij de auto niet is aangesloten. |
| Hoe vaak wijzigt het tarief? | Per kwartier/uur (standaard, voor dynamische tarieven), per dag, of per maand (vast tarief). Bepaalt hoe lang een tariefwaarde geldig blijft voordat er een storingsmelding verschijnt, en of de kwartierdetail-pagina in het PDF-rapport zinvol is (die wordt overgeslagen bij een vast tarief). |
| Dashboard 'Laadsessies' in de zijbalk | Toont het ingebouwde dashboard (`/laadsessie-log`). Het wordt automatisch opgebouwd uit de gekozen sensoren en is alleen-lezen; wil je het aanpassen, zet dit dan uit en maak een eigen dashboard. |
| Naam (optioneel) | Naam zoals die op het laadrapport wordt getoond. |
| Adres laadpaal (optioneel) | Adres zoals dat op het laadrapport wordt getoond. |
| Kenteken (optioneel) | Kenteken zoals dat op het laadrapport wordt getoond. Wordt genegeerd zodra **Voertuig** is ingesteld. |

> Naam, adres en kenteken stonden in oudere versies als tekstvelden op het dashboard. Die zijn vervangen door deze instellingen; een eventueel al ingevulde waarde wordt bij de eerste start na het bijwerken automatisch overgenomen, dus je hoeft niets opnieuw in te vullen.

## Voertuig per sessie

Met het optionele veld **Voertuig** wordt elke laadsessie gekoppeld aan de waarde van een sensor naar keuze, op het moment dat de sessie eindigt (zodat een trage herkenning bij de start van het laden geen probleem is). Zodra dit veld is ingesteld, maakt de integratie per maand een **los PDF- en CSV-rapport per voertuig** (inclusief een rapport "Onbekend" voor sessies waarbij het voertuig niet herkend kon worden) in plaats van één gecombineerd rapport, en toont het dashboard per maand een aparte rij per voertuig. Op elk rapport staat dan "Voertuig: \<naam\>" in plaats van "Kenteken: ...". Handig als je bijvoorbeeld twee auto's op dezelfde laadpaal hebt en er maar één van voor werk declareert.

## Voorbeelden

- [`examples/warp3pro_voertuigherkenning`](examples/warp3pro_voertuigherkenning) — automation + helper-sensoren die op een Tinkerforge WARP-laadpaal detecteren welke van twee auto's is aangesloten en de laadsessie aan de juiste gebruiker toewijzen via NFC-tag-injectie. De resulterende sensor is precies wat je bij **Voertuig** instelt.

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
