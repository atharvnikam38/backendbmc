# import os
# import json
# import time
# import math
# from datetime import datetime, timedelta
# from pymongo import MongoClient
# from dotenv import load_dotenv

# import cloudinary
# import cloudinary.uploader
# import cloudinary.api

# # 1. Force load the .env file and print the result immediately
# print("==========================================")
# print("🛠️ DEBUG: Loading Environment Variables...")
# dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
# print(f"🛠️ DEBUG: Looking for .env file at: {os.path.abspath('.env')}")
# load_dotenv()

# # Check if keys are actually loaded in this file
# cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
# api_key = os.environ.get("CLOUDINARY_API_KEY")
# print(f"🛠️ DEBUG: CLOUDINARY_CLOUD_NAME = {cloud_name}")
# print(f"🛠️ DEBUG: CLOUDINARY_API_KEY = {api_key}")
# print("==========================================\n")

# # ==========================================
# # 🛑 CONFIGURATION
# # ==========================================
# DB_NAME = "bmc_portal"
# COLLECTION_NAME = "complaints"
# WARDS_COLLECTION_NAME = "mumbai_wards" 
# COMPLAINTS_DIR = "bmc_complaints"

# # --- CLOUDINARY SETUP ---
# cloudinary.config( 
#   cloud_name = cloud_name, 
#   api_key = api_key, 
#   api_secret = os.environ.get("CLOUDINARY_API_SECRET") 
# )

# # ==========================================
# # 📤 HELPER: UPLOAD TO CLOUDINARY
# # ==========================================
# def upload_to_cloudinary(file_path, case_id):
#     """Uploads file to Cloudinary and returns a permanent public URL."""
#     print(f"\n   [UPLOAD DEBUG] Triggered for Case: {case_id}")
#     print(f"   [UPLOAD DEBUG] Relative Path Given: {file_path}")
    
#     # Let's check the absolute path to ensure Python is looking in the right folder
#     abs_path = os.path.abspath(file_path)
#     print(f"   [UPLOAD DEBUG] Absolute Path Checked: {abs_path}")
    
#     if not os.path.exists(abs_path):
#         print(f"   ❌ [UPLOAD ERROR] FILE DOES NOT EXIST at {abs_path}! Skipping upload.")
#         return None

#     # Let's check if the file is empty
#     file_size = os.path.getsize(abs_path)
#     print(f"   [UPLOAD DEBUG] File found! Size: {file_size} bytes.")
    
#     if file_size == 0:
#         print("   ❌ [UPLOAD ERROR] File is 0 bytes (Empty). Cloudinary will reject this.")
#         return None

#     try:
#         print(f"   ☁️ Uploading {os.path.basename(abs_path)} to Cloudinary...")
#         response = cloudinary.uploader.upload(
#             abs_path, 
#             resource_type="auto",
#             folder=f"bmc_complaints/{case_id}"
#         )
#         secure_url = response.get("secure_url")
#         print(f"   ✅ [UPLOAD SUCCESS] Link generated: {secure_url}")
#         return secure_url
        
#     except Exception as e:
#         print(f"   ❌ [UPLOAD CRASH] Cloudinary threw an exception: {e}")
#         return None


# def get_distance(lat1, lon1, lat2, lon2):
#     R = 6371000  
#     phi1, phi2 = math.radians(lat1), math.radians(lat2)
#     dphi = math.radians(lat2 - lat1)
#     dlambda = math.radians(lon2 - lon1)
#     a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
#     return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# def start_mongo_watcher():
#     print("👀 [MONGO WORKER] Connected to DB. Watching for resolved cases...")
#     client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/"))
#     db = client[DB_NAME]
#     collection = db[COLLECTION_NAME]
#     wards_collection = db[WARDS_COLLECTION_NAME]
    
#     while True:
#         if not os.path.exists(COMPLAINTS_DIR):
#             time.sleep(5)
#             continue
            
#         for case_id in os.listdir(COMPLAINTS_DIR):
#             case_folder = os.path.join(COMPLAINTS_DIR, case_id)
#             json_path = os.path.join(case_folder, "details.json")
            
