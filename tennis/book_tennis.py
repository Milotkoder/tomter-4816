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


async def dismiss_cookies(page):
    """Lukk cookie-popup hvis den vises."""
    for sel in [
        "button:has-text('ALLOW NECESSARY')",
        "button:has-text('Allow necessary')",
        "button:has-text('Godta')",
        "button:has-text('Accept')",
        "button:has-text('OK')",
        "[id*='cookie'] button",
        "[class*='cookie'] button",
        ".cc-btn",
    ]:
        try:
            btn = await page.wait_for_selector(sel, timeout=3000)
            if btn:
                await btn.click()
                print(f"[{ts()}] Cookie-popup lukket: {sel}")
                await page.wait_for_timeout(500)
                return
        except PlaywrightTimeout:
            continue


async def book_time(page, date: str, preferred_times: list) -> bool:
    url = f"{FACILITY_URL}?date={date}&sport=1"
    print(f"[{ts()}] Navigerer til {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    await dismiss_cookies(page)
    await page.wait_for_timeout(2000)

    for preferred_time in preferred_times:
        print(f"[{ts()}] Prover tid: {preferred_time}")

        import pytz
        from datetime import datetime as dt_cls
        oslo = pytz.timezone("Europe/Oslo")
        h, m = map(int, preferred_time.split(":"))
        y, mo, d = map(int, date.split("-"))
        local_dt = oslo.localize(dt_cls(y, mo, d, h, m, 0))
        target_ms = int(local_dt.timestamp() * 1000)
        print(f"[{ts()}]   Timestamp: {target_ms}")

        # Steg 1: Klikk btn-slot for å åpne collapse-panelet
        slot_btn_clicked = await page.evaluate(f"""() => {{
            const btn = document.querySelector('button.btn-slot[data-target="#642_{target_ms}"]');
            if (btn) {{
                btn.click();
                return true;
            }}
            return false;
        }}""")

        if not slot_btn_clicked:
            available = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('button.btn-slot'))
                    .map(b => b.getAttribute('data-target'))
                    .filter(Boolean);
            }""")
            print(f"[{ts()}]   Fant ikke tidsknapp. Tilgjengelige: {available[:6]}")
            await page.screenshot(path=f"debug_no_time_{preferred_time.replace(':', '')}.png", full_page=True)
            continue

        print(f"[{ts()}]   Klikket tidsknapp, venter på panel...")
        await page.wait_for_timeout(1000)

        # Steg 2: Klikk første a.slot.free inne i det åpnede panelet
        book_clicked = await page.evaluate(f"""() => {{
            const panel = document.querySelector('#642_{target_ms}');
            if (!panel) return 'panel ikke funnet';
            const link = panel.querySelector('a.slot.free');
            if (!link) return 'ingen ledig bane';
            link.click();
            return link.getAttribute('slotid') || 'klikket';
        }}""")

        if book_clicked in ('panel ikke funnet', 'ingen ledig bane'):
            print(f"[{ts()}]   {book_clicked}")
            await page.screenshot(path=f"debug_no_book_{preferred_time.replace(':', '')}.png", full_page=True)
            continue

        print(f"[{ts()}]   Klikket Book-lenke, slotId: {book_clicked}")

        # Steg 3: Vent på at modal lastes inn via AJAX
        try:
            await page.wait_for_selector('#userBookingModal .modal-footer, #userBookingModal button', timeout=10000)
        except PlaywrightTimeout:
            await page.screenshot(path=f"debug_no_modal_{preferred_time.replace(':', '')}.png", full_page=True)
            print(f"[{ts()}]   Modal ble ikke lastet")
            continue

        await page.wait_for_timeout(500)

        # Steg 4: Klikk NESTE inne i modalen
        neste_clicked = await page.evaluate("""() => {
            const modal = document.querySelector('#userBookingModal');
            if (!modal) return null;
            const buttons = Array.from(modal.querySelectorAll('button, a.btn'));
            const neste = buttons.find(b => {
                const t = (b.innerText || b.textContent || '').trim().toUpperCase();
                return t === 'NESTE' || t === 'NEXT' || t === 'NASTA';
            });
            if (neste) { neste.click(); return neste.innerText.trim(); }
            const primary = modal.querySelector('button.btn-primary, a.btn-primary');
            if (primary) { primary.click(); return 'primary: ' + primary.innerText.trim(); }
            return null;
        }""")

        if not neste_clicked:
            await page.screenshot(path=f"debug_no_neste_{preferred_time.replace(':', '')}.png", full_page=True)
            print(f"[{ts()}]   Fant ikke NESTE-knapp i modal")
            continue

        print(f"[{ts()}]   Klikket: {neste_clicked}")

        try:
            await page.wait_for_url(
                lambda url: "checkout" in url or "pay" in url,
                timeout=10_000
            )
            print(f"[{ts()}]   Checkout-side lastet: {page.url}")
        except PlaywrightTimeout:
            print(f"[{ts()}]   Advarsel: Forventet checkout-URL, men fikk: {page.url}")

        await page.wait_for_timeout(1500)

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

        content     = await page.content()
        current_url = page.url

        if any(x in content for x in ["Takk", "fullfort", "Tack", "bekraftad", "confirmed"]):
            print(f"[{ts()}] BOOKING VELLYKKET! Tid: {preferred_time}, dato: {date}")
            return True

        if any(x in current_url for x in ["confirm", "success", "thanks", "takk"]):
            print(f"[{ts()}] BOOKING VELLYKKET! (URL-sjekk) {current_url}")
            return True

        await page.screenshot(path=f"debug_uklar_{preferred_time.replace(':', '')}.png", full_page=True)
        print(f"[{ts()}]   Booking-status uklar. URL: {current_url} – prover neste tid")

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
        print(f"[{ts()}] FEIL: {wait_secs/60:.1f} min til midnatt — over grensen pa {max_wait_minutes} min.")
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
        print(f"[{ts()}] FEIL: MATCHI_EMAIL og MATCHI_PASSWORD ma vare satt som miljøvariabler.")
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
