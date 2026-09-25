"""
Megamet India - WhatsApp FAQ Bot (Marketing)
-----------------------------------
This app automatically reads incoming customer messages on the WhatsApp
Business number, and replies using FIXED (keyword-based) rules. This is
NOT "real AI" (paid) - it is free, no Anthropic/OpenAI API needed.

This app should run 24/7, so it needs to be deployed on Render.com (or
any cloud hosting) - not on your own computer.

SETUP:
1. Set your values in the "CONFIG" section below (or better, set them as
   environment variables in Render's "Environment" tab).
2. Packages listed in requirements.txt will be installed automatically
   on Render.
3. Once deployed, take the URL you get (e.g. https://megamet-ai.onrender.com),
   add "/webhook" at the end, and put it as the Callback URL in the Meta
   App Dashboard.
"""

import os
import json
import requests
from flask import Flask, request

app = Flask(__name__)

# =========================================================
# CONFIG - set these values in Render's "Environment Variables"
# =========================================================

WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "1427617750424162")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "megamet_verify_123")  # this must match the Meta dashboard

# =========================================================
# FAQ REPLIES - fixed, hardcoded answers. No AI/paid API used.
# To add a new question/keyword, add it to the lists below.
# =========================================================

GREETING_KEYWORDS = [
    "thank", "thanks", "thankyou", "dhanyavaad", "dhanyawad",
    "same to you", "happy anant", "happy chaturdashi", "happy ganesh",
    "ganpati", "shubhkamna", "welcome", "🙏", "👍", "❤️", "nice", "good",
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
    "Email: mail@megamet.in\n"
    "Website: www.megamet.in"
)

CONTACT_REPLY = (
    "Sure! Here are our contact details:" + CONTACT_INFO
)

GREETING_REPLY = (
    "Thank you! Wishing you a very Happy Ganesh Chaturthi / Anant "
    "Chaturdashi too 🙏 - Team Megamet India" + CONTACT_INFO
)

PRICE_REPLY = (
    "Thanks for your interest! Exact pricing/quotes are shared by our "
    "sales team based on your requirement. Please share your name, "
    "product & quantity needed, and your city - our team will contact "
    "you shortly."
)

DELIVERY_REPLY = (
    "We deliver our timber (KD pine wood) to various locations across "
    "India. Please share your city/state and requirement - our sales "
    "team will confirm delivery details and timelines."
)

SAMPLE_MOQ_REPLY = (
    "Thanks for asking! Sample availability and minimum order quantity "
    "details are confirmed by our sales team based on the product. "
    "Please share your requirement and city, and our team will get back "
    "to you."
)

ABOUT_REPLY = (
    "Megamet India Pvt Ltd is the largest importer and distributor of KD "
    "(kiln-dried) pine wood from Europe, Russia and the Baltic countries, "
    "supplying across India for sustainable timber, packaging, "
    "furniture manufacturing and construction needs."
)

BUSINESS_REPLY = (
    "Hello! Megamet India Pvt Ltd imports KD (kiln-dried) pine wood from "
    "Europe and the Baltic countries and delivers it across India. "
    "Could you share your requirement (product/quantity/location)? Our "
    "sales team will reach out to you shortly with details."
)

DEFAULT_REPLY = (
    "Hello! This is Megamet India's WhatsApp - we import and supply "
    "timber (pine wood) across India. Please share your requirement or "
    "question, and our team will get back to you shortly."
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