#             if os.path.exists(json_path):
#                 try:
#                     with open(json_path, "r", encoding="utf-8") as f:
#                         metadata = json.load(f)
#                 except Exception as e:
#                     print(f"Error reading {case_id}: {e}")
#                     continue
                    
#                 if metadata.get("status") == "Resolved by AI":
#                     print(f"\n🚀 Processing {case_id}...")
                    
#                     # DEBUG: Let's see what extensions the JSON actually has saved
#                     ext = metadata.get("evidence_type", "jpg")
#                     desc_ext = "ogg" if metadata.get("desc_type") == "voice" else "txt"
                    
#                     print(f"   [JSON DEBUG] Extracted Image Ext: {ext}")
#                     print(f"   [JSON DEBUG] Extracted Audio/Text Ext: {desc_ext}")
                    
#                     lat = float(metadata.get("lat", metadata.get("gps", {}).get("lat", 0.0)))
#                     lon = float(metadata.get("lon", metadata.get("gps", {}).get("lon", 0.0)))
#                     phone = metadata.get("phone", metadata.get("citizen_phone", ""))
#                     pincode = metadata.get("pincode", "")

#                     ai_analysis = metadata.get("ai_analysis", {})
#                     problem_summary = ai_analysis.get("problem_summary") or metadata.get("problem_summary", "Summary unavailable")
#                     category = ai_analysis.get("category") or metadata.get("category", "General Administration")
#                     urgency = ai_analysis.get("urgency") or metadata.get("urgency", "Medium")

#                     clean_pincode = str(pincode).strip().replace(" ", "")
#                     ward_name = "Unknown Ward"
#                     if pincode:
#                         ward_data = wards_collection.find_one({"pincodes": clean_pincode})
#                         if ward_data:
#                             ward_name = ward_data.get("ward", "Unknown Ward")
                    
#                     # ==========================================
#                     # ☁️ UPLOAD FILES TO CLOUDINARY
#                     # ==========================================
#                     local_evidence_path = os.path.join(case_folder, f"evidence.{ext}")
#                     local_statement_path = os.path.join(case_folder, f"statement.{desc_ext}")
                    
#                     print(f"\n--- Initiating Uploads for {case_id} ---")
#                     cloud_evidence_link = upload_to_cloudinary(local_evidence_path, case_id)
#                     cloud_statement_link = upload_to_cloudinary(local_statement_path, case_id)
#                     print("------------------------------------------\n")

#                     mongo_document = {
#                         "case_id": metadata.get("case_id"),
#                         "phone": phone,
#                         "pincode": pincode,
#                         "ward": ward_name, 
#                         "lat": lat,
#                         "lon": lon,
#                         "desc_type": metadata.get("desc_type"),
#                         "status": "Pending Assignment", 
#                         "trust_score": 50,              
                        
#                         "problem_summary": problem_summary,
#                         "category": category,
#                         "urgency": urgency,
                        
#                         "evidence_url": cloud_evidence_link or f"{COMPLAINTS_DIR}/{case_id}/evidence.{ext}",
#                         "statement_url": cloud_statement_link or f"{COMPLAINTS_DIR}/{case_id}/statement.{desc_ext}",
                        
#                         "transcript": metadata.get("transcript", ""),
#                         "createdAt": datetime.utcnow()
#                     }
                    
#                     try:
#                         # Use update_one to overwrite the existing Registered document
#                         collection.update_one(
#                             {"case_id": mongo_document["case_id"]},
#                             {"$set": mongo_document},
#                             upsert=True
#                         )
#                         print(f"✅ Successfully updated {mongo_document['case_id']} in MongoDB with AI data!")
                        
#                         metadata["status"] = "Saved to DB"
                            
#                     except Exception as e:
#                         print(f"❌ Failed to insert/process {case_id}: {e}")
                        
#         time.sleep(3)

