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

def repair_truncated_json(s: str) -> str:
    """Best-effort repair of a JSON string that was cut off mid-generation."""
    # Close any open string first
    # Count unescaped quotes to determine if we're inside a string
    in_string = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '\\' and in_string:
            i += 2
            continue
        if c == '"':
            in_string = not in_string
        i += 1

    if in_string:
        s += '"'  # close open string

    # Remove trailing commas before closing brackets (invalid JSON)
    import re
    s = re.sub(r',\s*([}\]])', r'\1', s)

    # Count and close unclosed brackets/braces
    stack = []
    in_string = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '\\' and in_string:
            i += 2
            continue
        if c == '"':
            in_string = not in_string
        elif not in_string:
            if c in ('{', '['):
                stack.append('}' if c == '{' else ']')
            elif c in ('}', ']'):
                if stack and stack[-1] == c:
                    stack.pop()
        i += 1

    # Close all unclosed structures
    s += ''.join(reversed(stack))
    return s


def normalize_plan(data: dict, original_prompt: str = "") -> dict:
    """Post-process the LLM output to fix common malformed structures."""

    # ── 1. Fix risks array ────────────────────────────────────────────────
    # LLM sometimes uses the risk text as a JSON key instead of a value.
    # Malformed:  {"Risk of X...": {"severity": "High", "mitigation": "..."}}
    # Expected:   {"risk": "Risk of X...", "severity": "High", "mitigation": "..."}
    if "risks" in data and isinstance(data["risks"], list):
        fixed_risks = []
        for item in data["risks"]:
            if not isinstance(item, dict):
                continue
            if "risk" in item and isinstance(item["risk"], str):
                fixed_risks.append(item)
            else:
                for key, val in item.items():
                    if isinstance(val, dict):
                        fixed_risks.append({
                            "risk": key,
                            "severity": val.get("severity", "Medium"),
                            "mitigation": val.get("mitigation", "")
                        })
                    else:
                        fixed_risks.append({
                            "risk": key,
                            "severity": item.get("severity", "Medium"),
                            "mitigation": item.get("mitigation", "")
                        })
                        break
        data["risks"] = fixed_risks

    # ── 2. Fix budget breakdown so amounts add up to the stated total ─────
    if "budget_breakdown" in data and isinstance(data["budget_breakdown"], dict) and original_prompt:
        data["budget_breakdown"] = _recompute_budget(data["budget_breakdown"], original_prompt)

    return data


def _extract_budget_from_prompt(prompt: str) -> float | None:
    """Try to extract a numeric budget value (in ₹) from the free-form prompt."""
    import re

    prompt_lower = prompt.lower()

    # Handle Indian shorthand: crore / lakh
    crore = re.search(r'[\u20b9rs\s]*([\d,]+(?:\.\d+)?)\s*crore', prompt_lower)
    if crore:
        num = float(crore.group(1).replace(',', ''))
        return num * 1_00_00_000

    lakh = re.search(r'[\u20b9rs\s]*([\d,]+(?:\.\d+)?)\s*lakh', prompt_lower)
    if lakh:
        num = float(lakh.group(1).replace(',', ''))
        return num * 1_00_000

    # Handle plain number with ₹ or "budget of X"
    plain = re.search(
        r'(?:budget\s+of\s+|budget\s*[:\-=]\s*|[\u20b9$])\s*([\d,]+(?:\.\d+)?)',
        prompt_lower
    )
    if plain:
        return float(plain.group(1).replace(',', ''))

    return None


def _parse_amount(value: str) -> float | None:
    """Extract a numeric ₹ amount from a string like '₹15,00,000 (30%)'."""
    import re
    match = re.search(r'[\d,]+(?:\.\d+)?', value.replace('\u20b9', '').replace(',', ''))
    if match:
        return float(match.group())
    return None


def _recompute_budget(breakdown: dict, prompt: str) -> dict:
    """
    Recompute budget line items so they sum to the total stated in the prompt.
    Uses the LLM's own percentage hints if present, otherwise falls back to
    standard construction splits: labour 30%, materials 45%, equipment 15%, contingency 10%.
    """
    import re

    total = _extract_budget_from_prompt(prompt)
    if total is None or total <= 0:
        return breakdown  # can't fix without a known total

    # Store total as a formatted string
    def fmt(amount: float) -> str:
        # Format with Indian comma style e.g. 15,00,000
        s = f"{amount:,.0f}"
        return f"\u20b9{s}"

    # Extract percentage hints from LLM output if available
    splits = {}
    for key in ("labour", "materials", "equipment", "contingency"):
        val = breakdown.get(key, "")
        pct_match = re.search(r'\((\d+(?:\.\d+)?)%\)', str(val))
        if pct_match:
            splits[key] = float(pct_match.group(1)) / 100.0

    # Default splits when LLM didn't include percentages
    defaults = {"labour": 0.30, "materials": 0.45, "equipment": 0.15, "contingency": 0.10}
    for key, default_pct in defaults.items():
        if key not in splits:
            splits[key] = default_pct

    # Normalise so percentages sum to exactly 1.0
    total_pct = sum(splits.values())
    if total_pct > 0:
        splits = {k: v / total_pct for k, v in splits.items()}

    # Compute amounts
    computed = {k: round(total * pct) for k, pct in splits.items()}

    # Build updated breakdown preserving notes and any extra keys
    updated = dict(breakdown)
    updated["total"] = fmt(total)
    for key, amount in computed.items():
        pct_display = round(splits[key] * 100, 1)
        updated[key] = f"{fmt(amount)} ({pct_display}%)"

    return updated



