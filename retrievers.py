from vector_store import VectorStore
from mongo import query_mongo

vs = VectorStore()

def retrieve_files(query):
    return vs.search(query)

def retrieve_mongodb(query):
    return query_mongo(query)