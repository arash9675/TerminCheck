import asyncio
from datetime import datetime
from pathlib import Path
import nest_asyncio
import requests
from playwright.async_api import async_playwright

CHECK_INTERVAL = 180
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"
SCREENSHOT_DIR = Path("artifacts")
HTML_DIR = SCREENSHOT_DIR / "html"
DAILY_SUMMARY_HOUR = 21
DEBUG_SCREENSHOT_EVERY_LOOPS = 20


def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=30)
    except Exception as exc:
        print(f"Telegram sendMessage failed: {exc}")


def send_telegram_photo(photo_path: Path, caption: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        with photo_path.open("rb") as image_file:
            requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
                files={"photo": image_file},
                timeout=60,
            )
    except Exception as exc:
        print(f"Telegram sendPhoto failed: {exc}")


def send_telegram_document(file_path: Path, caption: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    try:
        with file_path.open("rb") as doc_file:
            requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
                files={"document": doc_file},
                timeout=60,
            )
    except Exception as exc:
        print(f"Telegram sendDocument failed: {exc}")


def summarize_page_text(raw_text: str, max_chars: int = 800) -> str:
    cleaned = " ".join(raw_text.split())
    return cleaned[:max_chars] + ("..." if len(cleaned) > max_chars else "")


def create_page_artifacts(page_type: str, stamp: str):
    screenshot_path = SCREENSHOT_DIR / f"termin_{page_type}_{stamp}.png"
    html_path = HTML_DIR / f"termin_{page_type}_{stamp}.html"
    return screenshot_path, html_path


async def capture_page_artifacts(page, page_type: str, stamp: str):
    screenshot_path, html_path = create_page_artifacts(page_type, stamp)
    await page.screenshot(path=str(screenshot_path), full_page=True)
    html_path.write_text(await page.content(), encoding="utf-8")
    return screenshot_path, html_path


def maybe_send_daily_summary(
    now,
    last_summary_date,
    checks_today,
    no_slot_today,
    slot_alerts_today,
    unknown_state_today,
    errors_today,
    last_success_at,
):
    if now.hour < DAILY_SUMMARY_HOUR or last_summary_date == now.date():
        return (
            last_summary_date,
            checks_today,
            no_slot_today,
            slot_alerts_today,
            unknown_state_today,
            errors_today,
        )

    summary = (
        f"Daily checker summary ({now.strftime('%Y-%m-%d')})\n"
        f"Checks: {checks_today}\n"
        f"No-slot pages: {no_slot_today}\n"
        f"Slot alerts: {slot_alerts_today}\n"
        f"Unknown states: {unknown_state_today}\n"
        f"Errors: {errors_today}\n"
        f"Last successful check: {last_success_at or 'n/a'}"
    )
    send_telegram(summary)
    return now.date(), 0, 0, 0, 0, 0


