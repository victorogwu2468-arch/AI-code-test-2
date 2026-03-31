import streamlit as st
from openai import OpenAI
from sentence_transformers import SentenceTransformer, util
from PyPDF2 import PdfReader
from docx import Document
from supabase import create_client, Client
import tiktoken
import torch
import datetime  
import os   
import requests     
from langdetect import detect

# --- 0. PAGE CONFIG ---
st.set_page_config(
    page_title="AI Assistant Pro",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS STYLING ---
st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
.stApp { background: linear-gradient(135deg, #0f172a, #020617); }
section[data-testid="stSidebar"] { background: #020617; }
.stButton>button {
    background: linear-gradient(135deg, #6366F1, #8B5CF6);
    color: white;
    border-radius: 12px;
    border: none;
}
[data-testid="stChatMessage"] {
    background: #020617;
    border: 1px solid #1e293b;
    border-radius: 14px;
    padding: 10px;
}
/* Premium Buttons */
.stButton>button {
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    color: white;
    border-radius: 14px;
    border: none;
    height: 3.8em;
    font-weight: 600;
    font-size: 1.1rem !important;
    box-shadow: 0 4px 15px rgba(99, 102, 241, 0.3);
    transition: all 0.3s ease;
}

.stButton>button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(139, 92, 246, 0.4);
}

</style>
""", unsafe_allow_html=True)

# --- 1. SUPABASE INIT ---
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- 2. DATABASE & STORAGE FUNCTIONS ---
def load_user_data_db(email):
    response = supabase.table("user_chats").select("*").eq("email", email).execute()
    if response.data:
        return response.data[0]["data"]
    return {"sessions": {}, "knowledge_base": []}

def save_user_data_db(email, data):
    supabase.table("user_chats").upsert({
        "email": email,
        "data": data
    }).execute()

def upload_to_supabase(uploaded_file):
    user_id = st.session_state.user.id
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_path = f"{user_id}/{timestamp}_{uploaded_file.name}"
    try:
        file_bytes = uploaded_file.getvalue()
        supabase.storage.from_('generated-images').upload(
            path=unique_path,
            file=file_bytes,
            file_options={"content-type": uploaded_file.type}
        )
        return supabase.storage.from_('generated-images').get_public_url(unique_path)
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None

def generate_and_save_image(prompt, size, quality):
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality=quality,
            n=1
        )
        temp_url = response.data[0].url
        img_data = requests.get(temp_url).content
        user_id = st.session_state.user.id
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{user_id}/gen_{timestamp}.png"

        supabase.storage.from_('generated-images').upload(
            path=filename,
            file=img_data,
            file_options={"content-type": "image/png"}
        )
        return supabase.storage.from_('generated-images').get_public_url(filename)
    except Exception as e:
        st.error(f"Image generation failed: {e}")
        return None

def is_image_request(text):
    keywords = ["generate an image", "create an image", "make an image", "generate image", "create image"]
    return any(keyword in text.lower() for keyword in keywords)

# --- 3. AUTH SYSTEM ---
def auth_ui():
    st.title("🔐 AI Login / Signup")
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    with tab1:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user = res.user
                st.session_state.logged_in = True
                data = load_user_data_db(res.user.email)
                st.session_state.user_data = data
                st.session_state.knowledge_base = data.get("knowledge_base", [])
                st.session_state.messages = []
                st.session_state.current_session_id = None
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")
    with tab2:
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Password", type="password", key="signup_pass")
        if st.button("Sign Up"):
            try:
                supabase.auth.sign_up({"email": email, "password": password})
                st.success("Account created! You can now log in.")
            except Exception as e:
                st.error(f"Signup failed: {e}")

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    auth_ui()
    st.stop()

# --- 4. CORE CLIENTS ---
user_email = st.session_state.user.email
client = OpenAI(
    base_url="https://azure.com",
    api_key=st.secrets["GITHUB_TOKEN"]
)
model_name = st.secrets.get("MODEL_NAME", "gpt-4-32k")

@st.cache_resource
def get_embed_model():
    return SentenceTransformer('all-MiniLM-L6-v2')

embed_model = get_embed_model()

# --- 5. SIDEBAR ---
st.sidebar.markdown("<h2 style='text-align:center;'>🤖 AI Dashboard</h2>", unsafe_allow_html=True)
st.sidebar.markdown(f"👤 **{user_email}**")

if st.sidebar.button("🚪 Logout"):
    st.session_state.clear()
    st.rerun()

if st.sidebar.button("➕ New Project", use_container_width=True):
    new_id = str(len(st.session_state.user_data["sessions"]) + 1)
    st.session_state.current_session_id = new_id
    st.session_state.messages = []
    st.session_state.user_data["sessions"][new_id] = {"title": "New Chat", "messages": []}
    save_user_data_db(user_email, st.session_state.user_data)
    st.rerun()

st.sidebar.subheader("Recent Projects")
for sess_id, sess_info in list(st.session_state.user_data["sessions"].items()):
    if st.sidebar.button(sess_info["title"], key=sess_id, use_container_width=True):
        st.session_state.current_session_id = sess_id
        st.session_state.messages = sess_info["messages"]
        st.rerun()

# --- SETTINGS & LANGUAGE ---
languages = {"Auto": "auto", "English": "en", "Spanish": "es", "French": "fr", "German": "de", "Chinese": "zh", "Arabic": "ar"}
selected_lang_name = st.sidebar.selectbox("🌍 Response Language", list(languages.keys()))

system_role = st.sidebar.text_area("AI Persona", "You are a helpful AI assistant.")
max_tokens = st.sidebar.slider("Max Tokens", 50, 2000, 500)
temperature = st.sidebar.slider("Temperature", 0.0, 1.0, 0.7)

st.sidebar.subheader("🎨 Image Settings")
img_size = st.sidebar.selectbox("Image Size", ["1024x1024", "1024x1792", "1792x1024"])
img_quality = st.sidebar.select_slider("Quality", options=["standard", "hd"])

uploaded_files = st.sidebar.file_uploader("Upload Files", accept_multiple_files=True, type=["pdf", "txt", "docx"])

# --- 6. FILE PROCESSING & RAG ---
def process_files(files):
    chunks = []
    for file in files:
        ext = file.name.split(".")[-1].lower()
        if ext == "pdf":
            pdf = PdfReader(file)
            for page in pdf.pages: chunks.append(page.extract_text())
        elif ext == "txt":
            chunks.append(file.read().decode("utf-8"))
        elif ext == "docx":
            doc = Document(file)
            for p in doc.paragraphs: chunks.append(p.text)
    return [c.strip() for c in chunks if c]

if uploaded_files:
    for file in uploaded_files:
        upload_to_supabase(file)
    new_chunks = process_files(uploaded_files)
    st.session_state.knowledge_base.extend(new_chunks)
    st.session_state.user_data["knowledge_base"] = st.session_state.knowledge_base
    save_user_data_db(user_email, st.session_state.user_data)

if st.session_state.knowledge_base:
    st.session_state.embeddings = embed_model.encode(st.session_state.knowledge_base, convert_to_tensor=True)

def retrieve_context(query):
    if "embeddings" not in st.session_state: return ""
    query_emb = embed_model.encode(query, convert_to_tensor=True)
    hits = util.semantic_search(query_emb, st.session_state.embeddings, top_k=3)
    return "\n\n".join([st.session_state.knowledge_base[hit['corpus_id']] for hit in hits[0]])

def detect_language(text):
    try: return detect(text)
    except: return "en"

# --- 7. MAIN CHAT ---
st.markdown("<h1 style='text-align: center;'>🚀 AI Assistant Pro</h1>", unsafe_allow_html=True)

# --- Professional Quick-Start Interface ---
if not st.session_state.current_session_id:
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    # Using 5 columns centers the button perfectly on both Mobile and Desktop
    col1, col2, col3, col4, col5 = st.columns([1, 1, 3, 1, 1])
    
    with col3:
        st.markdown("<p style='text-align: center; color: #94a3b8;'>Ready to begin?</p>", unsafe_allow_html=True)
        if st.button("✨ Start New Project", use_container_width=True):
            # Create unique session ID
            new_id = str(len(st.session_state.user_data["sessions"]) + 1)
            st.session_state.current_session_id = new_id
            st.session_state.messages = []
            
            st.session_state.user_data["sessions"][new_id] = {
                "title": "New Chat",
                "messages": []
            }
            
            # Save and Refresh
            save_user_data_db(user_email, st.session_state.user_data)
            st.rerun()
            
    st.stop()


if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask something..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    if is_image_request(prompt):
        with st.chat_message("assistant"):
            with st.spinner("🎨 Creating your image..."):
                final_url = generate_and_save_image(prompt, img_size, img_quality)
                if final_url:
                    res_text = f"**Generated Image:**\n![Gen]({final_url})"
                    st.markdown(res_text)
                    st.session_state.messages.append({"role": "assistant", "content": res_text})
    else:
        with st.chat_message("assistant"):
            context = retrieve_context(prompt)
            
            # LANGUAGE LOGIC
            if selected_lang_name == "Auto":
                detected_lang = detect_language(prompt)
                lang_instr = f" Respond in the same language as the user (language code: {detected_lang})."
            else:
                lang_instr = f" Respond ONLY in {selected_lang_name}."

            full_messages = [{"role": "system", "content": system_role + lang_instr}]
            if context:
                full_messages.append({"role": "system", "content": f"Context:\n{context}"})
            full_messages += st.session_state.messages

            completion = client.chat.completions.create(
                model=model_name, messages=full_messages, max_tokens=max_tokens, temperature=temperature
            )
            response = completion.choices[0].message.content
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

    # SAVE CHAT
    current_sess = st.session_state.user_data["sessions"][st.session_state.current_session_id]
    current_sess["messages"] = st.session_state.messages
    if current_sess["title"] == "New Chat":
        current_sess["title"] = prompt[:30] + "..."
    save_user_data_db(user_email, st.session_state.user_data)
    st.rerun()
