# Voorbeeld: voertuigherkenning op een Tinkerforge WARP-laadpaal

Dit voorbeeld hoort bij de optionele **Voertuig**-instelling van Laadsessie log. Het laat zien
hoe je, met twee auto's op één laadpaal, automatisch detecteert welke auto is aangesloten en
de laadsessie op de laadpaal zelf aan de juiste gebruiker toewijst via NFC-tag-injectie — zodat
`charge_tracker` op de WARP-lader de sessie ook aan de juiste kant boekt, los van Home Assistant.

Dit is specifiek gebouwd voor een **Tinkerforge WARP3 Pro**-laadpaal (lokale HTTP-API, geen
authenticatie) met een Tesla en een Kia e-Niro, maar het patroon is herbruikbaar: vervang de
automation-logica door wat voor jouw laadpaal/auto's werkt, zolang je uiteindelijk één sensor
overhoudt waarvan de tekstwaarde het voertuig weergeeft ("Tesla", "Kia E-Niro", ...). Dát is de
sensor die je bij Laadsessie log instelt als **Voertuig**.

## Hoe het werkt

1. **`configuration.yaml`**: een `rest`-sensor pollt `charge_tracker/current_charge` op de
   WARP-lader om te zien welke gebruiker (user-ID) momenteel is geautoriseerd, en een
   `template`-sensor vertaalt dat ID naar een leesbare naam (`sensor.warp3pro_actieve_gebruiker`).
   Een `rest_command` stuurt een "NFC-tag gescand"-signaal naar de lader (`nfc/inject_tag_start`)
   om een sessie aan een specifieke gebruiker toe te wijzen, zonder fysiek een tag te hoeven
   scannen.
2. **`automation.yaml`**: zodra de laadkabel wordt aangesloten, wordt gekeken of de Tesla's eigen
   "aangesloten"-sensor "aan" staat (met een korte wake-up/force-update om trage polling te
   omzeilen). Is dat zo, dan wordt de Tesla-tag geïnjecteerd; zo niet, dan wordt standaard de
   Kia-tag geïnjecteerd. Een tweede trigger herautoriseert de sessie zodra er alsnog voldoende
   zonne-overschot ontstaat terwijl de lader nog aan het wachten was.

## Zelf instellen

1. Vraag de geregistreerde NFC-tags van je eigen lader op: `GET http://<lader-ip>/nfc/config`
   geeft een lijst `{"user_id": ..., "tag_type": ..., "tag_id": ...}` — vul die waarden in op de
   plekken met `AA:BB:CC:DD:EE:FF:...` in `automation.yaml`.
2. Pas de entity-ID's aan je eigen Tesla-integratie aan (`binary_sensor.duracell_charger`,
   `button.duracell_wake_up`, `button.duracell_force_data_update`) of vervang die logica door iets
   dat bij jouw tweede auto past.
3. Stel bij Laadsessie log (**Instellingen → Apparaten & diensten → Laadsessie log → Configureren**)
   het veld **Voertuig** in op `sensor.warp3pro_actieve_gebruiker`.

## Kanttekeningen

- De vertraging in `wait_template` (20s) bestaat omdat sommige voertuig-integraties traag pollen
  wanneer de auto geparkeerd staat; stem dit af op je eigen situatie.
- Dit voorbeeld autoriseert op de laadpaal zelf (zodat de laadpaal-eigen rapportage ook klopt);
  voor alleen de **Voertuig**-instelling van Laadsessie log heb je eigenlijk alleen de
  `sensor.warp3pro_actieve_gebruiker`-sensor nodig — de NFC-toewijzing is optioneel als je puur
  per-voertuig wilt rapporteren in Laadsessie log zonder de laadpaal zelf aan te sturen.
