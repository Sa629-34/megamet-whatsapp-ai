"""
Megamet India - WhatsApp FAQ Bot + Automatic Festival Poster Sender
--------------------------------------------------------------------
Runs on Render. Two jobs:

1. FAQ BOT: replies to customers' incoming WhatsApp messages with fixed
   keyword-based answers (free, no paid AI API).

2. FESTIVAL POSTER SENDER: when an outside timer (cron-job.org) calls
   /run-festival-check every morning, the app looks at data/festival_calendar.csv.
   If TODAY (India time) is a festival, it uploads that festival's poster to
   WhatsApp and sends the approved template (with the poster as its image
   header) to data/contacts.csv in small batches. Nobody has to run anything.

Why an outside timer: Render's free plan puts the app to sleep when idle, so
an in-app clock would never fire. The outside timer's request wakes it up.

Every festival needs its template APPROVED in WhatsApp Manager beforehand;
the template name must match template_name in data/festival_calendar.csv.
"""

import os
import io
import csv
import json
import time
import hmac
import tempfile
import threading
from datetime import datetime, date, timedelta, timezone

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IST = timezone(timedelta(hours=5, minutes=30))

# =========================================================
# CONFIG - set these in Render's "Environment" tab
# =========================================================

WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "1427617750424162")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "megamet_verify_123")  # must match the Meta dashboard

# Secret password for the festival endpoints (anyone without it is rejected).
FESTIVAL_RUN_KEY = os.environ.get("FESTIVAL_RUN_KEY", "")

# Optional: a Google Sheet (shared "anyone with the link can view") with columns
# name, phone, religion. If set, contacts are read from it so new numbers can be
# added by just editing the sheet. If not set / unreachable, data/contacts.csv is used.
CONTACTS_SHEET_ID = os.environ.get("CONTACTS_SHEET_ID", "")

BATCH_SIZE = int(os.environ.get("FESTIVAL_BATCH_SIZE", "12"))
BATCH_DELAY_SECONDS = int(os.environ.get("FESTIVAL_BATCH_DELAY_SECONDS", "90"))
MESSAGE_DELAY_SECONDS = float(os.environ.get("FESTIVAL_MESSAGE_DELAY_SECONDS", "1"))
GRAPH_URL = "https://graph.facebook.com/v21.0"

# =========================================================
# FAQ REPLIES - fixed, hardcoded answers. No AI/paid API used.
# To add a new question/keyword, add it to the lists below.
# =========================================================

GREETING_KEYWORDS = [
    "thank", "thanks", "thankyou", "dhanyavaad", "dhanyawad",
    "same to you", "happy anant", "happy chaturdashi", "happy ganesh",
    "happy navratri", "happy dussehra", "happy diwali", "happy dhanteras",
    "happy gandhi", "ganpati", "shubhkamna", "welcome", "🙏", "👍", "❤️", "nice", "good",
]

PRICE_KEYWORDS = [
    "price", "rate", "cost", "quote", "quotation", "kitna", "kimat",
    "keemat", "negotiat", "discount", "budget", "what is the price",
]

DELIVERY_KEYWORDS = [
    "deliver", "delivery", "location", "city", "state", "where",
    "shipping", "transport", "reach", "area", "pincode",
    "where do you deliver",
]

SAMPLE_MOQ_KEYWORDS = [
    "sample", "moq", "minimum order", "minimum quantity", "trial",
    "sample chahiye",
]

ABOUT_KEYWORDS = [
    "who are you", "what is this", "about", "company", "kya hai",
    "kaun ho", "what do you do", "megamet", "about your company",
]

BUSINESS_KEYWORDS = [
    "wood", "timber", "lakdi", "pine", "kd wood", "kiln", "supply",
    "furniture", "packaging", "construction", "import", "quantity",
    "order", "product", "requirement", "need",
]

CONTACT_KEYWORDS = [
    "contact number", "sales contact", "mail id", "email id", "your email",
    "your number", "phone number", "mobile number", "contact details",
    "sales number", "whatsapp number", "call number", "mail sales contact",
]

CONTACT_INFO = (
    "\n\nSales Contact: Chintan Vora - +91 98708 63388\n"
    "Sales Contact: Bhaskar Mehta - +91 89766 08029\n"
    "Email: mail@megamet.in\n"
    "Website: www.megamet.in"
)

CONTACT_REPLY = (
    "Sure! Here are our contact details:" + CONTACT_INFO
)

GREETING_REPLY = (
    "Thank you so much! Warm wishes to you and your family from "
    "Team Megamet India 🙏" + CONTACT_INFO
)

PRICE_REPLY = (
    "Thanks for your interest! Exact pricing/quotes are shared by our "
    "sales team based on your requirement. Please share your name, "
    "product & quantity needed, and your city - our team will contact "
    "you shortly." + CONTACT_INFO
)

