import streamlit as st
 st.set_page_config(
    page_title="AI Assistant Pro",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)
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

st.markdown("""
<style>

/* Hide Streamlit default UI */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* Background */
.stApp {
    background: linear-gradient(135deg, #0f172a, #020617);
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #020617;
}

/* Buttons */
.stButton>button {
    background: linear-gradient(135deg, #6366F1, #8B5CF6);
    color: white;
    border-radius: 12px;
    border: none;
}

/* Chat bubbles */
[data-testid="stChatMessage"] {
    background: #020617;
    border: 1px solid #1e293b;
    border-radius: 14px;
    padding: 10px;
}

</style>
""", unsafe_allow_html=True)
# --- 1. SUPABASE INIT ---
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- 2. DATABASE FUNCTIONS ---
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

# NEW: Upload function for your secure bucket
def upload_to_supabase(uploaded_file):
    def generate_and_save_image(prompt, size, quality):
    try:
        # Uses the same OpenAI client as your text chat
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality=quality,
            n=1
        )
        temp_url = response.data.url
        
        # Download image to save permanently in YOUR bucket
        import requests
        img_data = requests.get(temp_url).content
        
        user_id = st.session_state.user.id
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{user_id}/gen_{timestamp}.png"

        # Upload to 
         so it shows in formal chats later
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

    # 1. Get the current user's ID
    user_id = st.session_state.user.id
    
    # 2. Create a unique filename with a timestamp 
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # Matches the (storage.foldername(name)) = auth.uid() rule you just saved!
    unique_path = f"{user_id}/{timestamp}_{uploaded_file.name}"
    
    try:
        # 3. Upload the file bytes
        file_bytes = uploaded_file.getvalue()
        supabase.storage.from_('generated-images').upload(
            path=unique_path,
            file=file_bytes,
            file_options={"content-type": uploaded_file.type}
        )
        # 4. Get the URL to show in your chat
        return supabase.storage.from_('generated-images').get_public_url(unique_path)
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None


# --- 3. AUTH SYSTEM ---
def auth_ui():
    st.title("🔐 AI Login / Signup")

    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    # LOGIN
    with tab1:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_pass")

        if st.button("Login"):
            try:
                res = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })

                st.session_state.user = res.user
                st.session_state.logged_in = True

                # LOAD USER DATA
                data = load_user_data_db(res.user.email)
                st.session_state.user_data = data
                st.session_state.knowledge_base = data.get("knowledge_base", [])
                st.session_state.messages = []
                st.session_state.current_session_id = None

                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    # SIGNUP
    with tab2:
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Password", type="password", key="signup_pass")

        if st.button("Sign Up"):
            try:
                supabase.auth.sign_up({
                    "email": email,
                    "password": password
                })
                st.success("Account created! You can now log in.")
            except Exception as e:
                st.error(f"Signup failed: {e}")

# --- 4. AUTH CHECK ---
if "logged_in" not in st.session_state or not st.session_state.logged_in:
    auth_ui()
    st.stop()

# --- 5. USER IDENTIFICATION ---
user_email = st.session_state.user.email

# --- 6. OPENAI CLIENT ---
client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=st.secrets["GITHUB_TOKEN"]
)
model_name = st.secrets.get("MODEL_NAME", "gpt-4-32k")

# --- 7. EMBEDDING MODEL ---
@st.cache_resource
def get_embed_model():
    return SentenceTransformer('all-MiniLM-L6-v2')

embed_model = get_embed_model()

