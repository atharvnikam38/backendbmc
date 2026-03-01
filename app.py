from fastapi import FastAPI, Request
import requests
import os
import random
import io
import json
import cloudinary
import cloudinary.uploader
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ==========================================
# 🛑 CONFIGURATION & DATABASE
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8765381376:AAEtOvPxWRzWRBWLfs64knR-LYZ48MQqf_s")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

print(f"🛠️ DEBUG: Loaded Bot Token starts with: {TELEGRAM_BOT_TOKEN[:10]}...")

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True
)

mongo_client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/"))
db = mongo_client["bmc_portal"]
complaints_collection = db["complaints"]

COMPLAINTS_DIR = "bmc_complaints"
os.makedirs(COMPLAINTS_DIR, exist_ok=True)

user_sessions = {}

# ==========================================
# 🔧 HELPER FUNCTIONS
# ==========================================

def get_session(chat_id):
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {
            "current_flow": None,  
            "awaiting_confirmation": False, 
            "case_id": None,
            "media_url": None,
            "media_public_id": None,
            "media_type": None,
            "media_ext": None,
            "description": None,
            "voice_url": None,
            "lat": None,
            "lon": None,
            "pincode": None,
            "phone": None
        }
    return user_sessions[chat_id]

def generate_case_id():
    return f"BMC-{random.randint(10000, 99999)}"

def send_message(chat_id, text, request_contact=False):
    print(f"\n📩 DEBUG: Attempting to send message to {chat_id}...")
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    
    if request_contact:
        payload["reply_markup"] = {
            "keyboard": [[{"text": "Share My Phone Number 📞", "request_contact": True}]],
            "one_time_keyboard": True,
            "resize_keyboard": True
        }
    else:
        payload["reply_markup"] = {"remove_keyboard": True}
        
    try:
        res = requests.post(url, json=payload, timeout=5)
        if not res.ok:
            print(f"❌ TELEGRAM API ERROR (send_message): {res.status_code} - {res.text}")
            print(f"❌ Failed Text payload was: {text}")
        else:
            print(f"✅ Message sent successfully to {chat_id}!")
    except Exception as e:
        print(f"❌ REQUEST CRASH (send_message): {e}")

def send_inline_keyboard(chat_id, text, buttons):
    print(f"\n📩 DEBUG: Attempting to send inline keyboard to {chat_id}...")
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": buttons}
    }
    
    try:
        res = requests.post(url, json=payload, timeout=5)
        if not res.ok:
            print(f"❌ TELEGRAM API ERROR (send_inline_keyboard): {res.status_code} - {res.text}")
        else:
            print(f"✅ Keyboard sent successfully to {chat_id}!")
    except Exception as e:
        print(f"❌ REQUEST CRASH (send_inline_keyboard): {e}")