DELIVERY_REPLY = (
    "We deliver our timber (KD pine wood) to various locations across "
    "India. Please share your city/state and requirement - our sales "
    "team will confirm delivery details and timelines." + CONTACT_INFO
)

SAMPLE_MOQ_REPLY = (
    "Thanks for asking! Sample availability and minimum order quantity "
    "details are confirmed by our sales team based on the product. "
    "Please share your requirement and city, and our team will get back "
    "to you." + CONTACT_INFO
)

ABOUT_REPLY = (
    "Megamet India Pvt Ltd is the largest importer and distributor of KD "
    "(kiln-dried) pine wood from Europe, Russia and the Baltic countries, "
    "supplying across India for sustainable timber, packaging, "
    "furniture manufacturing and construction needs." + CONTACT_INFO
)

BUSINESS_REPLY = (
    "Hello! Megamet India Pvt Ltd imports KD (kiln-dried) pine wood from "
    "Europe and the Baltic countries and delivers it across India. "
    "Could you share your requirement (product/quantity/location)? Our "
    "sales team will reach out to you shortly with details." + CONTACT_INFO
)

DEFAULT_REPLY = (
    "Hello! This is Megamet India's WhatsApp - we import and supply "
    "timber (pine wood) across India. Please share your requirement or "
    "question, and our team will get back to you shortly." + CONTACT_INFO
)


def get_faq_reply(user_message: str) -> str:
    """Simple keyword-matching FAQ bot - no paid AI, free to run."""
    text = user_message.lower()

    if any(word in text for word in CONTACT_KEYWORDS):
        return CONTACT_REPLY
    if any(word in text for word in PRICE_KEYWORDS):
        return PRICE_REPLY
    if any(word in text for word in SAMPLE_MOQ_KEYWORDS):
        return SAMPLE_MOQ_REPLY
    if any(word in text for word in DELIVERY_KEYWORDS):
        return DELIVERY_REPLY
    if any(word in text for word in ABOUT_KEYWORDS):
        return ABOUT_REPLY
    if any(word in text for word in BUSINESS_KEYWORDS):
        return BUSINESS_REPLY
    if any(word in text for word in GREETING_KEYWORDS):
        return GREETING_REPLY

    return DEFAULT_REPLY


# =========================================================
# WEBHOOK VERIFICATION (Meta sends a one-time GET request during setup)
# =========================================================

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403


# =========================================================
# INCOMING MESSAGES (Meta POSTs the customer's message here)
# =========================================================

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    print("Incoming webhook:", json.dumps(data))

    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            # This is a status update (delivered/read), not a message - ignore it
            return "OK", 200

        message = value["messages"][0]
        from_number = message["from"]
        msg_type = message.get("type")

        if msg_type != "text":
            reply_text = "We currently only support text messages. Please type your question and send it."
        else:
            user_text = message["text"]["body"]
            reply_text = get_faq_reply(user_text)

        send_whatsapp_message(from_number, reply_text)

    except (KeyError, IndexError) as e:
        print("Parse error (probably a status update, ignoring):", e)

    return "OK", 200


# =========================================================
# SENDING THE REPLY BACK ON WHATSAPP
# =========================================================

def send_whatsapp_message(to_number: str, text: str):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    print("Send response:", response.status_code, response.text)


@app.route("/", methods=["GET"])
def health_check():
    return "Megamet WhatsApp FAQ bot is running.", 200



# =========================================================
# AUTOMATIC FESTIVAL POSTER SENDER
# =========================================================

CALENDAR_FILE = os.path.join(BASE_DIR, "data", "festival_calendar.csv")
CONTACTS_FILE = os.path.join(BASE_DIR, "data", "contacts.csv")
STATE_FILE = os.path.join(tempfile.gettempdir(), "megamet_festival_state.json")

_state_lock = threading.Lock()
_running = set()  # keys of festival runs in progress (this process)


def log(*args):
    print("[festival]", *args, flush=True)


def today_ist() -> date:
    return datetime.now(IST).date()


def _load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"done": {}, "runs": []}


def _save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        log("could not save state file:", e)


_state = _load_state()


def _read_csv_text(text: str):
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in row.items()})
    return rows


def load_calendar():
    with open(CALENDAR_FILE, encoding="utf-8-sig") as f:
        return _read_csv_text(f.read())


def load_contacts():
    if CONTACTS_SHEET_ID:
        try:
            url = f"https://docs.google.com/spreadsheets/d/{CONTACTS_SHEET_ID}/export?format=csv"
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            rows = _read_csv_text(r.content.decode("utf-8-sig"))
            if rows and "phone" in rows[0]:
                log(f"contacts loaded from Google Sheet ({len(rows)} rows)")
                return rows
            log("Google Sheet has no 'phone' column - using local contacts file instead")
        except Exception as e:
            log("could not read Google Sheet, using local contacts file:", e)
    with open(CONTACTS_FILE, encoding="utf-8-sig") as f:
        rows = _read_csv_text(f.read())
    log(f"contacts loaded from data/contacts.csv ({len(rows)} rows)")
    return rows


