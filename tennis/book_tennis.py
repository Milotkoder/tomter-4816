"""
MATCHi Tennis Booking Bot - Sagene
===================================
Booker tennisbane på Sagene via MATCHi ved nøyaktig midnatt.

Bruk:
  python book_tennis.py --date 2026-04-03 --times 19:00 20:00
  python book_tennis.py --date 2026-04-03 --times 19:00 20:00 --midnight
  python book_tennis.py --date 2026-04-03 --times 19:00 --check-only
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
    print(f"[{ts()}] Logger inn som {email}...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.fill('input[name="j_username"]', email)
    await page.fill('input[name="j_password"]', password)
    await page.click('button[type="submit"], input[type="submit"]')
    try:
        await page.wait_for_url(lambda url: "login" not in url, timeout=10_000)
        print(f"[{ts()}] Innlogget OK")
        return True
    except PlaywrightTimeout:
        error = await page.query_selector(".alert-danger, .error, #loginError")
        if error:
            msg = await error.inner_text()
            print(f"[{ts()}] Innlogging feilet: {msg.strip()}")
        else:
            print(f"[{ts()}] Innlogging feilet (ukjent feil)")
        return False


async def get_available_slots(page, date: str) -> list[dict]:
    url = f"{FACILITY_URL}?date={date}&sport=1"
    print(f"[{ts()}] Henter baner for {date}: {url}")
    await page.goto(url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector(
            ".booking-slot, .slot, [class*='slot'], [class*='booking'], .schedule-slot, .time-slot",
            timeout=10_000
        )
    except PlaywrightTimeout:
        print(f"[{ts()}] Advarsel: Fant ikke booking-slots etter 10 sek, fortsetter likevel...")

    slots = []
    selectors = [
        "a.free-slot", "a.available", ".slot.free a", ".booking-slot.available",
        "[class*='free'] a[href*='book']", "a[href*='/book']",
        ".time-slot:not(.booked) a", ".schedule a.available",
    ]
    for selector in selectors:
        elements = await page.query_selector_all(selector)
        if elements:
            print(f"[{ts()}] Fant {len(elements)} slots med selector: {selector}")
            for el in elements:
                text = await el.inner_text()
                href = await el.get_attribute("href") or ""
                parent = await el.evaluate_handle("el => el.closest('tr, .slot-row, .time-row')")
                parent_text = await parent.evaluate("el => el ? el.innerText : ''")
                slots.append({
                    "time": extract_time(text + " " + parent_text),
                    "court": extract_court(text + " " + parent_text),
                    "href": href, "element": el, "text": text.strip(),
                })
            break
    if not slots:
        title = await page.title()
        print(f"[{ts()}] Ingen slots funnet. Side-tittel: {title}")
    return slots


def extract_time(text: str) -> str:
    import re
    match = re.search(r"\b(\d{1,2}:\d{2})\b", text)
    return match.group(1) if match else ""


def extract_court(text: str) -> str:
    import re
    match = re.search(r"(Bane\s*\d+|Court\s*\d+|Bana\s*\d+)", text, re.IGNORECASE)
    return match.group(0) if match else "Ukjent"


async def book_slot(page, slot: dict) -> bool:
    print(f"[{ts()}] Booker slot: {slot['time']} {slot['court']} ...")
    try:
        await slot["element"].click()
        await page.wait_for_load_state("domcontentloaded")
        for sel in [
            "button:has-text('Bekreft')", "button:has-text('Bekräfta')",
            "button:has-text('Confirm')", "button:has-text('Book')",
            "button:has-text('Bestill')", ".btn-primary[type='submit']",
            "form[action*='book'] button[type='submit']",
        ]:
            btn = await page.query_selector(sel)
            if btn:
                print(f"[{ts()}] Fant bekreftelsesknapp: {sel}")
                await btn.click()
                await page.wait_for_load_state("domcontentloaded")
                break
        for sel in [
            ".booking-confirmation", "[class*='confirmation']", "[class*='success']",
            "h1:has-text('Booking')", "h2:has-text('bekreftet')", "h2:has-text('bekräftad')",
        ]:
            el = await page.query_selector(sel)
            if el:
                text = await el.inner_text()
                print(f"[{ts()}] BOOKING VELLYKKET: {text.strip()[:100]}")
                return True
        current_url = page.url
        if "confirm" in current_url or "success" in current_url or "booking" in current_url:
            print(f"[{ts()}] BOOKING VELLYKKET (URL): {current_url}")
            return True
        print(f"[{ts()}] Booking-status uklar.")
        return False
    except Exception as e:
        print(f"[{ts()}] Feil under booking: {e}")
        return False


def wait_for_midnight(pre_seconds: float = 0.3, max_wait_minutes: int = 10):
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    target = tomorrow - timedelta(seconds=pre_seconds)
    wait_secs = (target - now).total_seconds()
    if wait_secs < 0:
        print(f"[{ts()}] Allerede passert midnatt, booker umiddelbart.")
        return
    if wait_secs > max_wait_minutes * 60:
        print(f"[{ts()}] FEIL: {wait_secs/60:.1f} min til midnatt — over grensen på {max_wait_minutes} min.")
        sys.exit(1)
    print(f"[{ts()}] Venter til {target.strftime('%H:%M:%S.%f')[:-3]} ({wait_secs:.1f} sek)...")
    print(f"[{ts()}] Midnatt er: {tomorrow.strftime('%Y-%m-%d %H:%M:%S')}")
    if wait_secs > 10:
        time.sleep(wait_secs - 10)
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            break
        time.sleep(0.001 if remaining <= 1 else 0.1)
    print(f"[{ts()}] GO! Tidspunkt: {datetime.now().strftime('%H:%M:%S.%f')}")


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


async def main():
    parser = argparse.ArgumentParser(description="MATCHi Tennis Booking - Sagene")
    parser.add_argument("--date", required=True)
    parser.add_argument("--times", nargs="+", required=True)
    parser.add_argument("--midnight", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--pre-seconds", type=float, default=0.3)
    parser.add_argument("--max-wait", type=int, default=10)
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
            ok = await login(page, MATCHI_EMAIL, MATCHI_PASSWORD)
            if not ok:
                sys.exit(1)
            all_slots = await get_available_slots(page, args.date)
            print(f"[{ts()}] Fant totalt {len(all_slots)} ledige slots")
            if args.check_only:
                print(f"\n[{ts()}] === Tilgjengelige slots ===")
                for s in all_slots:
                    print(f"  {s['time']:5s}  {s['court']}")
                return
            booked = False
            for preferred_time in args.times:
                matching = [s for s in all_slots if s["time"].startswith(preferred_time[:5])]
                if not matching:
                    print(f"[{ts()}] Kl {preferred_time} ikke ledig, prøver neste...")
                    continue
                slot = matching[0]
                success = await book_slot(page, slot)
                if success:
                    booked = True
                    print(f"\n[{ts()}] SUKSESS! Bane booket: {slot['time']} {slot['court']}")
                    break
            if not booked:
                print(f"\n[{ts()}] Ingen av tidene ({', '.join(args.times)}) ble booket.")
            if not args.headless:
                await asyncio.sleep(5)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