async def check_termin():
    loop_count = 0
    last_alert_signature = None
    last_summary_date = None

    checks_today = 0
    no_slot_today = 0
    slot_alerts_today = 0
    unknown_state_today = 0
    errors_today = 0
    last_success_at = None

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    HTML_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
        except Exception as e:
            print("Playwright Chromium failed to start. Run on the VPS: python3 -m playwright install --with-deps chromium")
            raise RuntimeError(f"Failed to launch Chromium: {e}") from e

        page = await browser.new_page()
        while True:
            try:
                loop_count += 1
                checks_today += 1
                print(f"\n--- Starting new session (loop {loop_count}) ---")
                await page.goto(
                    "https://termine.bonn.de/m/auslaenderamt/extern/calendar/session_expired?uid=163e5a5b-3edb-4de1-97c7-b4922526085f&lang=de",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await page.get_by_role("link", name="Neuen Termin buchen").click(timeout=20000)
                postcode_input = page.get_by_test_id("popup_input_field-f5d4648e-30f4-4825-a5ed-72b1803548cc")
                await postcode_input.click(timeout=20000)
                await postcode_input.fill("53119", timeout=20000)
                await page.get_by_test_id("next_popup").click(timeout=20000)
                await page.get_by_role("group", name="Aufenthaltstitel zum Zweck der Bildung").locator("i").click(timeout=20000)
                await page.get_by_label("Aufenthaltstitel zum Zwecke").select_option("1")
                await page.get_by_test_id("button_next").click(timeout=20000)
                body_text = await page.locator("body").inner_text()
                print("Calendar page text preview:", body_text[:1000])
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                has_no_slot_text = (
                    "Keine freien Termine gefunden" in body_text
                    or "Keine freien Termine" in body_text
                )
                page_summary = summarize_page_text(body_text)
                last_success_at = timestamp

                if has_no_slot_text:
                    print("No free dates found.")
                    no_slot_today += 1
                    if loop_count % DEBUG_SCREENSHOT_EVERY_LOOPS == 1:
                        artifact_stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        screenshot_path, html_path = await capture_page_artifacts(page, "debug", artifact_stamp)

                        send_telegram(f"Still running - no free dates as of {timestamp}")
                        debug_caption = (
                            f"Debug no-slot snapshot at {timestamp}\n"
                            f"URL: {page.url}\n\n"
                            f"Preview: {page_summary}"
                        )
                        send_telegram_photo(screenshot_path, debug_caption)
                        send_telegram_document(html_path, "HTML snapshot for no-slot debug check")
                else:
                    artifact_stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    screenshot_path, html_path = await capture_page_artifacts(page, "alert", artifact_stamp)

                    alert_signature = f"{page.url}|{page_summary[:200]}"
                    is_probable_slot = (
                        "Kalender" in body_text
                        or "Termin auswählen" in body_text
                        or "verfügbar" in body_text.lower()
                        or "verfugbar" in body_text.lower()
                    )

                    if is_probable_slot:
                        slot_alerts_today += 1
                        print("SLOT FOUND!")
                        send_telegram(
                            "Termin may be available now in Bonn. Screenshot is attached."
                        )
                        caption = (
                            f"Slot alert at {timestamp}\n"
                            f"URL: {page.url}\n\n"
                            f"Preview: {page_summary}"
                        )
                        if alert_signature != last_alert_signature:
                            send_telegram_photo(screenshot_path, caption)
                            send_telegram_document(html_path, "HTML snapshot for slot alert")
                            last_alert_signature = alert_signature
                        else:
                            print("Duplicate slot signal; photo not resent.")
                    else:
                        unknown_state_today += 1
                        print("Unexpected page state detected.")
                        caption = (
                            f"Unexpected state at {timestamp}\n"
                            f"URL: {page.url}\n\n"
                            f"Preview: {page_summary}"
                        )
                        if alert_signature != last_alert_signature:
                            send_telegram_photo(screenshot_path, caption)
                            send_telegram_document(html_path, "HTML snapshot for unexpected page state")
                            send_telegram("Checker reached an unknown page state. Screenshot sent for review.")
                            last_alert_signature = alert_signature
                        else:
                            print("Duplicate unknown-state signal; photo not resent.")

                now = datetime.now()
                (
                    last_summary_date,
                    checks_today,
                    no_slot_today,
                    slot_alerts_today,
                    unknown_state_today,
                    errors_today,
                ) = maybe_send_daily_summary(
                    now,
                    last_summary_date,
                    checks_today,
                    no_slot_today,
                    slot_alerts_today,
                    unknown_state_today,
                    errors_today,
                    last_success_at,
                )

                print(f"Waiting {CHECK_INTERVAL} seconds...")
                await asyncio.sleep(CHECK_INTERVAL)
            except Exception as e:
                errors_today += 1
                print("Error, restarting session:", e)
                await page.close()
                page = await browser.new_page()
        await browser.close()


async def main():
    await check_termin()


if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
