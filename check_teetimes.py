import requests
from datetime import datetime, timedelta, time
import os
import json
from twilio.rest import Client

# ---------------- CONFIG ----------------
BASE_URL = "https://golfvancouver.cps.golf/onlineres/onlineapi/api/v1/onlinereservation/TeeTimes"

PLAYERS = os.getenv("PLAYERS", "ANY")
COURSE_IDS = os.getenv("COURSE_IDS", "1,2,3")

START_TIME = time(16, 0)
END_TIME = time(18, 0)
DAYS_AHEAD = 4

STATE_FILE = "state.json"

COURSE_NAMES = {
    "1": "Fraserview",
    "2": "McCleery",
    "3": "Langara",
}

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
    dates = []

    for i in range(1, DAYS_AHEAD + 1):
        d = today + timedelta(days=i)
        if not is_weekend(d):
            dates.append(d)

    return dates


def player_count_for_api():
    if str(PLAYERS).upper() == "ANY":
        return 0
    return int(PLAYERS)


def fetch_times(d):
    search_date = d.strftime("%a %b %-d %Y")

    params = {
        "searchDate": search_date,
        "holes": 18,
        "numberOfPlayer": player_count_for_api(),
        "courseIds": COURSE_IDS,
        "searchTimeType": 0,
        "teeOffTimeMin": 16,
        "teeOffTimeMax": 18,
        "isChangeTeeOffTime": "true",
        "teeSheetSearchView": 5,
        "classCode": "R",
        "defaultOnlineRate": "N",
        "isUseCapacityPricing": "false",
        "memberStoreId": 1,
        "searchType": 1,
    }

    headers = {
        "accept": "application/json, text/plain, */*",
        "user-agent": "Mozilla/5.0",
        "referer": "https://golfvancouver.cps.golf/onlineresweb/search-teetime",
    }

    r = requests.get(BASE_URL, params=params, headers=headers, timeout=20)

    print("Request URL:", r.url)

    if r.status_code == 403:
        print("403 Forbidden. The site may require a fresh browser session or authorization token.")

    r.raise_for_status()
    return r.json()


def extract_matches(data):
    matches = []

    def walk(obj):
        if isinstance(obj, dict):
            time_value = (
                obj.get("teeOffTime")
                or obj.get("teeTime")
                or obj.get("time")
                or obj.get("startTime")
            )

            course_id = str(
                obj.get("courseId")
                or obj.get("courseID")
                or obj.get("CourseId")
                or ""
            )

            if time_value:
                tee_time = parse_time(time_value)

                if tee_time and START_TIME <= tee_time <= END_TIME:
                    matches.append({
                        "course_id": course_id,
                        "time": tee_time.strftime("%H:%M")
                    })

            for value in obj.values():
                walk(value)

        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return matches


def parse_time(value):
    value = str(value)

    possible_formats = [
        "%H:%M:%S",
        "%H:%M",
        "%I:%M %p",
    ]

    if len(value) >= 8:
        possible_values = [value[-8:], value]
    else:
        possible_values = [value]

    for possible_value in possible_values:
        for fmt in possible_formats:
            try:
                return datetime.strptime(possible_value, fmt).time()
            except ValueError:
                continue

    return None


def send_sms(message):
    client.messages.create(
        body=message,
        from_=TWILIO_FROM,
        to=TWILIO_TO
    )


def make_key(date, course, tee_time):
    return f"{date}|{course}|{tee_time}"


# ---------------- MAIN ----------------
def main():
    state = load_state()
    new_matches = []

    for d in build_dates():
        date_str = d.strftime("%Y-%m-%d")

        try:
            data = fetch_times(d)
            matches = extract_matches(data)

            for match in matches:
                course_id = match["course_id"] or "?"
                tee_time = match["time"]

                key = make_key(date_str, course_id, tee_time)

                if key not in state:
                    state[key] = True
                    new_matches.append((date_str, course_id, tee_time))

        except Exception as e:
            print(f"Error {date_str}: {e}")

    if new_matches:
        message = ["⛳ New Tee Time Alert"]

        for date_str, course_id, tee_time in new_matches:
            course_name = COURSE_NAMES.get(course_id, f"Course {course_id}")
            message.append(f"{date_str} | {course_name} | {tee_time}")

        final_message = "\n".join(message)

        print(final_message)
        send_sms(final_message)
        save_state(state)

    else:
        print("No new tee times found.")


if __name__ == "__main__":
    main()
