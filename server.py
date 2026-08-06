import os
import json
import re
import requests
import google.generativeai as genai
import sqlite3

from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from fastapi.security import APIKeyHeader

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For production, you would put your specific Streamlit URL here
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app = FastAPI(title="AI Agent API")

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

VALID_API_KEY = os.getenv("VALID_API_KEY")
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

def verify_api_key(api_key: str = Depends(api_key_header)):
    if not api_key or api_key != VALID_API_KEY:
        raise HTTPException(status_code=403, detail="Could not validate credentials")
    return api_key

# 1. Connect to the database
conn = sqlite3.connect('memory.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        role TEXT,
        content TEXT
    )
''')
conn.commit()
print("Database setup complete!")

# =====================================================
# CONFIGURATION
# =====================================================
API_KEY =os.getenv("API_KEY")
TAVILY_API_KEY =os.getenv("TAVILY_API_KEY")

if not API_KEY: raise ValueError("GEMINI_API_KEY environment variable is missing.")
if not TAVILY_API_KEY: raise ValueError("TAVILY_API_KEY environment variable is missing.")

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# =====================================================
# REQUEST MODEL
# =====================================================
class UserRequest(BaseModel):
    prompt: str
    session_id: str

# =====================================================
# TOOLS
# =====================================================
def calculate_math(expression: str):
    try: return str(eval(expression))
    except Exception: return "Math Error"

def web_search(query: str):
    url = "https://api.tavily.com/search"
    payload = {"api_key": TAVILY_API_KEY, "query": query, "search_depth": "advanced", "max_results": 3}
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        if "results" not in data: return "No search results found."
        output = []
        for result in data["results"]:
            title = result.get("title", "")
            content = result.get("content", "")
            output.append(f"{title}\n{content}")
        return "\n\n".join(output)
    except Exception:
        return "I encountered an error while searching the web."

def sanitize_json(text: str):
    text = text.strip()
    text = re.sub(r"^```json", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```", "", text)
    text = re.sub(r"```$", "", text)
    return text.strip()

# =====================================================
# GEMINI JSON ROUTER
# =====================================================
def route_prompt(prompt: str):
    system_prompt = """
You are an AI Router. Reply ONLY with valid JSON.
Choose one tool:
1. calculator
2. web_search
3. none
Format:
{"tool":"calculator","input":"2+2"}
{"tool":"web_search","input":"latest AI news"}
{"tool":"none","input":"Your actual conversational reply to the user goes here."}
Return ONLY JSON.
"""
    response = model.generate_content(system_prompt + "\n\nUser: " + prompt)
    raw = sanitize_json(response.text)
    return json.loads(raw)

# =====================================================
# MAIN ENDPOINT
# =====================================================
@app.post("/ask", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def ask(request: Request, user_req: UserRequest):
    try:
        # FIX 1: Use user_req.session_id and user_req.prompt
        cursor.execute(
            "SELECT role, content FROM chat_history WHERE session_id = ? ORDER BY id DESC LIMIT 5",
            (user_req.session_id,)
        )
        rows = cursor.fetchall()
        rows = rows[::-1]
        
        history_text = ""
        for row in rows:
            history_text += f"{row[0]}: {row[1]}\n"
            
        full_prompt = f"History:\n{history_text}\nNew User Input: {user_req.prompt}"
        
        routing = route_prompt(full_prompt)
        
        if not routing or "tool" not in routing:
            tool = "none"
            tool_input = user_req.prompt
        else:
            tool = routing["tool"]
            tool_input = routing["input"]

        if tool == "calculator":
            result = calculate_math(tool_input)
        elif tool == "web_search":
            result = web_search(tool_input)
        else:
            convo_prompt = f"You are a helpful AI assistant. Reply briefly to the user. \n\n{full_prompt}"
            response = model.generate_content(convo_prompt)
            result = response.text

        cursor.execute(
            "INSERT INTO chat_history (session_id, role, content) VALUES (?, ?, ?)",
            (user_req.session_id, "user", user_req.prompt)
        )
        cursor.execute(
            "INSERT INTO chat_history (session_id, role, content) VALUES (?, ?, ?)",
            (user_req.session_id, "assistant", result)
        )
        conn.commit()

        return {
            "question": user_req.prompt,
            "tool_used": tool,
            "answer": result
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Gemini returned invalid JSON.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
