import chromadb

# 지정된 경로로 클라이언트 생성

# 1. ChromaDB 클라이언트 설정 (경로는 본인 설정에 맞게)
client = chromadb.PersistentClient(path="services/module-b/local_db/chroma")

# 2. 컬렉션 가져오기
collection = client.get_collection(name="module_b_chunks")

# 3. 딱 5개만 뽑아서 메타데이터와 내용 확인하기
results = collection.peek(limit=5)

print("--- [Metadata 확인] ---")
for meta in results['metadatas']:
    print(meta)

print("\n--- [Document 내용 확인] ---")
for doc in results['documents']:
    print(doc) # 너무 기니까 앞부분만