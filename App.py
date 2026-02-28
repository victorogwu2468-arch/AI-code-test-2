import streamlit as st
from openai import OpenAI
import sys
from io import StringIO
import contextlib
from pypdf import PdfReader  # Updated to the modern library

# --- 1. Security & Password Check ---
def check_password():
    if "password_correct" not in st.session_state:
        def password_entered():
            if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
                st.session_state["password_correct"] = True
                del st.session_state["password"]
            else:
                st.session_state["password_correct"] = False
        
        st.title("🔐 Access Restricted")
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        return False
    return st.session_state["password_correct"]

if not check_password():
    st.stop()

# --- 2. Client Setup (GitHub Models - FREE) ---
try:
    client = OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=st.secrets["GITHUB_TOKEN"] 
    )
    model_name = "gpt-5.3-codex" 
except Exception as e:
    st.error(f"⚠️ API Configuration error: {e}")
    st.stop()

# --- 3. Helpers: Execution & PDF Parsing ---
def execute_python_code(code):
    output = StringIO()
    try:
        with contextlib.redirect_stdout(output):
            exec(code, {"st": st, "print": print})
        return output.getvalue()
    except Exception as e:
        return f"Execution Error: {e}"

def extract_pdf_text(file):
    try:
        reader = PdfReader(file)
        return "".join([page.extract_text() for page in reader.pages])
    except Exception as e:
        return f"Error reading PDF: {e}"

# --- 4. Sidebar: Settings & Document Upload ---
with st.sidebar:
    st.header("🛠️ Workspace Settings")
    
    # 📄 Document Upload
    st.subheader("Knowledge Base")
    uploaded_files = st.file_uploader("Upload Docs (PDF, TXT, PY)", accept_multiple_files=True)
    file_context = ""
    if uploaded_files:
        for f in uploaded_files:
            if f.name.endswith(".pdf"):
                content = extract_pdf_text(f)
            else:
                content = f.read().decode("utf-8")
            file_context += f"\n--- FILE: {f.name} ---\n{content}\n"
        st.success(f"✅ Loaded {len(uploaded_files)} files")

    st.divider()
    
    # 🎛️ Model Sliders (Restored)
    st.subheader("Model Parameters")
    system_role = st.text_area("AI Persona:", "You are an elite developer and data scientist.")
    max_tokens = st.slider("Response Length", 50, 4000, 1000)
    temperature = st.slider("Creativity (Temperature)", 0.0, 1.0, 0.2)
    
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

# --- 5. Main Chat Interface ---
st.title("🤖 GPT-5.3 Codex: Free Workspace")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display message history
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# New Message Logic
if prompt := st.chat_input("Ask a question or request code..."):
    # Inject file context to the prompt
    full_prompt = f"CONTEXT DOCUMENTS:\n{file_context}\n\nUSER REQUEST: {prompt}" if file_context else prompt
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        with st.chat_message("assistant"):
            # --- TRIMMING HISTORY HERE ---
            # Keeps only the last 20 messages for GitHub token efficiency
            st.session_state.messages = st.session_state.messages[-20:]

            # Construct API messages
            api_msgs = [{"role": "system", "content": system_role}]
            # Send history, but only inject file context into the current prompt
            for m in st.session_state.messages[:-1]:
                api_msgs.append({"role": m["role"], "content": m["content"]})
            api_msgs.append({"role": "user", "content": full_prompt})

            completion = client.chat.completions.create(
                model=model_name,
                messages=api_msgs,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            response = completion.choices[0].message.content
            st.markdown(response)
            
            # --- 6. Code Execution Block ---
            if "```python" in response:
                # Basic parsing to get the code block
                code_parts = response.split("```python")
                if len(code_parts) > 1:
                    code_to_run = code_parts[1].split("```")[0]
                    if st.button("▶️ Run Python Code"):
                        exec_out = execute_python_code(code_to_run)
                        st.info("Execution Result:")
                        st.code(exec_out)

            st.session_state.messages.append({"role": "assistant", "content": response})
            
    except Exception as e:
        st.error(f"API Error: {e}")

