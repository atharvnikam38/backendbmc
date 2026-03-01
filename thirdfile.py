import os
import json
import time
import math
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

import cloudinary
import cloudinary.uploader
import cloudinary.api

# 1. Force load the .env file and print the result immediately
print("==========================================")
print("🛠️ DEBUG: Loading Environment Variables...")
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
print(f"🛠️ DEBUG: Looking for .env file at: {os.path.abspath('.env')}")
load_dotenv()

# Check if keys are actually loaded in this file
cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
api_key = os.environ.get("CLOUDINARY_API_KEY")
print(f"🛠️ DEBUG: CLOUDINARY_CLOUD_NAME = {cloud_name}")
print(f"🛠️ DEBUG: CLOUDINARY_API_KEY = {api_key}")
print("==========================================\n")

# ==========================================
# 🛑 CONFIGURATION
# ==========================================
DB_NAME = "bmc_portal"
COLLECTION_NAME = "complaints"
WARDS_COLLECTION_NAME = "mumbai_wards" 
COMPLAINTS_DIR = "bmc_complaints"

# --- CLOUDINARY SETUP ---
cloudinary.config( 
  cloud_name = cloud_name, 
  api_key = api_key, 
  api_secret = os.environ.get("CLOUDINARY_API_SECRET") 
)

# ==========================================
# 📤 HELPER: UPLOAD TO CLOUDINARY
# ==========================================
def upload_to_cloudinary(file_path, case_id):
    """Uploads file to Cloudinary and returns a permanent public URL."""
    print(f"\n   [UPLOAD DEBUG] Triggered for Case: {case_id}")
    print(f"   [UPLOAD DEBUG] Relative Path Given: {file_path}")
    
    # Let's check the absolute path to ensure Python is looking in the right folder
    abs_path = os.path.abspath(file_path)
    print(f"   [UPLOAD DEBUG] Absolute Path Checked: {abs_path}")
    
    if not os.path.exists(abs_path):
        print(f"   ❌ [UPLOAD ERROR] FILE DOES NOT EXIST at {abs_path}! Skipping upload.")
        return None

    # Let's check if the file is empty
    file_size = os.path.getsize(abs_path)
    print(f"   [UPLOAD DEBUG] File found! Size: {file_size} bytes.")
    
    if file_size == 0:
        print("   ❌ [UPLOAD ERROR] File is 0 bytes (Empty). Cloudinary will reject this.")
        return None

    try:
        print(f"   ☁️ Uploading {os.path.basename(abs_path)} to Cloudinary...")
        response = cloudinary.uploader.upload(
            abs_path, 
            resource_type="auto",
            folder=f"bmc_complaints/{case_id}"
        )
        secure_url = response.get("secure_url")
        print(f"   ✅ [UPLOAD SUCCESS] Link generated: {secure_url}")
        return secure_url
        
    except Exception as e:
        print(f"   ❌ [UPLOAD CRASH] Cloudinary threw an exception: {e}")
        return None


def get_distance(lat1, lon1, lat2, lon2):
    R = 6371000  
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def start_mongo_watcher():
    print("👀 [MONGO WORKER] Connected to DB. Watching for resolved cases...")
    client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/"))
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    wards_collection = db[WARDS_COLLECTION_NAME]
    
    while True:
        if not os.path.exists(COMPLAINTS_DIR):
            time.sleep(5)
            continue
            
        for case_id in os.listdir(COMPLAINTS_DIR):
            case_folder = os.path.join(COMPLAINTS_DIR, case_id)
            json_path = os.path.join(case_folder, "details.json")
            
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                except Exception as e:
                    print(f"Error reading {case_id}: {e}")
                    continue
                    
                if metadata.get("status") == "Resolved by AI":
                    print(f"\n🚀 Processing {case_id}...")
                    
                    # DEBUG: Let's see what extensions the JSON actually has saved
                    ext = metadata.get("evidence_type", "jpg")
                    desc_ext = "ogg" if metadata.get("desc_type") == "voice" else "txt"
                    
                    print(f"   [JSON DEBUG] Extracted Image Ext: {ext}")
                    print(f"   [JSON DEBUG] Extracted Audio/Text Ext: {desc_ext}")
                    
                    lat = float(metadata.get("lat", metadata.get("gps", {}).get("lat", 0.0)))
                    lon = float(metadata.get("lon", metadata.get("gps", {}).get("lon", 0.0)))
                    phone = metadata.get("phone", metadata.get("citizen_phone", ""))
                    pincode = metadata.get("pincode", "")

                    ai_analysis = metadata.get("ai_analysis", {})
                    problem_summary = ai_analysis.get("problem_summary") or metadata.get("problem_summary", "Summary unavailable")
                    category = ai_analysis.get("category") or metadata.get("category", "General Administration")
                    urgency = ai_analysis.get("urgency") or metadata.get("urgency", "Medium")

                    clean_pincode = str(pincode).strip().replace(" ", "")
                    ward_name = "Unknown Ward"
                    if pincode:
                        ward_data = wards_collection.find_one({"pincodes": clean_pincode})
                        if ward_data:
                            ward_name = ward_data.get("ward", "Unknown Ward")
                    
                    # ==========================================
                    # ☁️ UPLOAD FILES TO CLOUDINARY
                    # ==========================================
                    local_evidence_path = os.path.join(case_folder, f"evidence.{ext}")
                    local_statement_path = os.path.join(case_folder, f"statement.{desc_ext}")
                    
                    print(f"\n--- Initiating Uploads for {case_id} ---")
                    cloud_evidence_link = upload_to_cloudinary(local_evidence_path, case_id)
                    cloud_statement_link = upload_to_cloudinary(local_statement_path, case_id)
                    print("------------------------------------------\n")

                    mongo_document = {
                        "case_id": metadata.get("case_id"),
                        "phone": phone,
                        "pincode": pincode,
                        "ward": ward_name, 
                        "lat": lat,
                        "lon": lon,
                        "desc_type": metadata.get("desc_type"),
                        "status": "Pending Assignment", 
                        "trust_score": 50,              
                        
                        "problem_summary": problem_summary,
                        "category": category,
                        "urgency": urgency,
                        
                        "evidence_url": cloud_evidence_link or f"{COMPLAINTS_DIR}/{case_id}/evidence.{ext}",
                        "statement_url": cloud_statement_link or f"{COMPLAINTS_DIR}/{case_id}/statement.{desc_ext}",
                        
                        "transcript": metadata.get("transcript", ""),
                        "createdAt": datetime.utcnow()
                    }
                    
                    try:
                        collection.insert_one(mongo_document)
                        print(f"✅ Successfully inserted {case_id} into MongoDB!")
                        
                        metadata["status"] = "Saved to DB"
                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump(metadata, f, indent=4, ensure_ascii=False)
                            
                    except Exception as e:
                        print(f"❌ Failed to insert/process {case_id}: {e}")
                        
        time.sleep(3)

if __name__ == "__main__":
    start_mongo_watcher()