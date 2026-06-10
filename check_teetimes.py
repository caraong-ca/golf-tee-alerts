import requests
from datetime import datetime, timedelta, time
import os
import re
from twilio.rest import Client

# ---------------- CONFIG ----------------
BASE_URL = "https://golfvancouver.cps.golf/onlineresweb/search-teetime"

PLAYER_COUNT = os.getenv("PLAYERS", "1")
COURSE_IDS = os.getenv("COURSE_IDS", "1,2,3").split(",")

START_TIME = time(16, 0)  # 4:00 PM
END_TIME = time(18, 0)    # 6:00 PM
DAYS_AHEAD = 4

# -------- TWILIO CONFIG (ENV VARS) --------
TWILIO_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM = os.environ["TWILIO_FROM_NUMBER"]
TWILIO_TO = os.environ["TWILIO_TO_NUMBER"]

client = Client(TWILIO_SID, TWILIO_TOKEN)


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


# ---------------- MAIN ----------------
def main():
    all_matches = []

    for d in build_dates():
        date_str = d.strftime("%Y-%m-%d")

        for course_id in COURSE_IDS:
            try:
                html = fetch_times(date_str, course_id)
                times = extract_times(html)
                filtered = filter_times(times)

                if filtered:
                    all_matches.append({
                        "date": date_str,
                        "course": course_id,
                        "times": filtered
                    })

            except Exception as e:
                print(f"Error {date_str} course {course_id}: {e}")

    # -------- NOTIFY ONLY IF MATCHES --------
    if all_matches:
        message_lines = ["⛳ Tee Time Alert Found!"]

        for m in all_matches:
            message_lines.append(
                f"{m['date']} | Course {m['course']} | {', '.join(m['times'])}"
            )

        message = "\n".join(message_lines)

        print(message)
        send_sms(message)

    else:
        print("No matches found.")


if __name__ == "__main__":
    main()
