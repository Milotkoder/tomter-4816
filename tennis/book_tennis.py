"""
MATCHi Tennis Booking Bot - Sagene
===================================
Booker tennisbane på Sagene via MATCHi ved nøyaktig midnatt.

Bruk:
  python book_tennis.py --date 2026-04-03 --times 19:00 20:00
  python book_tennis.py --date 2026-04-03 --times 19:00 20:00 --midnight
  python book_tennis.py --date 2026-04-03 --times 19:00 --check-only

Midnatt-modus:
  Venter til 23:59:59.700 og forsøker å booke nøyaktig når banene åpner.
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

load_dotenv()

MATCHI_EMAIL = os.getenv("MATCHI_EMAIL", "milotincito@outlook.com")
MATCHI_PASSWORD = os.getenv("MATCHI_PASSWORD", "Jeggikkpåturi2025!")
FACILITY_URL = "https://www.matchi.se/facilities/sagene"
LOGIN_URL = "https://www.matchi.se/login/auth"


async def login(page, email: str, password: str) -> bool:
    """Logger inn på MATCHi. Returnerer True hvis vellykket."""
    print(f"[{ts()}] Logger inn som {email}...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")

    # Fyll inn innloggingsskjema
    await page.fill('input[name="j_username"]', email)
    await page.fill('input[name="j_password"]', password)
    await page.click('button[type="submit"], input[type="submit"]')

    # Vent på redirect etter login
    try:
        await page.wait_for_url(lambda url: "login" not in url, timeout=10_000)
        print(f"[{ts()}] Innlogget OK")
        return True
    except PlaywrightTimeout:
        # Sjekk for feilmelding
        error = await page.query_selector(".alert-danger, .error, #loginError")
        if error:
            msg = await error.inner_text()
            print(f"[{ts()}] Innlogging feilet: {msg.strip()}")
        else:
            print(f"[{ts()}] Innlogging feilet (ukjent feil)")
        return False


async def get_available_slots(page, date: str) -> list[dict]:
    """
    Henter tilgjengelige tidslukker for gitt dato på Sagene.
    Returnerer liste med {'time': '19:00', 'court': 'Bane 1', 'element': ...}
    """
    url = f"{FACILITY_URL}?date={date}&sport=1"
    print(f"[{ts()}] Henter baner for {date}: {url}")
    await page.goto(url, wait_until="domcontentloaded")

    # Vent til booking-grid er lastet
    try:
        await page.wait_for_selector(
            ".booking-slot, .slot, [class*='slot'], [class*='booking'], .schedule-slot, .time-slot",
            timeout=10_000
        )
    except PlaywrightTimeout:
        print(f"[{ts()}] Advarsel: Fant ikke booking-slots etter 10 sek, fortsetter likevel...")

    # Hent alle ledige slots (ulike klasser MATCHi bruker)
    slots = []
    selectors = [
        "a.free-slot",
        "a.available",
        ".slot.free a",
        ".booking-slot.available",
        "[class*='free'] a[href*='book']",
        "a[href*='/book']",
        ".time-slot:not(.booked) a",
        ".schedule a.available",
    ]

    for selector in selectors:
        elements = await page.query_selector_all(selector)
        if elements:
            print(f"[{ts()}] Fant {len(elements)} slots med selector: {selector}")
            for el in elements:
                text = await el.inner_text()
                href = await el.get_attribute("href") or ""
                # Prøv å finne tidspunkt i tekst eller parent-element
                parent = await el.evaluate_handle("el => el.closest('tr, .slot-row, .time-row')")
                parent_text = await parent.evaluate("el => el ? el.innerText : ''")
                slots.append({
                    "time": extract_time(text + " " + parent_text),
                    "court": extract_court(text + " " + parent_text),
                    "href": href,
                    "element": el,
                    "text": text.strip(),
                })
            break  # Bruk første selector som gir resultater

    # Fallback: dump all tekst fra siden for debugging
    if not slots:
        print(f"[{ts()}] Ingen slots funnet med standard selectors. Dumper page-tittel...")
        title = await page.title()
        print(f"[{ts()}] Side-tittel: {title}")

    return slots


def extract_time(text: str) -> str:
    """Trekker ut tid (HH:MM) fra tekst."""
    import re
    match = re.search(r"\b(\d{1,2}:\d{2})\b", text)
    return match.group(1) if match else ""


def extract_court(text: str) -> str:
    """Trekker ut banenavn fra tekst."""
    import re
    match = re.search(r"(Bane\s*\d+|Court\s*\d+|Bana\s*\d+)", text, re.IGNORECASE)
    return match.group(0) if match else "Ukjent"


async def book_slot(page, slot: dict) -> bool:
    """Klikker på en slot og bekrefter booking. Returnerer True hvis vellykket."""
    print(f"[{ts()}] Booker slot: {slot['time']} {slot['court']} ...")

    try:
        await slot["element"].click()
        await page.wait_for_load_state("domcontentloaded")

        # Se etter bekreftelsesknapp
        confirm_selectors = [
            "button:has-text('Bekreft')",
            "button:has-text('Bekräfta')",
            "button:has-text('Confirm')",
            "button:has-text('Book')",
            "button:has-text('Bestill')",
            "input[type='submit'][value*='ok' i]",
            "input[type='submit'][value*='book' i]",
            ".btn-primary[type='submit']",
            "form[action*='book'] button[type='submit']",
        ]

        for sel in confirm_selectors:
            btn = await page.query_selector(sel)
            if btn:
                print(f"[{ts()}] Fant bekreftelsesknapp: {sel}")
                await btn.click()
                await page.wait_for_load_state("domcontentloaded")
                break

        # Sjekk om booking var vellykket
        success_indicators = [
            ".booking-confirmation",
            "[class*='confirmation']",
            "[class*='success']",
            "h1:has-text('Booking')",
            "h2:has-text('bekreftet')",
            "h2:has-text('bekräftad')",
        ]

        for sel in success_indicators:
            el = await page.query_selector(sel)
            if el:
                text = await el.inner_text()
                print(f"[{ts()}] BOOKING VELLYKKET: {text.strip()[:100]}")
                return True

        # Sjekk URL for bekreftelses-signal
        current_url = page.url
        if "confirm" in current_url or "success" in current_url or "booking" in current_url:
            print(f"[{ts()}] BOOKING VELLYKKET (URL indikerer suksess): {current_url}")
            return True

        print(f"[{ts()}] Booking-status uklar. Sjekk nettleseren.")
        return False

    except Exception as e:
        print(f"[{ts()}] Feil under booking: {e}")
        return False


def wait_for_midnight(pre_seconds: float = 0.3, max_wait_minutes: int = 10):
    """
    Venter til nøyaktig midnatt minus pre_seconds sekunder,
    deretter returnerer ved midnatt.

    pre_seconds = 0.3 betyr at vi trigger 300ms FØR midnatt
    slik at HTTP-requesten ankommer serveren rett ved midnatt.

    max_wait_minutes: avbryt hvis ventetiden er lengre enn dette (sikkerhet for CI)
    """
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    target = tomorrow - timedelta(seconds=pre_seconds)
    wait_secs = (target - now).total_seconds()

    if wait_secs < 0:
        print(f"[{ts()}] Allerede passert midnatt, booker umiddelbart.")
        return

    if wait_secs > max_wait_minutes * 60:
        print(f"[{ts()}] FEIL: {wait_secs/60:.1f} min til midnatt — over grensen på {max_wait_minutes} min.")
        print(f"[{ts()}] Start scriptet nærmere midnatt, eller øk --max-wait.")
        sys.exit(1)

    print(f"[{ts()}] Venter til {target.strftime('%H:%M:%S.%f')[:-3]} ({wait_secs:.1f} sek)...")
    print(f"[{ts()}] Midnatt er: {tomorrow.strftime('%Y-%m-%d %H:%M:%S')}")

    # Grov sleep til 10 sekunder før
    if wait_secs > 10:
        time.sleep(wait_secs - 10)
        now = datetime.now()
        wait_secs = (target - now).total_seconds()

    # Presis busy-wait de siste 10 sekundene
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            break
        if remaining > 1:
            time.sleep(0.1)
        else:
            time.sleep(0.001)  # 1ms presisjon

    print(f"[{ts()}] GO! Tidspunkt: {datetime.now().strftime('%H:%M:%S.%f')}")


def ts() -> str:
    """Returnerer nåværende tidsstempel for logging."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


