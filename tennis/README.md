# MATCHi Tennis Booking - Sagene

Automatisk booking av tennisbane på Sagene via MATCHi. Kjører på GitHub Actions — ingen PC nødvendig.

## Oppsett (engangsjobb)

1. Gå til **Settings → Secrets and variables → Actions** og legg til:
   - `MATCHI_EMAIL` = din e-post
   - `MATCHI_PASSWORD` = ditt passord

2. Gå til **Actions**-fanen og aktiver workflows

## Slik booker du

### Metode 1: Umiddelbar booking (oppdater fil)
Rediger `tennis/next_booking.json` direkte på GitHub:
```json
{
  "active": true,
  "date": "2026-04-05",
  "times": ["19:00", "20:00"],
  "midnight": false
}
```
Lagre filen — workflowen starter automatisk.

### Metode 2: Midnatt-booking
Sett `"midnight": true` og `"active": true` i `tennis/next_booking.json`.
Cron-jobben starter kl **23:55 Oslo-tid** og venter til nøyaktig midnatt.

### Metode 3: Manuell trigger (fra PC)
Actions → Book Tennis Court - Sagene → Run workflow

## Filer

| Fil | Beskrivelse |
|---|---|
| `tennis/book_tennis.py` | Hoved-script (Playwright) |
| `tennis/next_booking.json` | Booking-konfig (rediger dette) |
| `tennis/requirements.txt` | Python-avhengigheter |
| `.github/workflows/book_tennis.yml` | GitHub Actions workflow |

## next_booking.json felter

| Felt | Beskrivelse |
|---|---|
| `active` | `true` = kjør booking, `false` = ikke gjør noe |
| `date` | Dato å booke (YYYY-MM-DD) |
| `times` | Tider i prioritetsrekkefølge, f.eks. `["19:00", "20:00"]` |
| `midnight` | `true` = vent til midnatt, `false` = book umiddelbart |

## Timing

Baner på Sagene åpner kl 00:00:00, **2 dager i forveien**.
For å booke f.eks. lørdag 5. april: oppdater `next_booking.json` **torsdag 3. april kveld**
med `"date": "2026-04-05"` og `"midnight": true`.

Scriptet venter til **23:59:59.700** og sender booking-forespørselen ved midnatt.
