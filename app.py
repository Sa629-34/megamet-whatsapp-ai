"""
Megamet India - WhatsApp FAQ Bot (Marketing)
-----------------------------------
Yeh app WhatsApp Business number pe aane wale customer messages ko
automatically padhta hai, aur FIXED (keyword-based) rules ke hisaab se
jawab bhejta hai. Ye "real AI" (paid) nahi hai - ye free hai, kisi
Anthropic/OpenAI API ki zaroorat nahi.

Yeh app hamesha (24/7) chalna chahiye, isliye ise Render.com (ya kisi bhi
cloud hosting) pe deploy karna hai - apne computer pe nahi.

SETUP:
1. Neeche "CONFIG" section mein apni values daalo (ya better, environment
   variables se set karo - Render pe "Environment" tab mein).
2. requirements.txt mein diye packages install honge automatically Render pe.
3. Deploy hone ke baad jo URL milega (jaise https://megamet-ai.onrender.com),
   uske aage "/webhook" laga ke Meta App Dashboard mein Callback URL mein daal do.
"""

import os
import json
import requests
from flask import Flask, request

app = Flask(__name__)

# =========================================================
# CONFIG - yeh values Render ke "Environment Variables" mein set karo
# =========================================================

WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "1427617750424162")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "megamet_verify_123")  # Meta dashboard mein yehi daalna hoga

# =========================================================
# FAQ REPLIES - fixed, hardcoded jawab. Koi AI/paid API nahi lagta.
# Naya sawal/keyword add karna ho toh RULES list mein neeche add karo.
# =========================================================

GREETING_KEYWORDS = [
    "thank", "thanks", "thankyou", "dhanyavaad", "dhanyawad",
    "same to you", "happy anant", "happy chaturdashi", "happy ganesh",
    "ganpati", "shubhkamna", "welcome", "🙏", "👍", "❤️", "nice", "good",
]

PRICE_KEYWORDS = [
    "price", "rate", "cost", "quote", "quotation", "kitna", "kimat",
    "keemat", "negotiat", "discount", "budget",
]

DELIVERY_KEYWORDS = [
    "deliver", "delivery", "location", "city", "state", "where",
    "shipping", "transport", "reach", "area", "pincode",
]

SAMPLE_MOQ_KEYWORDS = [
    "sample", "moq", "minimum order", "minimum quantity", "trial",
]

ABOUT_KEYWORDS = [
    "who are you", "what is this", "about", "company", "kya hai",
    "kaun ho", "what do you do", "megamet",
]

BUSINESS_KEYWORDS = [
    "wood", "timber", "lakdi", "pine", "kd wood", "kiln", "supply",
    "furniture", "packaging", "construction", "import", "quantity",
    "order", "product", "requirement", "need",
]

GREETING_REPLY = (
    "Thank you! Wishing you a very Happy Ganesh Chaturthi / Anant "
    "Chaturdashi too 🙏 - Team Megamet India"
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
    "Megamet India Pvt Ltd is an importer and distributor of KD "
    "(kiln-dried) pine wood from Europe and the Baltic countries, "
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
# WEBHOOK VERIFICATION (Meta ek baar GET request bhejta hai setup ke time)
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
# INCOMING MESSAGES (Meta yahan customer ka message POST karta hai)
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
            # Ye status update hai (delivered/read), message nahi - ignore karo
            return "OK", 200

        message = value["messages"][0]
        from_number = message["from"]
        msg_type = message.get("type")

        if msg_type != "text":
            reply_text = "Abhi hum sirf text messages samajh paate hain. Kripya apna sawal likh kar bhejein."
        else:
            user_text = message["text"]["body"]
            reply_text = get_faq_reply(user_text)

        send_whatsapp_message(from_number, reply_text)

    except (KeyError, IndexError) as e:
        print("Parse error (probably a status update, ignoring):", e)

    return "OK", 200


# =========================================================
# WHATSAPP KO REPLY BHEJNA
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
