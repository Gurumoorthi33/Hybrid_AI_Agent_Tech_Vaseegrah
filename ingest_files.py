import os
from vector_store import VectorStore
from pypdf import PdfReader

vs = VectorStore()

def read_pdf(path):
    reader = PdfReader(path)
    return "\n".join([p.extract_text() for p in reader.pages])

def load_files():
    texts = []

    if not os.path.exists("data"):
        print("No data folder → skipping file ingestion")
        return

    for file in os.listdir("data"):
        path = os.path.join("data", file)

        if file.endswith(".pdf"):
            texts.append(read_pdf(path))
        elif file.endswith(".txt"):
            with open(path) as f:
                texts.append(f.read())

    if texts:
        vs.add_documents(texts)
        print("Files embedded into vector DB ✅")
    else:
        print("No files found")

if __name__ == "__main__":
    load_files()