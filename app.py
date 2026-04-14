import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, UploadFile, File, Header, HTTPException
import shutil
from pydantic import BaseModel
from typing import Optional, List
from rag.ingest import ingest_pdf
from rag_pipeline import ask, ask_client
from config import INTERNAL_SECRET

app = FastAPI()

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