# MATCHi Tennis Booking - Sagene

Automatisk booking av tennisbane på Sagene via MATCHi.

## Oppsett

```bash
cd tennis
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env   # Fyll inn credentials
```

## Bruk

### Test: Sjekk tilgjengelighet
```bash
python book_tennis.py --date 2026-04-03 --times 19:00 20:00 --check-only
```

### Book nå (umiddelbart)
```bash
python book_tennis.py --date 2026-04-03 --times 19:00 20:00
```

### Midnatt-modus (venter til 23:59:59.700)
```bash
python book_tennis.py --date 2026-04-05 --times 19:00 20:00 --midnight
```

## Argumenter

| Argument | Beskrivelse |
|---|---|
| `--date` | Dato å booke (YYYY-MM-DD) |
| `--times` | Tidspunkt i prioritetsrekkefølge, f.eks. `19:00 20:00` |
| `--midnight` | Vent til midnatt før booking |
| `--check-only` | Sjekk tilgjengelighet uten å booke |
| `--headless` | Kjør uten synlig nettleser |
| `--pre-seconds` | Millisekunder før midnatt å sende (standard: 0.3) |

## Timing

Baner på Sagene åpner kl 00:00:00 nøyaktig, 2 dager i forveien.
Scriptet venter til 23:59:59.700 og sender forespørselen slik at
den ankommer serveren rett ved midnatt.