def normalize_number(raw):
    """Return a 12-digit Indian number (91 + 10 digits) or None if invalid."""
    s = str(raw or "").strip()
    if s.endswith(".0"):  # spreadsheet float like 9886758594.0
        s = s[:-2]
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        digits = "91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    return None


def build_recipients(contacts, exclude_religions):
    """Filter by religion exclusions, validate numbers, remove duplicate numbers."""
    excluded = {x.strip().lower() for x in exclude_religions.split("|") if x.strip()}
    seen, recipients, invalid, excluded_count = set(), [], [], 0
    for row in contacts:
        name = row.get("name", "Unknown")
        if row.get("religion", "").strip().lower() in excluded:
            excluded_count += 1
            continue
        number = normalize_number(row.get("phone"))
        if not number:
            invalid.append({"name": name, "phone": row.get("phone", "")})
            continue
        if number in seen:
            continue
        seen.add(number)
        recipients.append({"name": name, "phone": number})
    return recipients, invalid, excluded_count


def _auth_headers(json_body=True):
    h = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def upload_poster(poster_path: str) -> str:
    """Upload the poster to WhatsApp and return its media id (valid for 30 days;
    we upload fresh on every run, so it never expires on us)."""
    full = os.path.join(BASE_DIR, poster_path)
    ext = os.path.splitext(full)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    with open(full, "rb") as f:
        r = requests.post(
            f"{GRAPH_URL}/{PHONE_NUMBER_ID}/media",
            headers=_auth_headers(json_body=False),
            data={"messaging_product": "whatsapp"},
            files={"file": (os.path.basename(full), f, mime)},
            timeout=60,
        )
    data = r.json()
    if "id" not in data:
        raise RuntimeError(f"poster upload failed: {data}")
    return data["id"]


def send_template_with_image(to_number: str, template_name: str, media_id: str):
    """Returns (ok, response_json). Retries only for temporary errors."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en"},
            "components": [
                {"type": "header", "parameters": [{"type": "image", "image": {"id": media_id}}]}
            ],
        },
    }
    result = {}
    for attempt in range(1, 4):
        try:
            r = requests.post(
                f"{GRAPH_URL}/{PHONE_NUMBER_ID}/messages",
                headers=_auth_headers(), data=json.dumps(payload), timeout=30,
            )
            try:
                result = r.json()
            except ValueError:
                result = {"error": {"code": r.status_code, "message": r.text[:200]}}
            if "messages" in result and "error" not in result:
                return True, result
            code = (result.get("error") or {}).get("code")
            temporary = r.status_code >= 500 or r.status_code == 429 or code in (4, 80007, 130429)
            if not temporary:
                return False, result
        except requests.RequestException as e:
            result = {"error": {"code": "network", "message": str(e)[:200]}}
        time.sleep(5 * attempt)
    return False, result


def run_festival(festival: dict, recipients: list, run_key: str):
    """Sends one festival's poster to all recipients in batches (runs in a background thread)."""
    summary = {
        "festival": festival["festival"], "template": festival["template_name"],
        "date": festival["date"], "total": len(recipients), "sent": 0, "failed": [],
        "started": datetime.now(IST).isoformat(timespec="seconds"), "finished": None,
        "aborted": None,
    }
    try:
        media_id = upload_poster(festival["poster_file"])
        log(f"{festival['festival']}: poster uploaded (media id {media_id}), "
            f"sending to {len(recipients)} contacts in batches of {BATCH_SIZE}")
        auth_failures = 0
        for start in range(0, len(recipients), BATCH_SIZE):
            batch = recipients[start:start + BATCH_SIZE]
            log(f"{festival['festival']}: batch {start // BATCH_SIZE + 1} ({len(batch)} contacts)")
            for person in batch:
                ok, result = send_template_with_image(person["phone"], festival["template_name"], media_id)
                if ok:
                    summary["sent"] += 1
                    auth_failures = 0
                else:
                    err = result.get("error", {})
                    summary["failed"].append({
                        "name": person["name"], "phone": person["phone"],
                        "code": err.get("code"), "message": err.get("message"),
                    })
                    log(f"  FAILED {person['name']} ({person['phone']}): {err}")
                    auth_failures = auth_failures + 1 if err.get("code") == 190 else 0
                    if auth_failures >= 3:
                        summary["aborted"] = ("Access token rejected (error 190) - stopped. "
                                              "Create a new token and update WHATSAPP_ACCESS_TOKEN on Render.")
                        raise RuntimeError(summary["aborted"])
                time.sleep(MESSAGE_DELAY_SECONDS)
            if start + BATCH_SIZE < len(recipients):
                time.sleep(BATCH_DELAY_SECONDS)
    except Exception as e:
        summary["aborted"] = summary["aborted"] or str(e)
        log(f"{festival['festival']}: STOPPED - {e}")
    finally:
        summary["finished"] = datetime.now(IST).isoformat(timespec="seconds")
        with _state_lock:
            _running.discard(run_key)
            _state["runs"] = (_state["runs"] + [summary])[-20:]
            if summary["sent"] > 0:  # a run that sent nothing is allowed to be retried
                _state["done"][run_key] = summary["finished"]
            _save_state(_state)
        log(f"{festival['festival']}: finished - {summary['sent']} sent, {len(summary['failed'])} failed"
            + (f", STOPPED: {summary['aborted']}" if summary["aborted"] else ""))


