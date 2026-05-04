# Module B

Module B reads cleaned Module A documents and creates:

- Chroma chunks with OpenAI `text-embedding-3-small` embeddings
- graph JSON files
- Neo4j Cypher files or direct Neo4j inserts

## Module A Input

The default input directory is `services/module-a/data`.
`run_pipeline.py` recursively loads:

- news JSONL files such as `company_news_cleaned.jsonl`
- DART JSON files under each company's `dart` directory

Module A news fields are mapped to Module B's document contract:

- `doc_id` -> `source_id`
- `body_text` or `sentences` -> `content`
- `originallink` or `naver_link` -> `url`

Module A DART files use `text_blocks` as content. If `text_blocks` is empty, Module B falls back to `normalized_records`.

The common document schema is defined in `schemas/input_document_schema.json`.
Required common fields:

- `source_id`
- `document_type`: `news`, `dart`, or `unknown`
- `title`
- `content`
- `source`
- `published_at`
- `url`
- `metadata`

Source-specific Module A details are preserved in `metadata` so Module C can use them when it needs richer context.

## Run

Run with Module A data:

```powershell
.\.venv\Scripts\python.exe services\module-b\src\run_pipeline.py --skip-chroma
```

OpenAI extraction is the default graph extraction mode. Set these before graph extraction:

```powershell
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="gpt-4.1-mini"
$env:OPENAI_EMBEDDING_MODEL="text-embedding-3-small"
```

Graph extraction and Neo4j loading only run for documents with `relation_relevance_score >= 0.6`.
Override this threshold when needed:

```powershell
.\.venv\Scripts\python.exe services\module-b\src\run_to_neo4j.py --min-relation-score 0.7
```

Rule-based extraction is still available for local fallback or cost-saving runs:

```powershell
.\.venv\Scripts\python.exe services\module-b\src\run_pipeline.py --extractor rule --skip-chroma
```

Load graph outputs into Neo4j:

```powershell
$env:NEO4J_URI="neo4j+s://your-instance.databases.neo4j.io"
$env:NEO4J_USER="neo4j"
$env:NEO4J_PASSWORD="your_aura_password"
.\.venv\Scripts\python.exe services\module-b\src\load_neo4j.py --input services\module-b\outputs
```

Run Module B and load directly into Neo4j in one command:

```powershell
.\.venv\Scripts\python.exe services\module-b\src\run_to_neo4j.py
```

This command uses OpenAI for graph extraction by default and also inserts chunks into Chroma by default.
Chroma uses OpenAI `text-embedding-3-small` by default.
Skip Chroma when needed:

```powershell
.\.venv\Scripts\python.exe services\module-b\src\run_to_neo4j.py --skip-chroma
```

Rebuild only Chroma without touching Neo4j:

```powershell
.\.venv\Scripts\python.exe services\module-b\src\run_to_neo4j.py --chroma-only
```

Smoke test with one Module A document:

```powershell
.\.venv\Scripts\python.exe services\module-b\src\run_to_neo4j.py --limit 1
```

Generate Cypher files only:

```powershell
.\.venv\Scripts\python.exe services\module-b\src\load_neo4j.py --input services\module-b\outputs --export-only
```

## Outputs

- Graph JSON: `services/module-b/outputs/*_graph.json`
- Neo4j Cypher: `services/module-b/outputs/*_graph.cypher.txt`
- Chroma local DB: `services/module-b/local_db/chroma`

Person roles are normalized before graph JSON, Cypher export, and Neo4j loading:

- `role`: query-safe standard code such as `CHAIRMAN`, `CEO`, `PRESIDENT`, `DIRECTOR`
- `role_label`: Korean display label such as `회장`, `대표이사`, `사장`, `이사`
- `role_raw`: original extracted title text such as `삼성전자 회장`, `대표이사 사장`

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest services\module-b\tests\test_module_b.py
```

## Team AuraDB

Module B uses AuraDB as the shared team graph database.
Create one AuraDB instance from Neo4j Aura, then put its connection values in `.env`:

```env
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_aura_password
```

Load existing Module B graph outputs into AuraDB once:

```powershell
py -3 services\module-b\src\load_neo4j.py --input services\module-b\outputs
```

After that, teammates do not need to run `run_to_neo4j.py` for graph data.
They can use the same AuraDB URI, user, and password to browse/query the shared graph.

## Environment Files

`.env` is intentionally ignored by git because it can contain private OpenAI API keys.
Commit `.env.example` instead, then each teammate should copy it:

```powershell
Copy-Item .env.example .env
```

Then fill in `OPENAI_API_KEY`.
