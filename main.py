from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from groq import Groq
import json
import re
import os

# 1. Load embedding model
model = SentenceTransformer('all-MiniLM-L6-v2')

# 2. Sample transcripts (replace later with real data)
documents = [
    "In this video we explain arrays and time complexity with examples...",
    "This lecture covers binary trees, traversal techniques and recursion...",
    "Graph algorithms like BFS and DFS are essential for interviews...",
]

# 3. Convert to embeddings
doc_embeddings = model.encode(documents)

# 4. Store in FAISS
dimension = doc_embeddings.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(np.array(doc_embeddings))

# 5. Groq setup (put your API key)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def recommend(goal):
    # Convert query to embedding
    query_embedding = model.encode([goal])

    # Search top 3
    distances, indices = index.search(np.array(query_embedding), k=3)

    retrieved = [documents[i] for i in indices[0]]

    # Send to LLM
    prompt = f"""
User goal: {goal}

Relevant learning content:
{retrieved}

You are an AI learning assistant.

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

    # clean markdown
    cleaned = re.sub(r"```json|```", "", output).strip()

    try:
        parsed = json.loads(cleaned)
        return parsed
    except:
        return {
            "recommended_topics": ["Basics"],
            "reason": ["Fallback"],
            "roadmap": ["Start simple"]
        }


# Run test
if __name__ == "__main__":
    goal = input("Enter your goal: ")
    result = recommend(goal)
    print("\nResult:\n", result)

from fastapi import FastAPI

app = FastAPI()

@app.post("/recommend")
def recommend_api(data: dict):
    return recommend(data["goal"])


import os

port = int(os.environ.get("PORT", 8000))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)