def get_pincode(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
        headers = {"User-Agent": "BMC_Sahayak_Bot"}
        res = requests.get(url, headers=headers).json()
        return res.get("address", {}).get("postcode", "Unknown")
    except:
        return "Unknown"

LOCATION_INSTRUCTION = (
    "📍 **Step 1: Send Location**\n\n"
    "Please drop a pin on the exact spot of the issue:\n"
    "1. Click the Paperclip (📎) icon.\n"
    "2. Select **Location**.\n"
    "3. Drag the map to **Drop a Pin** on the exact spot.\n"
    "4. Click **'Send this location'**."
)

def fetch_and_send_status(chat_id, phone):
    # THE FIX: sort by 1 so Oldest is at the top, Newest is at the bottom
    user_cases = list(complaints_collection.find({"phone": phone}).sort("_id", 1))
    
    if not user_cases:
        send_message(chat_id, "📭 **No records found.**\nYou haven't registered any complaints yet! Type /start to report a new issue.")
        return

    buttons = []
    for case in user_cases:
        cat = case.get("category", "Civic Issue")
        cid = case.get("case_id")
        short_cat = cat[:15] + "..." if len(cat) > 15 else cat
        buttons.append([{"text": f"🚧 {short_cat} ({cid})", "callback_data": f"status_{cid}"}])

    send_inline_keyboard(
        chat_id,
        "🔍 **Your Registered Complaints**\n*(Oldest at the top, Newest at the bottom)*\n\nClick an issue below to check its live AI-processed status:",
        buttons
    )

# ==========================================
# ☁️ CLOUDINARY UPLOAD & LOCAL SAVE
# ==========================================
def upload_to_cloudinary_and_save(file_id: str, resource_type: str, case_id: str, filename: str, ext: str):
    try:
        res = requests.get(
            f"{TELEGRAM_API_URL}/getFile",
            params={"file_id": file_id},
            timeout=10
        ).json()

        if not res.get("ok"):
            print(f"[Cloudinary] ❌ Telegram getFile failed: {res}")
            return None

        file_path = res["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"

        print(f"[Cloudinary] ⬇️  Downloading from Telegram: .../{file_path.split('/')[-1]}")
        telegram_response = requests.get(download_url, timeout=30)
        telegram_response.raise_for_status()
        file_bytes = telegram_response.content
        print(f"[Cloudinary] ✅ Downloaded {len(file_bytes) / 1024:.1f} KB")

        local_folder = os.path.join(COMPLAINTS_DIR, case_id)
        os.makedirs(local_folder, exist_ok=True)
        local_filepath = os.path.join(local_folder, f"{filename}.{ext}")
        with open(local_filepath, "wb") as f:
            f.write(file_bytes)
        print(f"📁 ✅ Saved locally to {local_filepath}")

        public_id = f"bmc_complaints/{case_id}/{filename}"
        print(f"[Cloudinary] ⬆️  Uploading to Cloudinary as '{public_id}' (type={resource_type})...")

        upload_result = cloudinary.uploader.upload(
            io.BytesIO(file_bytes),
            resource_type=resource_type,
            public_id=public_id,
            overwrite=True,
            tags=[case_id, "bmc_complaint"],
            context=f"case_id={case_id}"
        )

        secure_url = upload_result["secure_url"]
        print(f"[Cloudinary] ✅ Upload success: {secure_url}")

        return {
            "url": secure_url,
            "public_id": upload_result["public_id"],
            "format": upload_result.get("format"),
            "resource_type": resource_type
        }

    except Exception as e:
        print(f"❌ Error downloading/uploading media: {e}")
        return None

# ==========================================
# 📦 FINAL SUBMIT FUNCTION
# ==========================================
def submit_complaint(chat_id):
    session = get_session(chat_id)
    case_id = session["case_id"]

    metadata = {
        "case_id": case_id,
        "phone": session["phone"],
        "pincode": session["pincode"],
        "lat": session["lat"],
        "lon": session["lon"],
        "status": "Registered",
        "evidence_type": session["media_ext"],
        "desc_type": "voice" if session["voice_url"] else "text",
        "evidence": {
            "url": session["media_url"],
            "public_id": session["media_public_id"],
            "type": session["media_type"],
        },
        "description": {
            "type": "voice" if session["voice_url"] else "text",
            "text": session["description"] if not session["voice_url"] else None,
            "voice_url": session["voice_url"],
        }
    }

    local_folder = os.path.join(COMPLAINTS_DIR, case_id)
    os.makedirs(local_folder, exist_ok=True)
    
    if session.get("description") and not session.get("voice_url"):
        with open(os.path.join(local_folder, "statement.txt"), "w", encoding="utf-8") as f:
            f.write(session["description"])
            
    with open(os.path.join(local_folder, "details.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)
    print(f"📄 ✅ Saved details.json locally to trigger AI worker.")

    complaints_collection.update_one(
        {"case_id": case_id},
        {"$set": metadata},
        upsert=True
    )
    
    del user_sessions[chat_id]

    send_message(
        chat_id,
        f"✅ **Complaint Successfully Registered!**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎟️ **Case ID:** `{case_id}`\n"
        f"📍 **Pin Code:** {session['pincode']}\n\n"
        f"Your evidence has been securely uploaded to the cloud and our AI workers are currently analyzing your issue. ⚙️\n\n"
        f"👉 Type /status at any time to track live updates."
    )

# ==========================================
# 🌐 WEBHOOK HANDLER
# ==========================================
@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
        
        # ------------------------------------------
        # 👆 INLINE BUTTON CLICKS (Callbacks)
        # ------------------------------------------
        if "callback_query" in update:
            cb = update["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            data = cb["data"]
            session = get_session(chat_id)

            if data == "confirm_submit":
                if session.get("awaiting_confirmation"):
                    submit_complaint(chat_id)
                else:
                    send_message(chat_id, "⚠️ This draft has already been processed or expired.")
            
            elif data == "confirm_cancel":
                if session.get("awaiting_confirmation"):
                    phone = session.get("phone")
                    user_sessions[chat_id] = {
                        "current_flow": None,  
                        "awaiting_confirmation": False, 
                        "case_id": None, "media_url": None, "media_public_id": None,
                        "media_type": None, "media_ext": None, "description": None,
                        "voice_url": None, "lat": None, "lon": None, "pincode": None,
                        "phone": phone
                    }
                    send_message(chat_id, "🚫 **Complaint Cancelled.**\n\nNothing was sent to the BMC. Type /start when you are ready to report a new issue.")
                else:
                    send_message(chat_id, "⚠️ This draft has already been processed or expired.")

            elif data.startswith("status_"):
                case_id = data.split("_")[1]
                
                # Grabs the absolute newest document for this case ID so the LangGraph AI details show
                case = complaints_collection.find_one(
                    {"case_id": case_id},
                    sort=[("_id", -1)] 
                )

                if case:
                    category = case.get('category', 'Analyzing...')
                    ward = case.get('ward', 'Pending Mapping')
                    trust_score = case.get('trust_score', 50)
                    status = case.get('status', 'Pending Verification')
                    problem_summary = case.get('problem_summary', 'AI is currently processing your audio/text. Please check back shortly.')
                    urgency = case.get('urgency', 'Normal')
                    
                    media_link = case.get('evidence_url', '#')
                        
                    msg_text = (
                        f"📋 **Live Status for {case_id}**\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🚨 **Category:** {category}\n"
                        f"🏢 **Ward:** {ward}\n"
                        f"⚡ **Urgency:** {urgency}\n"
                        f"📊 **Trust Score:** {trust_score}%\n\n"
                        f"✅ **Current Status:** `{status}`\n\n"
                        f"📝 **Problem Summary:** {problem_summary}\n\n"
                        f"🖼️ **Evidence:** [Click here to View Media]({media_link})"
                    )
                    send_message(chat_id, msg_text)
                else:
                    send_message(chat_id, "⚠️ Case not found or our AI is currently processing it. Please try again in a minute.")

            requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb["id"]})
            return {"status": "ok"}

        # ------------------------------------------
        # 💬 TEXT & MEDIA HANDLING
        # ------------------------------------------
        if "message" not in update:
            return {"status": "ok"}

        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        session = get_session(chat_id)

        if session.get("awaiting_confirmation") and text not in ["/start", "/status"]:
            send_message(chat_id, "⚠️ **Please use the buttons above** to either Submit or Cancel your current draft before typing anything else.")
            return {"status": "ok"}

        if text in ["/start", "/newrequest"]:
            phone = session.get("phone")
            user_sessions[chat_id] = {
                "current_flow": "start",  
                "awaiting_confirmation": False, 
                "case_id": None, "media_url": None, "media_public_id": None,
                "media_type": None, "media_ext": None, "description": None,
                "voice_url": None, "lat": None, "lon": None, "pincode": None,
                "phone": phone
            }
            
            if not phone:
                send_message(chat_id, "Namaste! 🙏 Welcome to BMC Sahayak.\n\nTo register a new complaint, please **Share My Phone Number** using the button below.", request_contact=True)
            else:
                send_message(chat_id, f"Welcome back! Let's register a new complaint.\n\n{LOCATION_INSTRUCTION}")
            return {"status": "ok"}

        if text == "/status":
            session["current_flow"] = "status"
            if not session["phone"]:
                send_message(chat_id, "Namaste! 🙏 \n\nTo check your complaint history, please securely **Share My Phone Number** using the button below.", request_contact=True)
            else:
                fetch_and_send_status(chat_id, session["phone"])
            return {"status": "ok"}

        if "contact" in msg:
            session["phone"] = msg["contact"]["phone_number"]
            if session["current_flow"] == "status":
                send_message(chat_id, "Phone verified! ✅ Fetching your secure records...")
                fetch_and_send_status(chat_id, session["phone"])
            else:
                session["current_flow"] = "start"
                send_message(chat_id, f"Phone verified! ✅ Let's get started.\n\n{LOCATION_INSTRUCTION}")
            return {"status": "ok"}

        if not session["phone"]:
            welcome_msg = (
                "Namaste! 🙏 Welcome to the **BMC Sahayak Bot**.\n"
                "I am an AI assistant here to help resolve your civic issues.\n\n"
                "Please choose an option to proceed:\n"
                "📢 **Register a new issue:** Type /start\n"
                "🔍 **Check existing issues:** Type /status"
            )
            send_message(chat_id, welcome_msg)
            return {"status": "ok"}

        if "location" in msg:
            session["current_flow"] = "start" 
            session["lat"] = msg["location"]["latitude"]
            session["lon"] = msg["location"]["longitude"]
            session["pincode"] = get_pincode(session["lat"], session["lon"])
            send_message(
                chat_id,
                f"📍 Location Captured! (Pincode: **{session['pincode']}**)\n\n"
                f"📸 **Step 2:** Please send a clear **Photo or Video** of the issue."
            )
            return {"status": "ok"}

        if ("photo" in msg or "video" in msg) and not session["lat"]:
            send_message(chat_id, f"⚠️ **Wait!** I need to know where this is before accepting photos.\n\n{LOCATION_INSTRUCTION}")
            return {"status": "ok"}

        if "photo" in msg or "video" in msg:
            send_message(chat_id, "⏳ Uploading your media to our secure cloud. Please wait...")

            if "photo" in msg:
                file_id = msg["photo"][-1]["file_id"]
                resource_type = "image"
                ext = "jpg"
            else:
                file_id = msg["video"]["file_id"]
                resource_type = "video"
                ext = "mp4"

            if not session["case_id"]:
                session["case_id"] = generate_case_id()

            case_id = session["case_id"]

            result = upload_to_cloudinary_and_save(file_id, resource_type, case_id, "evidence", ext)

            if result:
                session["media_url"] = result["url"]
                session["media_public_id"] = result["public_id"]
                session["media_type"] = resource_type
                session["media_ext"] = ext
                send_message(chat_id, "📸 Media uploaded successfully! ✅\n\n🎤 **Final Step:** Send a **Voice Note** explaining the issue, or type a **Text Description**.")
            else:
                send_message(chat_id, "❌ Media upload failed. Please try sending the photo or video again.")

            return {"status": "ok"}

        if "voice" in msg or (text and session.get("media_url")):
            
            if not session["media_url"]:
                send_message(chat_id, "⚠️ Please send a **Photo or Video** first so our AI can visually analyze the issue!")
                return {"status": "ok"}

            if "voice" in msg:
                send_message(chat_id, "⏳ Processing your voice statement...")
                case_id = session["case_id"]

                result = upload_to_cloudinary_and_save(
                    file_id=msg["voice"]["file_id"],
                    resource_type="raw",
                    case_id=case_id,
                    filename="statement",
                    ext="ogg"
                )

                if result:
                    session["voice_url"] = result["url"]
                else:
                    send_message(chat_id, "❌ Voice upload failed. Please try sending your voice note again.")
                    return {"status": "ok"}
            else:
                session["description"] = text

            session["awaiting_confirmation"] = True
            
            draft_msg = (
                "📄 **COMPLAINT DRAFT PREVIEW**\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "This is exactly what the BMC officer and AI will see:\n\n"
                f"📞 **Citizen Phone:** `{session['phone']}`\n"
                f"📍 **Pincode:** `{session['pincode']}`\n"
                f"📸 **Evidence:** [Click to View]({session['media_url']})\n"
            )
            
            if session.get("voice_url"):
                draft_msg += f"🎤 **Statement:** [Click to Listen]({session['voice_url']})\n\n"
            else:
                draft_msg += f"📝 **Statement:** {session['description']}\n\n"
                
            draft_msg += "❓ **Are you sure you want to submit this to the BMC?**"

            buttons = [
                [{"text": "✅ Yes, Submit to BMC", "callback_data": "confirm_submit"}],
                [{"text": "❌ Cancel Request", "callback_data": "confirm_cancel"}]
            ]
            send_inline_keyboard(chat_id, draft_msg, buttons)
            return {"status": "ok"}

        if text and not session.get("media_url"):
            menu_msg = (
                "Namaste! 🙏 How can I assist you today?\n\n"
                "📢 **Register a Complaint:** Type /start\n"
                "🔍 **Check Status:** Type /status\n\n"
                "*(If you are trying to submit an issue, please type /start to begin the guided process)*"
            )
            send_message(chat_id, menu_msg)

        return {"status": "ok"}

    except Exception as e:
        import traceback
        print(f"🔥 FATAL WEBHOOK ERROR: {e}")
        traceback.print_exc()  
        return {"status": "error"}

@app.get("/complaint/{case_id}/media")
async def get_complaint_media(case_id: str):
    case = complaints_collection.find_one({"case_id": case_id}, {"_id": 0})
    if not case:
        return {"error": "Case not found"}
    return {
        "case_id": case_id,
        "status": case.get("status"),
        "evidence": case.get("evidence"),
        "description": case.get("description"),
        "location": {
            "lat": case.get("lat"),
            "lon": case.get("lon"),
            "pincode": case.get("pincode")
        }
    }