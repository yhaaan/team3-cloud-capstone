# Module B

Module B는 Module A가 정제한 문서를 입력받아 다음 산출물을 만든다.

- Chroma 적재용 청크
- 그래프 JSON
- Neo4j 적재용 Cypher

## 입력 형식

다음 필드를 포함한 `json` 또는 `jsonl` 문서를 지원한다.

```json
{
  "source_id": "news_001",
  "title": "카카오, A사 인수 발표",
  "content": "카카오는 2026년 3월 20일 A사 인수를 발표했다.",
  "source": "mock_news",
  "published_at": "2026-03-20",
  "url": "https://example.com/news/001"
}
```

## 실행

샘플 JSON 디렉터리 기준 실행:

```powershell
.\.venv\Scripts\python.exe services\module-b\src\run_pipeline.py
```

JSONL 입력 기준 실행:

```powershell
.\.venv\Scripts\python.exe services\module-b\src\run_pipeline.py --input services\module-b\tests\sample_news_batch.jsonl
```

규칙 기반 추출:

```powershell
.\.venv\Scripts\python.exe services\module-b\src\run_pipeline.py --extractor rule
```

OpenAI 기반 추출:

```powershell
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="gpt-4.1-mini"
.\.venv\Scripts\python.exe services\module-b\src\run_pipeline.py --extractor openai --skip-chroma
```

Neo4j 실적재:

```powershell
$env:NEO4J_URI="bolt://localhost:7687"
$env:NEO4J_USER="neo4j"
$env:NEO4J_PASSWORD="password"
.\.venv\Scripts\python.exe services\module-b\src\load_neo4j.py --input services\module-b\outputs
```

Cypher 파일만 생성:

```powershell
.\.venv\Scripts\python.exe services\module-b\src\load_neo4j.py --input services\module-b\outputs --export-only
```

## 산출물 위치

- 그래프 JSON: `services/module-b/outputs/*_graph.json`
- Neo4j Cypher: `services/module-b/outputs/*_graph.cypher.txt`
- Chroma 로컬 DB: `services/module-b/local_db/chroma`

## 테스트

```powershell
.\.venv\Scripts\python.exe -m unittest services\module-b\tests\test_module_b.py
```