# if __name__ == "__main__":
#     start_mongo_watcher()


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
                    current_case_id = metadata.get("case_id")
                    
                    ext = metadata.get("evidence_type", "jpg")
                    desc_ext = "ogg" if metadata.get("desc_type") == "voice" else "txt"
                    
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
                    # 📍 GEOSPATIAL CLUSTERING & TRUST SCORE LOGIC
                    # ==========================================
                    print(f"   [GEO DEBUG] Scanning for nearby '{category}' issues in '{ward_name}'...")
                    
                    # 1. Fetch all existing complaints in the same ward and category
                    similar_complaints = list(collection.find({
                        "ward": ward_name,
                        "category": category,
                        "case_id": {"$ne": current_case_id} # Exclude the current case if it's already there
                    }))
                    
                    nearby_matches = []
                    
                    # 2. Measure distance for each existing complaint
                    for comp in similar_complaints:
                        comp_lat = comp.get("lat")
                        comp_lon = comp.get("lon")
                        
                        if comp_lat and comp_lon:
                            dist = get_distance(lat, lon, float(comp_lat), float(comp_lon))
                            if dist <= 50.0:  # Under 50 meters
                                nearby_matches.append(comp["case_id"])
                                
                    cluster_size = len(nearby_matches) + 1 # Include the new complaint
                    
                    # 3. Determine the dynamic score
                    if cluster_size >= 3:
                        new_trust_score = 90
                    elif cluster_size == 2:
                        new_trust_score = 70
                    else:
                        new_trust_score = 50
                        
                    print(f"   [GEO DEBUG] Found {len(nearby_matches)} complaints within 50m. New Trust Score: {new_trust_score}")
                    
                    # 4. Update the existing database entries with the new score
                    if nearby_matches:
                        collection.update_many(
                            {"case_id": {"$in": nearby_matches}},
                            {"$set": {"trust_score": new_trust_score}}
                        )
                        print(f"   ✅ [DB UPGRADE] Upgraded trust score to {new_trust_score} for existing cases: {nearby_matches}")

                    # ==========================================
                    # ☁️ UPLOAD FILES TO CLOUDINARY
                    # ==========================================
                    local_evidence_path = os.path.join(case_folder, f"evidence.{ext}")
                    local_statement_path = os.path.join(case_folder, f"statement.{desc_ext}")
                    
                    print(f"\n--- Initiating Uploads for {current_case_id} ---")
                    cloud_evidence_link = upload_to_cloudinary(local_evidence_path, current_case_id)
                    cloud_statement_link = upload_to_cloudinary(local_statement_path, current_case_id)
                    print("------------------------------------------\n")

                    mongo_document = {
                        "case_id": current_case_id,
                        "phone": phone,
                        "pincode": pincode,
                        "ward": ward_name, 
                        "lat": lat,
                        "lon": lon,
                        "desc_type": metadata.get("desc_type"),
                        "status": "Pending Assignment", 
                        "trust_score": new_trust_score,  # Injecting the dynamic score here
                        
                        "problem_summary": problem_summary,
                        "category": category,
                        "urgency": urgency,
                        
                        "evidence_url": cloud_evidence_link or f"{COMPLAINTS_DIR}/{current_case_id}/evidence.{ext}",
                        "statement_url": cloud_statement_link or f"{COMPLAINTS_DIR}/{current_case_id}/statement.{desc_ext}",
                        
                        "transcript": metadata.get("transcript", ""),
                        "createdAt": datetime.utcnow()
                    }
                    
                    try:
                        # Use update_one to overwrite the existing Registered document to prevent duplicates
                        collection.update_one(
                            {"case_id": current_case_id},
                            {"$set": mongo_document},
                            upsert=True
                        )
                        print(f"✅ Successfully updated {current_case_id} in MongoDB with AI data and Trust Score {new_trust_score}!")
                        
                        # Tell the local system this file is done so the loop moves on
                        metadata["status"] = "Saved to DB"
                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump(metadata, f, indent=4, ensure_ascii=False)
                            
                    except Exception as e:
                        print(f"❌ Failed to insert/process {current_case_id}: {e}")
                        
        time.sleep(3)

if __name__ == "__main__":
    start_mongo_watcher()