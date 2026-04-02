"""
MATCHi Tennis Booking Bot - Sagene
===================================
Booker tennisbane på Sagene via MATCHi.

Flyt:
  1. Logg inn
  2. Gå til /facilities/sagene?date=DATO
  3. Klikk ønsket tidsknapp (f.eks. 20:00)
  4. Klikk BOOK på første ledige bane
  5. Klikk NESTE i modal
  6. Klikk "Bekreft bestilling" på checkout-siden
  7. Bekreft "Takk! Bestillingen din er fullført."

Bruk:
  python book_tennis.py --date 2026-04-09 --times 19:00 20:00
  python book_tennis.py --date 2026-04-09 --times 19:00 20:00 --midnight
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

MATCHI_EMAIL    = os.getenv("MATCHI_EMAIL")
MATCHI_PASSWORD = os.getenv("MATCHI_PASSWORD")
FACILITY_URL    = "https://www.matchi.se/facilities/sagene"
LOGIN_URL       = "https://www.matchi.se/login/auth"


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


async def login(page, email: str, password: str) -> bool:
    print(f"[{ts()}] Logger inn som {email}...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")

    email_sel = 'input[type="email"], input[name="email"], input[name="j_username"]'
    pass_sel  = 'input[type="password"], input[name="j_password"]'

    try:
        await page.wait_for_selector(email_sel, timeout=10_000)
    except PlaywrightTimeout:
        await page.screenshot(path="debug_login_page.png", full_page=True)
        print(f"[{ts()}] FEIL: Fant ikke innloggingsfelt. Skjermbilde lagret.")
        return False

    await page.fill(email_sel, email)
    await page.fill(pass_sel, password)
    await page.click('button[type="submit"], input[type="submit"], button:has-text("Log in"), button:has-text("Logg inn")')

    try:
        await page.wait_for_url(lambda url: "login" not in url, timeout=10_000)
        print(f"[{ts()}] Innlogget OK")
        return True
    except PlaywrightTimeout:
        await page.screenshot(path="debug_login_failed.png", full_page=True)
        print(f"[{ts()}] Innlogging feilet. Skjermbilde lagret.")
        return False


async def book_time(page, date: str, preferred_times: list) -> bool:
    """
    Hovedflyt: naviger, velg tid, velg første ledige bane,
    bekreft modal, bekreft checkout.
    """
    url = f"{FACILITY_URL}?date={date}&sport=1"
    print(f"[{ts()}] Navigerer til {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    for preferred_time in preferred_times:
        print(f"[{ts()}] Prover tid: {preferred_time}")

        # -- Steg 1: Klikk tidsknapp ------------------------------------─
        # Knappene vises som "20 00" / "21 00" på siden
        hour = preferred_time.split(":")[0]   # "20"
        clicked = False

        candidates = [
            f"button:has-text('{preferred_time}')",
            f"a:has-text('{preferred_time}')",
            f"[data-time='{preferred_time}']",
            f"button:has-text('{hour}')",        # fallback: bare timen
            f".time-slot:has-text('{hour}')",
            f"td:has-text('{hour}') a",
        ]
        for sel in candidates:
            try:
                el = await page.wait_for_selector(sel, timeout=2000)
                if el:
                    await el.click()
                    clicked = True
                    print(f"[{ts()}]   Klikket tidsknapp med selector: {sel}")
                    break
            except PlaywrightTimeout:
                continue

        if not clicked:
            await page.screenshot(path=f"debug_no_time_{preferred_time.replace(':', '')}.png", full_page=True)
            print(f"[{ts()}]   Fant ikke tidsknapp for {preferred_time} – prøver neste tid")
            continue

        await page.wait_for_timeout(1500)

        # -- Steg 2: Klikk BOOK på første ledige bane --------------------
        book_btn = None
        for sel in [
            "button:has-text('BOOK')",
            "a:has-text('BOOK')",
            "button:has-text('Book')",
            "a:has-text('Book')",
            ".btn-success",
            ".btn-primary:has-text('BOK')",
        ]:
            btns = await page.query_selector_all(sel)
            if btns:
                book_btn = btns[0]
                print(f"[{ts()}]   Fant BOOK-knapp med selector: {sel}")
                break

        if not book_btn:
            await page.screenshot(path=f"debug_no_book_{preferred_time.replace(':', '')}.png", full_page=True)
            print(f"[{ts()}]   Ingen ledige baner for {preferred_time} – prøver neste tid")
            continue

        await book_btn.click()
        await page.wait_for_timeout(1500)

        # -- Steg 3: Klikk NESTE i modal --------------------------------─
        neste_btn = None
        for sel in [
            "button:has-text('NESTE')",
            "button:has-text('Neste')",
            "button:has-text('Next')",
            "button:has-text('Nästa')",
            ".modal-footer button.btn-primary",
            ".modal button.btn-primary",
            "button.btn-primary",
        ]:
            try:
                neste_btn = await page.wait_for_selector(sel, timeout=5000)
                if neste_btn:
                    print(f"[{ts()}]   Fant NESTE-knapp med selector: {sel}")
                    break
            except PlaywrightTimeout:
                continue

        if not neste_btn:
            await page.screenshot(path=f"debug_no_neste_{preferred_time.replace(':', '')}.png", full_page=True)
            print(f"[{ts()}]   Fant ikke NESTE-knapp i modal")
            continue

        await neste_btn.click()

        # -- Steg 4: Vent på checkout-siden ------------------------------
        try:
            await page.wait_for_url(
                lambda url: "checkout" in url or "pay" in url,
                timeout=10_000
            )
            print(f"[{ts()}]   Checkout-side lastet: {page.url}")
        except PlaywrightTimeout:
            print(f"[{ts()}]   Advarsel: Forventet checkout-URL, men fikk: {page.url}")

        await page.wait_for_timeout(1500)

        # -- Steg 5: Klikk "Bekreft bestilling" --------------------------
        bekreft_btn = None
        for sel in [
            "button:has-text('Bekreft bestilling')",
            "button:has-text('Confirm')",
            "button:has-text('Bekräfta beställning')",
            "button:has-text('Bekräfta')",
            "button.btn-primary",
            "input[type='submit']",
        ]:
            try:
                bekreft_btn = await page.wait_for_selector(sel, timeout=5000)
                if bekreft_btn:
                    print(f"[{ts()}]   Fant Bekreft-knapp med selector: {sel}")
                    break
            except PlaywrightTimeout:
                continue

        if not bekreft_btn:
            await page.screenshot(path=f"debug_no_bekreft_{preferred_time.replace(':', '')}.png", full_page=True)
            print(f"[{ts()}]   Fant ikke 'Bekreft bestilling'-knapp")
            continue

        await bekreft_btn.click()
        await page.wait_for_timeout(2000)

        # -- Steg 6: Sjekk bekreftelse ----------------------------------─
        content     = await page.content()
        current_url = page.url

        if any(x in content for x in ["Takk", "fullført", "Tack", "bekräftad", "confirmed"]):
            print(f"[{ts()}] BOOKING VELLYKKET! Tid: {preferred_time}, dato: {date}")
            return True

        if any(x in current_url for x in ["confirm", "success", "thanks", "takk"]):
            print(f"[{ts()}] BOOKING VELLYKKET! (URL-sjekk) {current_url}")
            return True

        await page.screenshot(path=f"debug_uklar_{preferred_time.replace(':', '')}.png", full_page=True)
        print(f"[{ts()}]   Booking-status uklar. URL: {current_url} – prøver neste tid")

    print(f"[{ts()}] Ingen av tidene ble booket: {', '.join(preferred_times)}")
    return False


def wait_for_midnight(pre_seconds: float = 0.3, max_wait_minutes: int = 10):
    now      = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    target   = tomorrow - timedelta(seconds=pre_seconds)
    wait_secs = (target - now).total_seconds()

    if wait_secs < 0:
        print(f"[{ts()}] Allerede passert midnatt, booker umiddelbart.")
        return
    if wait_secs > max_wait_minutes * 60:
        print(f"[{ts()}] FEIL: {wait_secs/60:.1f} min til midnatt — over grensen på {max_wait_minutes} min.")
        sys.exit(1)

    print(f"[{ts()}] Venter til {target.strftime('%H:%M:%S.%f')[:-3]} ({wait_secs:.1f} sek)...")
    if wait_secs > 10:
        time.sleep(wait_secs - 10)
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            break
        time.sleep(0.001 if remaining <= 1 else 0.1)
    print(f"[{ts()}] GO! Tidspunkt: {datetime.now().strftime('%H:%M:%S.%f')}")


async def main():
    parser = argparse.ArgumentParser(description="MATCHi Tennis Booking - Sagene")
    parser.add_argument("--date",        required=True)
    parser.add_argument("--times",       nargs="+", required=True)
    parser.add_argument("--midnight",    action="store_true")
    parser.add_argument("--headless",    action="store_true")
    parser.add_argument("--pre-seconds", type=float, default=0.3)
    parser.add_argument("--max-wait",    type=int,   default=10)
    args = parser.parse_args()

    print(f"[{ts()}] === MATCHi Tennis Booking ===")
    print(f"[{ts()}] Dato: {args.date}")
    print(f"[{ts()}] Ønskede tider: {', '.join(args.times)}")
    print(f"[{ts()}] Modus: {'Midnatt' if args.midnight else 'Umiddelbar'}")

    if not MATCHI_EMAIL or not MATCHI_PASSWORD:
        print(f"[{ts()}] FEIL: MATCHI_EMAIL og MATCHI_PASSWORD må være satt som miljøvariabler.")
        sys.exit(1)

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
            if not await login(page, MATCHI_EMAIL, MATCHI_PASSWORD):
                sys.exit(1)

            success = await book_time(page, args.date, args.times)
            sys.exit(0 if success else 1)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
