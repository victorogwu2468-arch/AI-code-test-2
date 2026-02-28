
import streamlit as st
from openai import OpenAI
from io import StringIO
import contextlib
from pypdf import PdfReader 

# --- Security ---
def check_password():
    if "password_correct" not in st.session_state:
        def p_entered():
            if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
                st.session_state["password_correct"] = True
            else: st.error("Wrong password")
            st.title("🔏 USER AUTHENTICATION ")
        st.text_input("Password", type="password", on_change=p_entered, key="password")
        return False
    return True

if not check_password(): st.stop()

# --- Client ---
client = OpenAI(
    base_url="https://models.github.ai/inference", # Updated URL
    api_key=st.secrets["GITHUB_TOKEN"] 
)

# --- Sidebar & Files ---
with st.sidebar:
    st.header("Settings")
    uploaded = st.file_uploader("Upload Files", accept_multiple_files=True)
    file_context = ""
    if uploaded:
        for f in uploaded:
            if f.name.endswith(".pdf"):
                file_context += "".join([p.extract_text() for p in PdfReader(f).pages])
            else: file_context += f.read().decode()
    
    max_t = st.slider("Tokens", 50, 4000, 1000)
    temp = st.slider("Temp", 0.0, 1.0, 0.2)

# --- Main App ---
st.title("🤖 GPT-5.3 Codex Workspace")

if "messages" not in st.session_state: st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]): st.markdown(m["content"])

if prompt := st.chat_input("Message..."):
    # Limit history to 20 messages
    st.session_state.messages = st.session_state.messages[-20:]
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)

    try:
        with st.chat_message("assistant"):
            ctx = f"DOCS:\n{file_context}\n\nUSER: {prompt}" if file_context else prompt
            res = client.chat.completions.create(
                model="openai/gpt-5.3-codex",
                messages=[{"role": "user", "content": ctx}],
                max_tokens=max_t,
                temperature=temp
            )
            ans = res.choices[0].message.content # Fixed indexing
            st.markdown(ans)
            st.session_state.messages.append({"role": "assistant", "content": ans})
            
            # Simple Python execution detection
            if "```python" in ans:
                code = ans.split("```python")[1].split("```")[0]
                if st.button("Run This Code"):
                    out = StringIO()
                    with contextlib.redirect_stdout(out): exec(code)
                    st.code(out.getvalue())

    except Exception as e:
        st.error(f"Error: {e}")