def is_project_request(prompt: str) -> bool:
    """Classify if the prompt is asking to build/plan a project or if it's a normal chat message."""
    import requests
    from config import OLLAMA_URL
    import json

    system_prompt = f"""You are an intent classifier for a construction AI.
Analyze the user's message. 
If they are asking to build, design, construct, or plan a project, output ONLY {{"is_project": true}}.
If they are just saying hello, thanking you, or asking a general question NOT about creating a specific project, output ONLY {{"is_project": false}}.

User message: {prompt}"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": "phi3",
                "prompt": system_prompt,
                "format": "json",
                "stream": False,
                "options": {
                    "num_predict": 50
                }
            }
        )
        resp_json = response.json()
        if "response" in resp_json:
            result = json.loads(clean_response(resp_json["response"]))
            return result.get("is_project", True)
    except Exception:
        pass
    
    # Default to true if classification fails so we don't break the main flow
    return True


def generate_engineer_chat_response(prompt: str) -> dict:
    """Generate a standard conversational response without RAG."""
    import requests
    from config import OLLAMA_URL
    
    system_prompt = f"""You are AURA, an expert AI construction planning assistant for the Civicora platform.
The user sent a conversational message. Respond politely and concisely in plain text (no markdown, no json).

User message: {prompt}
Response:"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": "phi3",
                "prompt": system_prompt,
                "stream": False,
                "options": {
                    "num_predict": 200
                }
            }
        )
        resp_json = response.json()
        if "response" in resp_json:
            return {
                "is_project_request": False,
                "message": resp_json["response"].strip()
            }
    except Exception:
        pass
    
    return {
        "is_project_request": False,
        "message": "Hello! How can I help you with your construction projects today?"
    }


def generate_engineer_plan(prompt: str, context: str):
    original_prompt = prompt  # preserve before the f-string overwrites the variable
    prompt = f"""You are AURA, an expert AI construction planning assistant for the Civicora platform.
An engineer has submitted a new client project request as free-form text. Your job is to generate a detailed, realistic project plan using the construction knowledge base provided.

STRICT RULES:
- Output ONLY valid JSON
- No markdown, no explanation outside JSON
- DO NOT wrap output in ```json or markdown
- Write clear, professional English
- All arrays must have at least one item where applicable
- Keep descriptions concise (1 sentence max per field)
- Always use the Indian Rupee symbol ₹ for all monetary values, NEVER use $

BUDGET RULES (critical):
- If the engineer's request mentions a total budget, ALL breakdown amounts MUST sum exactly to that total
- Use the RAG CONTEXT to determine realistic percentage splits (e.g. labour ~30%, materials ~45%, equipment ~15%, contingency ~10%)
- Apply those percentage splits to the actual stated budget to compute each line item amount
- Example: if budget is ₹50,00,000 and labour is 30%, then labour = ₹15,00,000 (30%)
- Do NOT invent arbitrary numbers — calculate each amount from (percentage × total budget)
- Add a note in "notes" if the stated budget appears insufficient based on RAG knowledge

RAG CONTEXT (construction knowledge base — use this to estimate real costs):
{context}

ENGINEER'S REQUEST:
{prompt}

Generate an actionable project plan following this exact JSON format:
{{
  "project_scope": {{
    "summary": "brief project overview",
    "key_deliverables": ["deliverable1", "deliverable2"],
    "exclusions": ["what is NOT included"]
  }},
  "timeline": {{
    "estimated_duration": "e.g. 8 months",
    "phases": [
      {{
        "phase": "Phase name",
        "duration": "e.g. 4 weeks",
        "description": "what happens in this phase"
      }}
    ],
    "critical_milestones": ["milestone1", "milestone2"]
  }},
  "resource_allocation": {{
    "team": [
      {{
        "role": "e.g. Site Engineer",
        "count": 2,
        "responsibility": "brief description"
      }}
    ],
    "equipment": ["equipment1", "equipment2"],
    "materials": ["material1", "material2"]
  }},
  "budget_breakdown": {{
    "total": "the full stated budget e.g. ₹50,00,000",
    "labour": "e.g. ₹15,00,000 (30%)",
    "materials": "e.g. ₹22,50,000 (45%)",
    "equipment": "e.g. ₹7,50,000 (15%)",
    "contingency": "e.g. ₹5,00,000 (10%)",
    "notes": "assessment of whether the client's budget is realistic"
  }},
  "risks": [
    {{
      "risk": "risk description as a plain string value",
      "severity": "Low | Medium | High",
      "mitigation": "mitigation strategy"
    }}
  ],
  IMPORTANT: In the risks array, 'risk' must ALWAYS be a key with a string value.
  NEVER use the risk description as a JSON key. Every risk object must have exactly three keys: risk, severity, mitigation.
  "recommendations": ["recommendation1", "recommendation2"],
  "next_steps": ["step1", "step2"]
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
                "num_predict": -1   # no limit — let the model finish the full JSON
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
        return {"error": f"Request Error: {str(e)}", "raw": response.text}

    # First attempt: parse as-is
    try:
        data = json.loads(cleaned)
        data = normalize_plan(data, original_prompt)
        return data
    except Exception:
        pass

    # Second attempt: repair truncated JSON and retry
    try:
        repaired = repair_truncated_json(cleaned)
        data = json.loads(repaired)
        data = normalize_plan(data, original_prompt)
        return data
    except Exception as e:
        return {
            "error": f"LLM Parsing Error: {str(e)}",
            "raw": cleaned[:300]
        }