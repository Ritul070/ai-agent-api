import streamlit as st
import requests
import uuid

# ==========================================
# CONFIGURATION
# ==========================================
FASTAPI_URL = "https://ai-agent-api-bf17.onrender.com/ask"
API_KEY = "secret-123"  # FIX 1: Define the API Key

st.set_page_config(
    page_title="AI Chat Client",
    page_icon="🤖",
    layout="centered"
)

st.title("🤖 AI Chat Client")

# ==========================================
# SESSION STATE
# ==========================================
# FIX 3: Removed the redundant session_id line
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    
session_id = st.session_state.session_id

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display previous chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ==========================================
# CHAT INPUT
# ==========================================

if prompt := st.chat_input("Ask me anything..."):

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = requests.post(
                    FASTAPI_URL,
                    json={"prompt": prompt, "session_id": session_id},
                    headers={"x-api-key": API_KEY},
                    timeout=60
                )
                if response.status_code == 403:
                    answer = "Authentication failed: Invalid API Key."
                else:
                    response.raise_for_status()
                    data = response.json()
                    answer = data.get("answer", "No answer returned.")

            except requests.exceptions.RequestException as e:
                answer = f"Connection Error:\n\n{e}"
            # FIX 2: Aligned the except blocks vertically
            except Exception as e:
                answer = f"Unexpected Error:\n\n{e}"

            st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