# --- 8. SIDEBAR ---
st.sidebar.markdown("""
<h2 style='text-align:center;'>🤖 AI Dashboard</h2>
<p style='text-align:center; font-size:12px;'>Powered by AI</p>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")

st.sidebar.markdown(f"👤 **{user_email}**")

# LOGOUT
if st.sidebar.button("🚪 Logout"):
    st.session_state.clear()
    st.rerun()

# NEW PROJECT
if st.sidebar.button("➕ New Project", use_container_width=True):
    new_id = str(len(st.session_state.user_data["sessions"]) + 1)
    st.session_state.current_session_id = new_id
    st.session_state.messages = []

    st.session_state.user_data["sessions"][new_id] = {
        "title": "New Chat",
        "messages": []
    }

    save_user_data_db(user_email, st.session_state.user_data)
    st.rerun()

# CHAT HISTORY
st.sidebar.subheader("Recent Projects")
for sess_id, sess_info in list(st.session_state.user_data["sessions"].items()):
    if st.sidebar.button(sess_info["title"], key=sess_id, use_container_width=True):
        st.session_state.current_session_id = sess_id
        st.session_state.messages = sess_info["messages"]
        st.rerun()

# SETTINGS
system_role = st.sidebar.text_area("AI Persona", "You are a helpful AI assistant.")
max_tokens = st.sidebar.slider("Max Tokens", 50, 2000, 500)
temperature = st.sidebar.slider("Temperature", 0.0, 1.0, 0.7)
st.sidebar.markdown("---")
st.sidebar.subheader("🎨 Image Settings")
# DALL-E 3 supports these specific sizes
img_size = st.sidebar.selectbox("Image Size", ["1024x1024", "1024x1792", "1792x1024"])
img_quality = st.sidebar.select_slider("Quality", options=["standard", "hd"])
# Note: DALL-E 3 currently only supports 1 image per request
img_num = st.sidebar.number_input("Number of Images", min_value=1, max_value=1, value=1)

# FILE UPLOAD
uploaded_files = st.sidebar.file_uploader(
    "Upload Files", accept_multiple_files=True, type=["pdf", "txt", "docx"]
)

# --- 9. FILE PROCESSING ---
def process_files(files):
    chunks = []
    for file in files:
        ext = file.name.split(".")[-1].lower()

        if ext == "pdf":
            pdf = PdfReader(file)
            for page in pdf.pages:
                chunks.append(page.extract_text())

        elif ext == "txt":
            chunks.append(file.read().decode("utf-8"))

        elif ext == "docx":
            doc = Document(file)
            for p in doc.paragraphs:
                chunks.append(p.text)

    return [c.strip() for c in chunks if c]

if uploaded_files:
    for file in uploaded_files:
        # 1. Save the file to your secure Supabase Bucket
        file_url = upload_to_supabase(file)
        
        if file_url:
            st.sidebar.info(f"Uploaded: {file.name}")
            # You can now save this 'file_url' to the user's history!
    
    # 2. Process for RLS/Knowledge base (your existing code)
    new_chunks = process_files(uploaded_files)
    st.session_state.knowledge_base.extend(new_chunks)
    st.session_state.user_data["knowledge_base"] = st.session_state.knowledge_base
    save_user_data_db(user_email, st.session_state.user_data)

# --- 10. EMBEDDINGS ---
if st.session_state.knowledge_base:
    st.session_state.embeddings = embed_model.encode(
        st.session_state.knowledge_base, convert_to_tensor=True
    )

def retrieve_context(query):
    if "embeddings" not in st.session_state:
        return ""

    query_emb = embed_model.encode(query, convert_to_tensor=True)
    hits = util.semantic_search(query_emb, st.session_state.embeddings, top_k=3)

    return "\n\n".join([
        st.session_state.knowledge_base[hit['corpus_id']]
        for hit in hits[0]
    ])

# --- 11. TOKEN COUNT ---
def num_tokens(messages):
    encoding = tiktoken.get_encoding("cl100k_base")
    return sum(len(encoding.encode(m["content"])) for m in messages)

# --- 12. MAIN CHAT ---
st.markdown("""
<h1 style='text-align: center;'>🚀 AI Assistant Pro</h1>
<p style='text-align: center; color: gray;'>
Smart AI powered by your documents
</p>
""", unsafe_allow_html=True)

if not st.session_state.current_session_id:
    st.info("👈 Start a new project from the sidebar to begin.")
    st.stop()
    
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask something or 'Generate an image of...'"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # --- IMAGE LOGIC ---
    if is_image_request(prompt):
        with st.chat_message("assistant"):
            with st.spinner("🎨 Creating your image..."):
                final_url = generate_and_save_image(prompt, img_size, img_quality)
                if final_url:
                    response_text = f"**Generated Image:**\n![Gen]({final_url})"
                    st.markdown(response_text)
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                else:
                    st.error("Could not generate image.")

    # --- TEXT LOGIC ---
    else:
        with st.chat_message("assistant"):
            context = retrieve_context(prompt)
            full_messages = [{"role": "system", "content": system_role}]
            if context:
                full_messages.append({"role": "system", "content": f"Context:\n{context}"})
            full_messages += st.session_state.messages

            completion = client.chat.completions.create(
                model=model_name,
                messages=full_messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            response = completion.choices[0].message.content
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

    # --- SAVE & PERSIST ---
    current_sess = st.session_state.user_data["sessions"][st.session_state.current_session_id]
    current_sess["messages"] = st.session_state.messages
    
    if current_sess["title"] == "New Chat":
        current_sess["title"] = prompt[:30] + "..."
        
    save_user_data_db(user_email, st.session_state.user_data)
    st.rerun()