def check_festivals(on_date: date, dry_run: bool):
    """Looks at the calendar for on_date; starts sending (or just reports, if dry_run)."""
    report = []
    for fest in [r for r in load_calendar() if r.get("date") == on_date.isoformat()]:
        run_key = f"{fest['date']}|{fest.get('template_name', '')}"
        item = {"festival": fest.get("festival"), "template": fest.get("template_name"), "date": fest["date"]}

        if not fest.get("template_name") or not fest.get("poster_file"):
            item["status"] = "skipped - template_name or poster_file missing in calendar"
        elif not os.path.exists(os.path.join(BASE_DIR, fest["poster_file"])):
            item["status"] = f"skipped - poster file not found: {fest['poster_file']}"
        else:
            recipients, invalid, excluded = build_recipients(load_contacts(), fest.get("exclude_religions", ""))
            item.update({"recipients": len(recipients), "excluded_by_religion": excluded,
                         "invalid_numbers": invalid})
            with _state_lock:
                already = run_key in _state["done"]
                busy = run_key in _running
                if already:
                    item["status"] = "already sent today - not sending again"
                elif busy:
                    item["status"] = "already running"
                elif dry_run:
                    item["status"] = "DRY RUN - would send now (nothing was sent)"
                elif not recipients:
                    item["status"] = "skipped - no valid contacts"
                else:
                    _running.add(run_key)
                    threading.Thread(target=run_festival, args=(fest, recipients, run_key), daemon=True).start()
                    item["status"] = "started - sending in background"
        log(f"{item['festival']}: {item['status']}")
        report.append(item)
    return report


def _authorized() -> bool:
    key = request.args.get("key", "")
    return bool(FESTIVAL_RUN_KEY) and hmac.compare_digest(key, FESTIVAL_RUN_KEY)


@app.route("/run-festival-check", methods=["GET", "POST"])
def run_festival_check():
    """Called every morning by the outside timer. Add &dry=1 to only see what would
    be sent (you may add &date=2026-10-11 together with dry=1 to test another day)."""
    if not FESTIVAL_RUN_KEY:
        return jsonify({"error": "FESTIVAL_RUN_KEY is not set on the server"}), 503
    if not _authorized():
        return jsonify({"error": "wrong key"}), 403
    dry = request.args.get("dry") == "1"
    on_date = today_ist()
    if dry and request.args.get("date"):
        try:
            on_date = date.fromisoformat(request.args["date"])
        except ValueError:
            return jsonify({"error": "date must look like 2026-10-11"}), 400
    report = check_festivals(on_date, dry)
    return jsonify({"checked_date_ist": on_date.isoformat(), "dry_run": dry,
                    "festivals_today": report or "no festival today"}), 200


@app.route("/send-test", methods=["GET"])
def send_test():
    """Send one festival's poster to ONE number (e.g. your own) to see exactly how it looks.
    /send-test?key=...&template=navratri_greeting&to=9876543210"""
    if not FESTIVAL_RUN_KEY:
        return jsonify({"error": "FESTIVAL_RUN_KEY is not set on the server"}), 503
    if not _authorized():
        return jsonify({"error": "wrong key"}), 403
    template = request.args.get("template", "")
    number = normalize_number(request.args.get("to"))
    fest = next((r for r in load_calendar() if r.get("template_name") == template), None)
    if not fest or not number:
        return jsonify({"error": "unknown template, or 'to' is not a valid Indian number"}), 400
    try:
        media_id = upload_poster(fest["poster_file"])
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    ok, result = send_template_with_image(number, template, media_id)
    return jsonify({"sent": ok, "to": number, "response": result}), (200 if ok else 502)


@app.route("/festival-log", methods=["GET"])
def festival_log():
    """Shows what the automatic sender did recently (who failed and why)."""
    if not _authorized():
        return jsonify({"error": "wrong key"}), 403
    with _state_lock:
        return jsonify({"running": sorted(_running), "done": _state["done"], "runs": _state["runs"]}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
