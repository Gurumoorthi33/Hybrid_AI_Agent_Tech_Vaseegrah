import numpy as np

def simple_embedding(text):
    return np.array([hash(word) % 1000 for word in text.split()[:100]])

def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)