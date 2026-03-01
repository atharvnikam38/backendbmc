import os
import time
import json
import base64
from typing import TypedDict, Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
import google.generativeai as genai

# ==========================================
# 0. SETUP & CREDENTIALS
# ==========================================
load_dotenv()
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

COMPLAINTS_DIR = "bmc_complaints"

# ==========================================
# 1. LANGGRAPH: STATE & SCHEMA
# ==========================================
class ComplaintState(TypedDict):
    audio_path: Optional[str]
    text_input: Optional[str]
    extracted_text: Optional[str]
    final_category: Optional[dict]

BMCCategories = Literal[
    "Roads & Infrastructure", 
    "Sanitation & Waste", 
    "Water Supply", 
    "Sewage & Drainage", 
    "Electrical & Streetlights", 
    "Encroachment Removal", 
    "Public Health", 
    "Storm Water Drainage", 
    "General Administration"
]

class BMCComplaint(BaseModel):
    problem_summary: str = Field(description="A clear, text-based summary of the problem.")
    category: BMCCategories = Field(description="The exact matched category from the allowed list.")
    urgency: str = Field(description="Urgency level: Low, Medium, High, or Critical")

# ==========================================
# 2. LANGGRAPH: NODES & ROUTER
# ==========================================
def process_audio_node(state: ComplaintState):
    """Uses Gemini 2.5 Flash to natively process .ogg, .mp3, or .wav files."""
    print(f"🎙️ [GRAPH] Routing to: Audio Node (Processing {state['audio_path']})...")
    
    try:
        print("   -> Uploading audio to Gemini...")
        audio_file = genai.upload_file(path=state["audio_path"])
        
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = (
            "Listen to this civic complaint. Transcribe it accurately. "
            "If it is in Hindi, Marathi, Gujarati, or any other Indian language, translate it to English. "
            "Output ONLY the plain text of the complaint."
        )
        
        response = model.generate_content([prompt, audio_file])
        extracted_text = response.text
        print(f"   -> Audio Transcribed & Translated: {extracted_text.strip()}")
        
        # Clean up file from Google's servers
        genai.delete_file(audio_file.name)
        
    except Exception as e:
        extracted_text = f"Error processing audio with Gemini: {e}"
        print(f"   -> {extracted_text}")
        
    return {"extracted_text": extracted_text}

def classifier_node(state: ComplaintState):
    """Takes all extracted text and categorizes it strictly."""
    print("🧠 [GRAPH] Routing to: Classifier Node...")
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(BMCComplaint)
    
    combined_context = f"User Input: {state.get('text_input', '')}\nMedia Extraction: {state.get('extracted_text', '')}"
    
    prompt = f"Analyze the following civic complaint context and categorize it:\n\n{combined_context}"
    result = structured_llm.invoke(prompt)
    
    return {"final_category": result.model_dump()}

def route_input(state: ComplaintState):
    """Inspects the state and routes to the appropriate media node."""
    if state.get("audio_path"):
        return "process_audio"
    else:
        return "classifier"

# ==========================================
# 3. LANGGRAPH: COMPILE WORKFLOW
# ==========================================
workflow = StateGraph(ComplaintState)

workflow.add_node("process_audio", process_audio_node)
workflow.add_node("classifier", classifier_node)

workflow.set_conditional_entry_point(
    route_input,
    {
        "process_audio": "process_audio",
        "classifier": "classifier"
    }
)

workflow.add_edge("process_audio", "classifier")
workflow.add_edge("classifier", END)

bmc_app = workflow.compile()
print("✅ LangGraph AI Pipeline compiled successfully!")


# ==========================================
# 4. BOT WORKER: PROCESS INDIVIDUAL CASE
# ==========================================
def process_case(case_folder, metadata):
    """This is where the AI magic happens using our LangGraph workflow."""
    case_id = metadata.get("case_id", "UNKNOWN_ID")
    print(f"\n⚙️  [AI WORKER] Picking up new case: {case_id}")
    
    metadata["status"] = "Processing AI"
    with open(os.path.join(case_folder, "details.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)
        
    desc_type = metadata.get("desc_type")
    
    input_state = {
        "audio_path": None,
        "text_input": None,
        "extracted_text": None,
        "final_category": None
    }
    
    if desc_type == "voice":
        voice_path = os.path.join(case_folder, "statement.ogg")
        if os.path.exists(voice_path):
            input_state["audio_path"] = voice_path
        else:
            print(f"⚠️ Warning: {voice_path} not found!")
    else:
        text_path = os.path.join(case_folder, "statement.txt")
        if os.path.exists(text_path):
            with open(text_path, "r", encoding="utf-8") as f:
                input_state["text_input"] = f.read()

    print(f"🚀 [AI WORKER] Triggering LangGraph for {case_id}...")
    result = bmc_app.invoke(input_state)
    
    ai_output = result.get("final_category", {})
    
    # ==========================================
    # 🔗 FIXED: NESTING THE OUTPUT FOR MONGODB
    # ==========================================
    metadata["status"] = "Resolved by AI"
    
    # Bundle the LangGraph output into the 'ai_analysis' dictionary
    metadata["ai_analysis"] = {
        "problem_summary": ai_output.get("problem_summary", "Summary unavailable"),
        "category": ai_output.get("category", "General Administration"),
        "urgency": ai_output.get("urgency", "Low")
    }
    
    if result.get("extracted_text"):
        metadata["transcript"] = result["extracted_text"].strip()
    
    with open(os.path.join(case_folder, "details.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)
        
    print(f"✅ [AI WORKER] Successfully processed and categorized {case_id}!")
    print(f"   -> Category: {metadata['ai_analysis']['category']} | Urgency: {metadata['ai_analysis']['urgency']}")


# ==========================================
# 5. BOT WORKER: FOLDER MONITORING
# ==========================================
def watch_folder():
    """Continuously monitors the folder for new, unprocessed complaints."""
    print("👀 [AI WORKER] Started monitoring the bmc_complaints folder...")
    
    while True:
        if os.path.exists(COMPLAINTS_DIR):
            for case_id in os.listdir(COMPLAINTS_DIR):
                case_folder = os.path.join(COMPLAINTS_DIR, case_id)
                json_path = os.path.join(case_folder, "details.json")
                
                if os.path.exists(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            metadata = json.load(f)
                            
                        if metadata.get("status") == "Registered":
                            process_case(case_folder, metadata)
                            
                    except json.JSONDecodeError:
                        pass 
                        
        time.sleep(5)

if __name__ == "__main__":
    os.makedirs(COMPLAINTS_DIR, exist_ok=True)
    watch_folder()