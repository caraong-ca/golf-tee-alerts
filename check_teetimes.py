import requests
from datetime import datetime, timedelta, time
import os
import re
import json
from twilio.rest import Client

# ---------------- CONFIG ----------------
BASE_URL = "https://golfvancouver.cps.golf/onlineres/onlineapi/api/v1/onlinereservation/TeeTimes"

PLAYER_COUNT = os.getenv("PLAYERS", "1")
COURSE_IDS = os.getenv("COURSE_IDS", "1,2,3").split(",")

START_TIME = time(16, 0)
END_TIME = time(18, 0)
DAYS_AHEAD = 4

STATE_FILE = "state.json"

# ---------------- TWILIO ----------------
client = Client(
    os.environ["TWILIO_ACCOUNT_SID"],
    os.environ["TWILIO_AUTH_TOKEN"]
)

TWILIO_FROM = os.environ["TWILIO_FROM_NUMBER"]
TWILIO_TO = os.environ["TWILIO_TO_NUMBER"]


# ---------------- STATE ----------------
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------------- HELPERS ----------------
def is_weekend(d):
    return d.weekday() >= 5


def build_dates():
    today = datetime.now().date()
    return [
        today + timedelta(days=i)
        for i in range(1, DAYS_AHEAD + 1)
        if not is_weekend(today + timedelta(days=i))
    ]


def fetch_times(date_str, course_id):
    params = {
        "Date": date_str,
        "Player": PLAYER_COUNT,
        "Hole": "18",
        "CourseId": course_id
    }

    r = requests.get(BASE_URL, params=params, timeout=15)
    r.raise_for_status()
    return r.text


def extract_times(html):
    return re.findall(r"(\d{1,2}:\d{2})", html)


def filter_times(times):
    results = []
    for t in times:
        try:
            parsed = datetime.strptime(t, "%H:%M").time()
            if START_TIME <= parsed <= END_TIME:
                results.append(t)
        except:
            continue
    return results


def send_sms(message):
    client.messages.create(
        body=message,
        from_=TWILIO_FROM,
        to=TWILIO_TO
    )


def make_key(date, course, t):
    return f"{date}|{course}|{t}"


# ---------------- MAIN ----------------
def main():
    state = load_state()
    new_matches = []

    for d in build_dates():
        date_str = d.strftime("%Y-%m-%d")

        for course_id in COURSE_IDS:
            try:
                html = fetch_times(date_str, course_id)
                times = extract_times(html)
                filtered = filter_times(times)

                for t in filtered:
                    key = make_key(date_str, course_id, t)

                    if key not in state:
                        state[key] = True
                        new_matches.append((date_str, course_id, t))

            except Exception as e:
                print(f"Error {date_str} course {course_id}: {e}")

    if new_matches:
        message = ["⛳ New Tee Time Alert"]

        for date_str, course_id, t in new_matches:
            message.append(f"{date_str} | Course {course_id} | {t}")

        final_message = "\n".join(message)

        print(final_message)
        send_sms(final_message)

        save_state(state)

    else:
        print("No new tee times found.")


if __name__ == "__main__":
    main()
