import os
import requests

TWILIO_SID = os.environ["TWILIO_SID"]
TWILIO_TOKEN = os.environ["TWILIO_TOKEN"]
TWILIO_FROM = os.environ["TWILIO_FROM"]
TWILIO_TO = os.environ["TWILIO_TO"]

def send_sms(msg):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
    data = {
        "From": TWILIO_FROM,
        "To": TWILIO_TO,
        "Body": msg
    }
    requests.post(url, data=data, auth=(TWILIO_SID, TWILIO_TOKEN))

# TEMP TEST MESSAGE
send_sms("🏌️ Golf alert system is working!")
print("Done")
