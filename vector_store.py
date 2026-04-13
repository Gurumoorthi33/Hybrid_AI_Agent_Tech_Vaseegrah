from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import os
import pickle

model = SentenceTransformer("all-MiniLM-L6-v2")

INDEX_FILE = "faiss_index.bin"
DOCS_FILE = "docs.pkl"

class VectorStore:
    def __init__(self):
        self.index = None
        self.docs = []

        if os.path.exists(INDEX_FILE):
            self.index = faiss.read_index(INDEX_FILE)
            self.docs = pickle.load(open(DOCS_FILE, "rb"))

    def add_documents(self, texts):
        embeddings = model.encode(texts)

        if self.index is None:
            self.index = faiss.IndexFlatL2(len(embeddings[0]))

        self.index.add(np.array(embeddings))
        self.docs.extend(texts)

        faiss.write_index(self.index, INDEX_FILE)
        pickle.dump(self.docs, open(DOCS_FILE, "wb"))

    def search(self, query, k=3):
        if self.index is None:
            return []

        q_vec = model.encode([query])
        distances, indices = self.index.search(np.array(q_vec), k)

        return [self.docs[i] for i in indices[0]]