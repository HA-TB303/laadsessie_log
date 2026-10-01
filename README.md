# Laadsessie log

> [!WARNING]
> **Dit is een persoonlijk hobbyproject zonder enige onderhoudsgarantie.** Het wordt in mijn vrije tijd gemaakt en gebruikt; er is geen toezegging dat issues, pull requests of feature-verzoeken worden opgepakt, en reactietijden kunnen (zeer) lang zijn of uitblijven. Gebruik op eigen risico — bekijk de code en test grondig voordat je het op je eigen Home Assistant-installatie draait.

Home Assistant-integratie die laadsessies van je laadpaal per kwartier logt tegen een dynamisch stroomtarief (bijv. Zonneplan) en maandelijks een PDF- en CSV-laadrapport maakt, bijvoorbeeld voor declaratie bij je werkgever.

## Functies

- Logt per kwartier de geladen energie (kWh) en het bijbehorende tarief (EUR/kWh).
- Gebruikt optioneel de energiemeter van de laadpaal om het totaal per sessie te corrigeren (een per-sessie-teller of een doorlopende meterstand).
- Maakt per maand een PDF- en CSV-rapport. De rapporten zijn **alleen voor ingelogde gebruikers** te bekijken en te downloaden (zie [Rapporten en beveiliging](#rapporten-en-beveiliging)).
- Ingebouwd dashboard **Laadsessies** in de zijbalk met maandtotalen, een staafgrafiek van de geladen kWh per dag, rapportenoverzicht en PDF-viewer (uit te zetten in de opties).
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
| Sessie-energie (optioneel) | Energiemeter van de laadpaal (kWh of Wh). Dit mag een teller zijn die per sessie op 0 begint, maar ook een doorlopende meterstand (zoals `energy_rel` van een WARP-laadpaal): de integratie onthoudt de stand bij de start van de sessie en telt alleen het verschil. |
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

Met het optionele veld **Voertuig** wordt elke laadsessie gekoppeld aan de waarde van een sensor naar keuze. Het voertuig wordt vastgelegd op het moment dat er echt energie bijkomt; een sessie krijgt het voertuig met de meeste geladen energie (zodat een trage herkenning bij de start, of een sensor die na het loskoppelen terugvalt op "Onbekend", geen probleem is). Zodra dit veld is ingesteld, maakt de integratie per maand een **los PDF- en CSV-rapport per voertuig** in plaats van één gecombineerd rapport, en toont het dashboard per maand een aparte rij per voertuig. Sessies waarbij het voertuig niet herkend kon worden komen in een rapport "Onbekend". Op elk rapport staat dan "Voertuig: \<naam\>" in plaats van "Kenteken: ...". Handig als je bijvoorbeeld twee auto's op dezelfde laadpaal hebt en er maar één van voor werk declareert.

### Wanneer begint een nieuwe sessie?

- Een sessie eindigt pas als de laadpaal langer dan **2 minuten** "niet aangesloten" meldt; korte haperingen of de kabel even loshalen en terugsteken bij dezelfde auto horen bij dezelfde sessie.
- Wordt de kabel kort losgekoppeld en daarna een **ander voertuig** herkend (bijvoorbeeld snel wisselen van auto), dan begint er wel direct een nieuwe sessie.
- Sessies met minder dan **0,01 kWh** worden genegeerd.
- Maanden of voertuigen zonder geladen energie (0 kWh en € 0,00) krijgen geen rapport en worden niet in het overzicht getoond.

## Dashboard

Het ingebouwde dashboard toont onder andere de tegels Geladen, Kosten, Laadpaal, Voertuig (het nu aangesloten voertuig, als **Voertuig** is ingesteld), Actieve sessie en het tarief, plus een overzicht van alle rapporten.

De grafiek **Laadsessies deze maand** is een staafgrafiek met de dagen van de maand op de x-as en de geladen kWh op de y-as. Daarvoor is de kaart [ApexCharts Card](https://github.com/RomRider/apexcharts-card) nodig (via HACS → Frontend). Is die niet geïnstalleerd, dan toont het dashboard in plaats daarvan een eenvoudige tekstgrafiek met het totaal en de piekdag.

## Rapporten en beveiliging

Rapporten bevatten persoonsgegevens (naam, adres, laadgedrag) en worden daarom **niet** in de openbare `www`-map gezet: alles onder `/local/...` is in Home Assistant voor iedereen bereikbaar, ook zonder inloggen.

- De rapporten staan in `<config>/laadsessies/rapporten`.
- Ze worden geserveerd via `/api/laadsessie_log/rapport/<bestand>`, dat alleen werkt voor ingelogde gebruikers.
- Op het dashboard staan tijdelijk ondertekende links (zoals Home Assistant die ook voor camera- en mediabestanden gebruikt). Een link is 2 uur geldig, werkt alleen voor dat ene bestand en wordt automatisch vernieuwd zolang het dashboard open staat. Deel zo'n link dus niet als je niet wilt dat iemand anders het rapport binnen die tijd kan openen.
- De PDF-viewer (`/local/laadrapporten/viewer`) bevat zelf geen gegevens en opent alleen ondertekende links naar dit endpoint.
- De ondertekende links worden niet in de recorder-database opgeslagen.

> **Bijwerken vanaf 1.3.x:** bestaande rapporten in `www/laadrapporten` worden bij de eerste start automatisch naar `laadsessies/rapporten` verplaatst. Oude links naar `/local/laadrapporten/...` werken daarna niet meer; open de rapporten opnieuw via het dashboard. Gebruik je git voor je configuratie, zet `laadsessies/` dan in je `.gitignore`.

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

Het antwoord bevat het pad van het rapport (`/api/laadsessie_log/rapport/...`); dat is alleen op te halen met een geldig toegangstoken.

## Licentie

MIT. De meegeleverde PDF.js-bestanden (`viewer/pdf*.js`) vallen onder de Apache 2.0-licentie van Mozilla.
