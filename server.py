import os
import json
import re
import requests
import google.generativeai as genai

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# =====================================================
# CONFIGURATION
# =====================================================

API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


if not API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is missing.")

if not TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY environment variable is missing.")

genai.configure(api_key=API_KEY)

model = genai.GenerativeModel("gemini-2.5-flash")

app = FastAPI(title="AI Agent API")


# =====================================================
# REQUEST MODEL
# =====================================================

class UserRequest(BaseModel):
    prompt: str


# =====================================================
# TOOLS
# =====================================================

def calculate_math(expression: str):
    try:
        return str(eval(expression))
    except Exception:
        return "Math Error"


def web_search(query: str):
    url = "https://api.tavily.com/search"

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": 3
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()

        data = response.json()

        if "results" not in data:
            return "No search results found."

        output = []

        for result in data["results"]:
            title = result.get("title", "")
            content = result.get("content", "")
            output.append(f"{title}\n{content}")

        return "\n\n".join(output)

    except Exception:
        return "I encountered an error while searching the web."


# =====================================================
# SANITIZER
# =====================================================

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
You are an AI Router.

Reply ONLY with valid JSON.

Choose one tool:

1. calculator
2. web_search
3. none

Format:

{
  "tool":"calculator",
  "input":"2+2"
}

{
  "tool":"web_search",
  "input":"latest AI news"
}

{
  "tool":"none",
  "input":"hello"
}

Return ONLY JSON.
"""

    response = model.generate_content(
        system_prompt + "\n\nUser: " + prompt
    )

    raw = sanitize_json(response.text)

    return json.loads(raw)


# =====================================================
# MAIN ENDPOINT
# =====================================================

@app.post("/ask")
def ask(request: UserRequest):

    try:
        routing = route_prompt(request.prompt)

        tool = routing["tool"]
        tool_input = routing["input"]

        if tool == "calculator":

            result = calculate_math(tool_input)

        elif tool == "web_search":

            result = web_search(tool_input)

        else:

            result = tool_input

        return {
            "question": request.prompt,
            "tool_used": tool,
            "answer": result
        }

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Gemini returned invalid JSON."
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