async def main():
    parser = argparse.ArgumentParser(description="MATCHi Tennis Booking - Sagene")
    parser.add_argument("--date", required=True, help="Dato å booke (YYYY-MM-DD), f.eks. 2026-04-03")
    parser.add_argument("--times", nargs="+", required=True,
                        help="Foretrukne tidspunkt i prioritetsrekkefølge, f.eks. 19:00 20:00")
    parser.add_argument("--midnight", action="store_true",
                        help="Vent til midnatt og book da (for neste ledige dag)")
    parser.add_argument("--check-only", action="store_true",
                        help="Sjekk bare tilgjengelighet, ikke book")
    parser.add_argument("--headless", action="store_true",
                        help="Kjør uten synlig nettleser (standard: synlig)")
    parser.add_argument("--pre-seconds", type=float, default=0.3,
                        help="Sekunder før midnatt å sende request (standard: 0.3)")
    parser.add_argument("--max-wait", type=int, default=10,
                        help="Maks minutter å vente på midnatt (standard: 10, for CI-sikkerhet)")
    args = parser.parse_args()

    print(f"[{ts()}] === MATCHi Tennis Booking ===")
    print(f"[{ts()}] Dato: {args.date}")
    print(f"[{ts()}] Ønskede tider: {', '.join(args.times)}")
    print(f"[{ts()}] Modus: {'Sjekk' if args.check_only else 'Midnatt' if args.midnight else 'Umiddelbar'}")
    print(f"[{ts()}] Tidssone: {datetime.now().astimezone().tzname()}")

    if args.midnight:
        wait_for_midnight(pre_seconds=args.pre_seconds, max_wait_minutes=args.max_wait)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # Login
            ok = await login(page, MATCHI_EMAIL, MATCHI_PASSWORD)
            if not ok:
                print(f"[{ts()}] Avslutter pga innloggingsfeil.")
                sys.exit(1)

            # Hent tilgjengelige slots
            all_slots = await get_available_slots(page, args.date)
            print(f"[{ts()}] Fant totalt {len(all_slots)} ledige slots")

            if args.check_only:
                print(f"\n[{ts()}] === Tilgjengelige slots ===")
                for s in all_slots:
                    print(f"  {s['time']:5s}  {s['court']}")
                return

            # Prøv å booke i prioritetsrekkefølge
            booked = False
            for preferred_time in args.times:
                matching = [s for s in all_slots if s["time"].startswith(preferred_time[:5])]
                if not matching:
                    print(f"[{ts()}] Kl {preferred_time} er ikke ledig, prøver neste...")
                    continue

                slot = matching[0]
                print(f"[{ts()}] Forsøker å booke kl {preferred_time} ({slot['court']})...")
                success = await book_slot(page, slot)
                if success:
                    booked = True
                    print(f"\n[{ts()}] SUKSESS! Bane booket: {slot['time']} {slot['court']}")
                    break
                else:
                    print(f"[{ts()}] Booking av {preferred_time} feilet, prøver neste...")

            if not booked:
                print(f"\n[{ts()}] Ingen av de ønskede tidene ({', '.join(args.times)}) ble booket.")
                print(f"[{ts()}] Kjør med --check-only for å se hva som er ledig.")

            # Hold nettleser åpen litt så man ser resultatet
            if not args.headless:
                await asyncio.sleep(5)

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
