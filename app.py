from fastapi import FastAPI, UploadFile, File
import shutil
from pydantic import BaseModel
from rag.ingest import ingest_pdf
from rag_pipeline import ask
app = FastAPI()

@app.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    file_path = f"temp_{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    count = ingest_pdf(file_path)

    return {"message": f"{count} chunks added"}

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
def chat(req: ChatRequest):
    response = ask(req.message)
    return {"response": response}