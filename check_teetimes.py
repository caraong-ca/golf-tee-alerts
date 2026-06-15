import os
import json
import re
from datetime import datetime, timedelta, time
from twilio.rest import Client
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

STATE_FILE = "state.json"

GOLF_USERNAME = os.environ["GOLF_USERNAME"]
GOLF_PASSWORD = os.environ["GOLF_PASSWORD"]

TWILIO_FROM = os.environ["TWILIO_FROM_NUMBER"]
TWILIO_TO = os.environ["TWILIO_TO_NUMBER"]

START_TIME = time(16, 0)
END_TIME = time(18, 0)
DAYS_AHEAD = 4

COURSE_NAMES = ["Fraserview", "McCleery", "Langara"]

BASE_URL = "https://golfvancouver.cps.golf/onlineresweb/search-teetime"


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def is_weekend(d):
    return d.weekday() >= 5


def build_dates():
    today = datetime.now().date()
    dates = []

    for i in range(1, DAYS_AHEAD + 1):
        d = today + timedelta(days=i)
        if not is_weekend(d):
            dates.append(d)

    return dates


def parse_times_from_text(text):
    raw_times = re.findall(r"\b(?:[01]?\d|2[0-3]):[0-5]\d(?:\s?[APap][Mm])?\b|\b(?:1[0-2]|0?[1-9]):[0-5]\d\s?[APap][Mm]\b", text)
    results = []

    for raw in raw_times:
        raw = raw.strip()

        for fmt in ["%H:%M", "%I:%M %p", "%I:%M%p"]:
            try:
                parsed = datetime.strptime(raw.upper(), fmt).time()
                if START_TIME <= parsed <= END_TIME:
                    results.append(parsed.strftime("%H:%M"))
                break
            except ValueError:
                pass

    return sorted(set(results))


def send_sms(message):
    client = Client(
        os.environ["TWILIO_ACCOUNT_SID"],
        os.environ["TWILIO_AUTH_TOKEN"]
    )

    client.messages.create(
        body=message,
        from_=TWILIO_FROM,
        to=TWILIO_TO
    )


def click_if_visible(page, text, timeout=3000):
    try:
        page.get_by_text(text, exact=False).click(timeout=timeout)
        return True
    except Exception:
        return False


def login(page):
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)

    # Common cookie / consent popups
    click_if_visible(page, "Accept", timeout=2000)
    click_if_visible(page, "I Agree", timeout=2000)

    # Try to open login form
    for label in ["Login", "Log In", "Sign In", "My Account"]:
        if click_if_visible(page, label, timeout=3000):
            break

    page.wait_for_timeout(3000)

    # Try common username/email fields
    username_selectors = [
        "input[type='email']",
        "input[name='email']",
        "input[name='username']",
        "input[id*='email' i]",
        "input[id*='user' i]",
        "input[placeholder*='email' i]",
        "input[placeholder*='user' i]",
    ]

    password_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[id*='password' i]",
        "input[placeholder*='password' i]",
    ]

    username_filled = False
    for selector in username_selectors:
        try:
            page.locator(selector).first.fill(GOLF_USERNAME, timeout=5000)
            username_filled = True
            break
        except Exception:
            pass

    password_filled = False
    for selector in password_selectors:
        try:
            page.locator(selector).first.fill(GOLF_PASSWORD, timeout=5000)
            password_filled = True
            break
        except Exception:
            pass

    if not username_filled or not password_filled:
        page.screenshot(path="login_debug.png", full_page=True)
        raise RuntimeError("Could not find login fields. Saved login_debug.png.")

    for label in ["Login", "Log In", "Sign In", "Submit"]:
        if click_if_visible(page, label, timeout=3000):
            break

    page.wait_for_load_state("networkidle", timeout=60000)
    page.wait_for_timeout(5000)

    print("Login step completed.")


def check_date(page, d):
    date_string = d.strftime("%Y-%m-%d")
    url = f"{BASE_URL}?TeeOffTimeMin=0&TeeOffTimeMax=23"

    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)

    # Try filling date if a date input exists
    try:
        date_input = page.locator("input[type='date']").first
        date_input.fill(date_string, timeout=3000)
        page.keyboard.press("Enter")
        page.wait_for_timeout(3000)
    except Exception:
        pass

    # Try clicking/searching if needed
    for label in ["Search", "Find Tee Times", "Apply"]:
        click_if_visible(page, label, timeout=1500)

    page.wait_for_timeout(5000)

    text = page.inner_text("body")
    times = parse_times_from_text(text)

    matches = []

    for tee_time in times:
        # Course detection is imperfect from page text, so label as Vancouver Golf if needed.
        matches.append({
            "date": date_string,
            "course": "Vancouver Golf",
            "time": tee_time
        })

    print(f"{date_string}: found {len(matches)} possible times between 4–6 PM.")
    return matches


def main():
    state = load_state()
    new_matches = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            timezone_id="America/Vancouver",
            viewport={"width": 1440, "height": 1200},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        )

        page = context.new_page()

        login(page)

        for d in build_dates():
            try:
                matches = check_date(page, d)

                for match in matches:
                    key = f"{match['date']}|{match['course']}|{match['time']}"

                    if key not in state:
                        state[key] = True
                        new_matches.append(match)

            except Exception as e:
                print(f"Error checking {d}: {e}")
                page.screenshot(path=f"debug_{d}.png", full_page=True)

        browser.close()

    if new_matches:
        lines = ["⛳ New Tee Time Alert"]

        for match in new_matches:
            lines.append(f"{match['date']} | {match['course']} | {match['time']}")

        message = "\n".join(lines)
        print(message)
        send_sms(message)
        save_state(state)
    else:
        print("No new tee times found.")


if __name__ == "__main__":
    main()
