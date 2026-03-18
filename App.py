import streamlit as st
from openai import OpenAI
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
from PyPDF2 import PdfReader
from docx import Document
import os
import tiktoken  # New dependency for token calculation

# --- 1. Security & Password Check ---
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Enter Password to Unlock AI", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Enter Password to Unlock AI", type="password", on_change=password_entered, key="password")
        st.error("😕 Password incorrect")
        return False
    return True

if not check_password():
    st.stop()

# --- 2. Client Setup ---
try:
    client = OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=st.secrets["GITHUB_TOKEN"]
    )
    model_name = st.secrets.get("MODEL_NAME","gpt-4-32k")  # Updated to use GPT-4 with 32k context size
except Exception as e:
    st.error(f"⚠️ API Configuration error: {e}")
    st.stop()

# --- 3. Sidebar and File Uploader ---
st.sidebar.header("Settings")
st.sidebar.subheader("Knowledge Base")

uploaded_files = st.sidebar.file_uploader("Upload Files (PDF, TXT, DOCX)", accept_multiple_files=True, type=["pdf", "txt", "docx"])
system_role = st.sidebar.text_area("AI Role (Persona):", "You are an AI assistant optimized for domain-specific Q&A.")
max_tokens = st.sidebar.slider("Response Length", 50, 2000, 500)
temperature = st.sidebar.slider("Creativity (Temperature)", 0.0, 1.0, 0.7)

# --- 4. Document Processor ---
def process_uploaded_files(files):
    chunks = []
    for file in files:
        extension = file.name.split(".")[-1].lower()

        if extension == "pdf":
            pdf_reader = PdfReader(file)
            for page in pdf_reader.pages:
                text = page.extract_text()
                chunks.extend(text.split("\n\n"))  # Use paragraphs as chunks

        elif extension == "txt":
            text = file.read().decode("utf-8")
            chunks.extend(text.split("\n\n"))  # Use paragraphs as chunks

        elif extension == "docx":
            doc = Document(file)
            for para in doc.paragraphs:
                chunks.append(para.text)

    return chunks

if "knowledge_base" not in st.session_state:
    st.session_state.knowledge_base = []
    st.session_state.vectorizer = None
    st.session_state.nbrs = None

# Process uploaded files and update the knowledge base
if uploaded_files:
    st.session_state.knowledge_base = process_uploaded_files(uploaded_files)
    st.success(f"Loaded {len(st.session_state.knowledge_base)} chunks into the knowledge base.")

    # Transform uploaded content to embeddings using TF-IDF
    st.session_state.vectorizer = TfidfVectorizer().fit(st.session_state.knowledge_base)
    vectors = st.session_state.vectorizer.transform(st.session_state.knowledge_base)
    st.session_state.nbrs = NearestNeighbors(n_neighbors=5, metric="cosine").fit(vectors)

# --- 5. Token Calculation ---
def num_tokens_from_messages(messages, model="gpt-4-32k"):
    """Calculate the number of tokens used by a list of messages."""
    encoding = tiktoken.encoding_for_model(model)
    num_tokens = 0
    for message in messages:
        num_tokens += 4  # Every message has {role/name}\n{content}\n tokens
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
    num_tokens += 2  # Every reply is primed with <im_start>
    return num_tokens

# --- 6. Context Augmentation and Truncation ---
st.title("🤖 RAG + GPT-4-32k")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

def retrieve_context(query):
    if not st.session_state.nbrs or not st.session_state.knowledge_base:
        return None

    # Embed the query and retrieve similar chunks
    queàry_vector = st.session_state.vectorizer.transform([query])
    distances, indices = st.session_state.nbrs.kneighbors(query_vector)
    return "\n\n".join([st.session_state.knowledge_base[i] for i in indices[0]])

# Allow the user to send inputs
if prompt := st.chat_input("Ask anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        # Retrieve context from the knowledge base
        context = retrieve_context(prompt)
        context_message = f"Context: {context}" if context else "No relevant document context found."

        # Prepare the full context: system role + RAG context + chat history + user input
        full_context = [{"role": "system", "content": system_role}]
        if context:
            full_context.append({"role": "system", "content": f"Context: {context}"})
        full_context.extend(st.session_state.messages)

        # Manage tokens: truncate chat history if necessary
        max_allowed_tokens = 32000  # Max context length for GPT-4-32k
        buffer_tokens = 2000        # Reserve space for the model's reply
        while num_tokens_from_messages(full_context) > (max_allowed_tokens - buffer_tokens):
            # Remove the oldest user/assistant message in the conversation history
            del full_context[2]  # Keep system instructions + RAG context at the top

        # Display token usage in the sidebar
        token_usage = num_tokens_from_messages(full_context)
        st.sidebar.write(f"🧮 Token Usage: {token_usage}/{max_allowed_tokens - buffer_tokens}")

        # Generate AI response
        completion = client.chat.completions.create(
            model=model_name,
            messages=full_context,
            max_tokens=max_tokens,
            temperature=temperature
        )
        response = completion.choices[0].message.content

        # Process and display the response
        with st.chat_message("assistant"):
            st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})

    except Exception as e:
        st.error(f"Error generating response: {e}")
