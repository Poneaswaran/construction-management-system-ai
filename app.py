import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, UploadFile, File, Header, HTTPException
import shutil
from pydantic import BaseModel
from typing import Optional, List
from rag.ingest import ingest_pdf, ingest_pdf_with_metadata
from rag_pipeline import ask, ask_client
from services.llm import generate_engineer_plan, is_project_request, generate_engineer_chat_response
from config import INTERNAL_SECRET

app = FastAPI()

# ---------------------------------------------------------------------------
# Startup: auto-ingest location-tagged documents
# ---------------------------------------------------------------------------
CHENNAI_PDF = os.path.join(
    os.path.dirname(__file__),
    "rag", "documents", "engineer", "Chennai Requirements.pdf"
)

@app.on_event("startup")
def auto_ingest_documents():
    if os.path.exists(CHENNAI_PDF):
        count = ingest_pdf_with_metadata(CHENNAI_PDF, {"location": "chennai"})
        print(f"[Startup] Ingested Chennai Requirements PDF → {count} chunks")
    else:
        print(f"[Startup] WARNING: Chennai PDF not found at {CHENNAI_PDF}")

class MilestoneContext(BaseModel):
    id: str
    title: str
    status: str
    due_date: str
    completed_at: Optional[str] = None
    order_index: int
    description: str

class ProjectContext(BaseModel):
    project_id: str
    project_name: str
    status: str
    budget: float
    progress_percentage: float
    start_date: str
    end_date: str
    location: str
    description: str
    milestones: List[MilestoneContext]

class ChatRequest(BaseModel):
    message: str
    project_context: Optional[ProjectContext] = None

class ProjectSummary(BaseModel):
    project_id: str
    project_name: str
    status: str
    budget: float
    progress_percentage: float
    start_date: str
    end_date: str
    location: str

class ClientChatRequest(BaseModel):
    message: str
    all_projects: Optional[List[ProjectSummary]] = None
    selected_project: Optional[ProjectContext] = None

class EngineerChatRequest(BaseModel):
    prompt: str

@app.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    file_path = f"temp_{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    count = ingest_pdf(file_path)

    return {"message": f"{count} chunks added"}

@app.post("/chat")
def chat(req: ChatRequest, x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key")):
    if not x_internal_key or x_internal_key != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    response = ask(req.message, req.project_context)
    return {"response": response}

@app.post("/client-chat")
def client_chat(req: ClientChatRequest):
    print("\n================== INCOMING PAYLOAD ==================")
    print(req)
    print("======================================================\n")
    
    response = ask_client(req.message, req.all_projects, req.selected_project)
    
    print("\n================== OUTGOING RESPONSE ==================")
    print(response)
    print("======================================================\n")
    
    return {"response": response}

@app.post("/engineer-chat")
def engineer_chat(req: EngineerChatRequest):
    print("\n================== INCOMING PAYLOAD (ENGINEER) ==================")
    print(req)
    print("=================================================================\n")

    # 1. Classify the user's intent
    if not is_project_request(req.prompt):
        # 2a. If normal message, respond conversationally WITHOUT RAG
        chat_resp = generate_engineer_chat_response(req.prompt)
        
        print("\n================== OUTGOING RESPONSE (ENGINEER CHAT) ==================")
        print(chat_resp)
        print("=======================================================================\n")
        
        return {"plan": chat_resp}

    # 2b. If it IS a project request, do the full RAG knowledge search
    from rag.chroma_client import collection

    # Detect location keywords in prompt to apply metadata filtering
    prompt_lower = req.prompt.lower()
    LOCATION_KEYWORDS = {
        "chennai": ["chennai", "madras", "tamil nadu"],
    }

    detected_location = None
    for location, keywords in LOCATION_KEYWORDS.items():
        if any(kw in prompt_lower for kw in keywords):
            detected_location = location
            break

    # Build query args — filter by location metadata if detected
    query_kwargs = {
        "query_texts": [req.prompt],
        "n_results": 3,
    }
    if detected_location:
        query_kwargs["where"] = {"location": detected_location}
        print(f"[engineer-chat] Location detected: {detected_location} — applying metadata filter")

    results = collection.query(**query_kwargs)

    # Cap context to 800 chars to keep LLM prompt short and fast
    raw_context = "\n\n".join(results["documents"][0])
    context = raw_context[:800]

    plan = generate_engineer_plan(
        prompt=req.prompt,
        context=context
    )

    # Include flag for frontend to know this is a full project plan
    if isinstance(plan, dict):
        plan["is_project_request"] = True

    print("\n================== OUTGOING RESPONSE (ENGINEER PLAN) ==================")
    print(plan)
    print("=======================================================================\n")

    return {"plan": plan}