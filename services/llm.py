import requests
import json
import re
from config import OLLAMA_URL

def clean_response(text):
    # Find the first '{' and last '}' to extract only the JSON object
    match = re.search(r'(\{.*\})', text, re.DOTALL)
    if match:
        text = match.group(1)
    
    # remove markdown blocks if they still exist
    text = re.sub(r"```json|```", "", text).strip()
    return text

def generate_answer(query, context):
    prompt = f"""
You are AURA, an AI assistant for Civicora construction management platform.

STRICT RULES:
- Output ONLY valid JSON
- No markdown
- No explanation outside JSON
- DO NOT wrap output in ```json or markdown.
Write clear, grammatically correct English.
Avoid typos or broken words.

Use the PROJECT CONTEXT section when the user asks about "my project", "this project", or "progress".

Context:
{context}

User:
{query}

Format:
{{
  "answer": "",
  "materials": [],
  "risks": [],
  "next_question": "",
  "project_insights": ""
}}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "phi3",
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "num_predict": 400   # prevents cut-off
            }
        }
    )

    try:
        resp_json = response.json()
        if "response" not in resp_json:
            return {"error": "Ollama Error", "raw": json.dumps(resp_json)}
        raw = resp_json["response"]
        cleaned = clean_response(raw)
    except Exception as e:
        return {"error": str(e), "raw": response.text}

    try:
        data = json.loads(cleaned)
        # Ensure 'answer' is present
        if "answer" not in data:
             data["answer"] = "AI responded but 'answer' field was missing."
        return data
    except Exception as e:
        return {
            "answer": f"LLM Parsing Error: {str(e)}\nRaw: {cleaned[:200]}...",
            "awaiting_selection": False,
            "error": True
        }

def generate_client_answer(query, context, mode="list"):
    if mode == "list":
        prompt_instruction = """You are AURA, an AI assistant for the Civicora platform.
The user has multiple projects. 

RULES:
1. If the user's message is a greeting or unrelated to their projects, respond naturally and helpfully.
2. If the user is asking about their projects or just starting, help them select a project by presenting the numbered list from the context.
3. When asking them to select a project, set "awaiting_selection" to true.

Output JSON format:
{
  "answer": "your response to the user",
  "awaiting_selection": true,
  "project_insights": "",
  "next_question": "",
  "projects": []
}"""
    else:
        prompt_instruction = """You are AURA, an AI assistant for the Civicora platform.
The user has selected a specific project.

RULES:
1. Answer their question using the project and milestone data provide in the context.
2. Give a clear status summary: how many milestones are complete, in progress, delayed, or pending.
3. If the message is a greeting or unrelated, respond naturally but keep the project context in mind.

Output JSON format:
{
  "answer": "detailed response using project data",
  "awaiting_selection": false,
  "project_insights": "specific insight based on milestone data",
  "next_question": "a helpful follow-up question",
  "materials": [],
  "risks": []
}"""

    prompt = f"""{prompt_instruction}

STRICT RULES:
- Output ONLY valid JSON
- No markdown
- No explanation outside JSON
- DO NOT wrap output in ```json or markdown.
Write clear, grammatically correct English.
Avoid typos or broken words.

Context:
{context}

User:
{query}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "phi3",
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "num_predict": 400
            }
        }
    )

    try:
        resp_json = response.json()
        if "response" not in resp_json:
            return {"answer": f"Ollama Error: {json.dumps(resp_json)}"}
        raw = resp_json["response"]
        cleaned = clean_response(raw)
    except Exception as e:
        return {"answer": f"Request Error: {str(e)}"}

    try:
        data = json.loads(cleaned)
        if "answer" not in data:
            data["answer"] = "AI responded but 'answer' field was missing."
        return data
    except Exception as e:
        return {
            "answer": f"LLM Parsing Error: {str(e)}\nRaw: {cleaned[:200]}...",
            "error": True
        }