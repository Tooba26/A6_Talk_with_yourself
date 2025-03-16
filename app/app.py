from flask import Flask, request, jsonify, render_template
import fitz  # PyMuPDF for PDF extraction
import requests
from bs4 import BeautifulSoup
from langchain.vectorstores import FAISS
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document  # Correct import for Document structure
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
import os

# Initialize Flask App
app = Flask(__name__)

# 📌 **Step 1: Extract Text from CV & Portfolio**
def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF document."""
    text = ""
    doc = fitz.open(pdf_path)
    for page in doc:
        text += page.get_text() + "\n"
    return text.strip()

def extract_text_from_website(url):
    """Extract text from a website."""
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    return soup.get_text()

# Load Data
cv_text = extract_text_from_pdf("CV.pdf") 
portfolio_text = extract_text_from_website("https://tooba-portfolio.vercel.app/")

# 📌 **Step 2: Store Data in FAISS Retriever with Metadata**
embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# Ensure documents have metadata
cv_doc = Document(page_content=cv_text, metadata={"source": "CV.pdf"})
portfolio_doc = Document(page_content=portfolio_text, metadata={"source": "Portfolio Website"})

# Create FAISS Vector Database
vector_db = FAISS.from_documents([cv_doc, portfolio_doc], embedding_model)
vector_db.save_local("faiss_index")

# Load FAISS Retriever
retriever = FAISS.load_local("faiss_index", embedding_model, allow_dangerous_deserialization=True).as_retriever()

# 📌 **Step 3: Load FLAN-T5 for Answer Generation**
model_id = "google/flan-t5-large"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForSeq2SeqLM.from_pretrained(model_id)

def generate_answer(query, context):
    """Generate answer using FLAN-T5 model."""
    input_text = f"Question: {query} Context: {context} Answer:"
    inputs = tokenizer(input_text, return_tensors="pt")
    output = model.generate(**inputs, max_length=100)
    return tokenizer.decode(output[0], skip_special_tokens=True)

# 📌 **Step 4: Chatbot Logic with Source Documents**
def rag_chatbot(query):
    """Retrieve relevant context and generate response along with sources."""
    retrieved_docs = retriever.get_relevant_documents(query)
    
    if not retrieved_docs:
        return {"response": "Sorry, I couldn't find relevant information.", "sources": []}

    # Extract relevant context and sources
    context = " ".join([doc.page_content for doc in retrieved_docs])

    # Extract sources properly
    sources = list(set([doc.metadata.get("source", "Unknown Source") for doc in retrieved_docs]))

    # Generate model response
    response = generate_answer(query, context)

    return {"response": response, "sources": sources}

# 📌 **Step 5: Create Flask Routes**
@app.route("/")
def home():
    """Render the chat UI."""
    return render_template("index.html")

@app.route("/chat", methods=["POST", "GET"])
def chat():
    """Handle chatbot queries."""
    data = request.json
    query = data.get("message", "")

    if not query:
        return jsonify({"response": "Please enter a valid question.", "sources": []})

    result = rag_chatbot(query)
    return jsonify(result)

# 📌 **Step 6: Run Flask App**
if __name__ == "__main__":
    app.run(debug=True)
