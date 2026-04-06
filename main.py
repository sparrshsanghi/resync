from fastapi import FastAPI
from groq import Groq
import numpy as np
import json
import re
import os

app = FastAPI()

# -------- Documents --------
documents = [
    "In this video we explain arrays and time complexity with examples...",
    "This lecture covers binary trees, traversal techniques and recursion...",
    "Graph algorithms like BFS and DFS are essential for interviews...",
]

# -------- Lazy Model Loader --------
model = None

def get_model():
    global model
    if model is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('all-MiniLM-L6-v2')
    return model

# -------- Recommendation --------
def recommend(goal):
    model = get_model()

    # Encode
    doc_embeddings = model.encode(documents)
    query_embedding = model.encode([goal])

    # Simple similarity (NO FAISS)
    similarities = np.dot(doc_embeddings, query_embedding.T).flatten()

    # Top 3
    top_indices = similarities.argsort()[-3:][::-1]
    retrieved = [documents[i] for i in top_indices]

    # Groq client (lazy)
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"error": "API key missing"}

    client = Groq(api_key=api_key)

    # Prompt
    prompt = f"""
User goal: {goal}

Relevant learning content:
{retrieved}

Return ONLY valid JSON:

{{
  "recommended_topics": ["topic1", "topic2", "topic3"],
  "reason": ["why1", "why2", "why3"],
  "roadmap": ["step1", "step2", "step3"]
}}
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}]
    )

    output = response.choices[0].message.content

    cleaned = re.sub(r"```json|```", "", output).strip()

    try:
        return json.loads(cleaned)
    except:
        return {
            "recommended_topics": ["Basics"],
            "reason": ["Fallback"],
            "roadmap": ["Start simple"]
        }

# -------- API --------
@app.post("/recommend")
def recommend_api(data: dict):
    return recommend(data["goal"])

@app.get("/")
def home():
    return {"message": "Resync AI running 🚀"}