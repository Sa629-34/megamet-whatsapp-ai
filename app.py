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
    "same to you", "happy anant", "happy chaturdashi", "shubhkamna",
    "welcome", "🙏", "👍", "❤️", "nice", "good",
]

PRICE_KEYWORDS = [
    "price", "rate", "cost", "quote", "kitna", "kimat", "keemat",
    "negotiat", "discount",
]

BUSINESS_KEYWORDS = [
    "wood", "timber", "lakdi", "pine", "kd wood", "kiln", "supply",
    "furniture", "packaging", "construction", "import", "delivery",
    "quantity", "order", "product", "sample", "moq",
]

GREETING_REPLY = (
    "Dhanyavaad! Aapko bhi Anant Chaturdashi ki shubhkamnayein 🙏 "
    "- Megamet India"
)

PRICE_REPLY = (
    "Dhanyavaad interest ke liye! Pricing/quote ki exact detail hamari "
    "sales team aapko confirm karke degi. Kripya apna naam, requirement "
    "(quantity/product) aur city share karein, hum jald contact karenge."
)

BUSINESS_REPLY = (
    "Namaste! Megamet India Pvt Ltd - hum Europe aur Baltic countries se "
    "KD (kiln-dried) pine wood import karke India mein deliver karte hain. "
    "Aapko kya requirement hai (product/quantity/location)? Hamari sales "
    "team aapse jald contact karke detail share karegi."
)

DEFAULT_REPLY = (
    "Namaste! Ye Megamet India ka WhatsApp hai - hum timber (pine wood) "
    "import aur supply karte hain. Aap apna requirement ya sawal bata "
    "sakte hain, hamari team jald reply karegi."
)


def get_faq_reply(user_message: str) -> str:
    """Simple keyword-matching FAQ bot - no paid AI, free to run."""
    text = user_message.lower()

    if any(word in text for word in PRICE_KEYWORDS):
        return PRICE_REPLY
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
