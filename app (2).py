"""
Megamet India - WhatsApp AI Agent
-----------------------------------
Yeh app WhatsApp Business number pe aane wale customer messages ko
automatically padhta hai, Claude AI se jawab generate karwata hai
(company ki jaankari ke hisaab se), aur customer ko wapas reply bhejta hai.

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
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# =========================================================
# MARKETING AI - scope: sirf poster/campaign ke baad aane wale
# customer replies ko engage karna. Sales negotiation, price
# finalize karna iska kaam NAHI hai - wo "Sales Team AI" (alag se
# banega) karega. Marketing AI sirf interest capture aur
# warm-up karta hai, phir sales ko handover ka sanket deta hai.
# =========================================================

BUSINESS_CONTEXT = """
Tum Megamet India ke WhatsApp MARKETING assistant ho - tumhara kaam
sirf naye leads ko engage karna hai, sales close karna nahi.

Company:
- Megamet India Pvt Ltd - Europe aur Baltic countries se KD (kiln-dried)
  pine wood import aur distribute karti hai India mein.
- [Yahan aur details daalo: konsi timber grades, kaunse sheher/regions
  mein supply hoti hai, company ki USP, etc.]

Tumhara scope (Marketing AI):
- Customer ne poster/ad dekh ke reply kiya hai - use warmly welcome karo,
  thodi si basic jaankari do product ke baare mein.
- Uska interest samjho: konsa product chahiye, kitni quantity, kaha deliver
  karwana hai - ye basic details friendly tarike se pucho.
- KABHI bhi exact price quote MAT karo, negotiation mat karo.
- Jab lead "warm" lage (genuinely interested, details de raha ho), toh
  bolo: "Hamari sales team aapse jald contact karegi detailed quote ke
  saath" - aur baat ko wahi close karo.
- Agar customer directly price/negotiation pe chala jaye, politely bolo
  ki sales team exact pricing discuss karegi.

Rules:
- Hamesha polite, friendly tone (Hindi/English mix, jaisa customer likhe).
- Chhote, clear jawab do - WhatsApp message jaisa, lamba essay nahi.
- Kabhi galat/banayi hui information mat do - pata na ho toh saaf bolo
  team confirm karke batayegi.
"""

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
            reply_text = get_ai_reply(user_text)

        send_whatsapp_message(from_number, reply_text)

    except (KeyError, IndexError) as e:
        print("Parse error (probably a status update, ignoring):", e)

    return "OK", 200


# =========================================================
# AI REPLY - Claude API se jawab generate karwana
# =========================================================

def get_ai_reply(user_message: str) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 300,
        "system": BUSINESS_CONTEXT,
        "messages": [{"role": "user", "content": user_message}],
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()
    return result["content"][0]["text"]


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
    return "Megamet WhatsApp AI agent is running.", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
