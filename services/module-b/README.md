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
$env:NEO4J_URI="bolt://localhost:7687"
$env:NEO4J_USER="neo4j"
$env:NEO4J_PASSWORD="password"
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

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest services\module-b\tests\test_module_b.py
```

## Team Local Neo4j

Install Docker Desktop manually first, then start Docker Desktop.
After Docker Desktop is running, run this from the repository root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File infra\setup-local.ps1
```

The script checks that Docker is available, installs Python dependencies, prepares `.env` from `.env.example`, and starts the Neo4j container with Docker Compose.

If Python dependencies are already installed:

```powershell
powershell -ExecutionPolicy Bypass -File infra\setup-local.ps1 -SkipPythonInstall
```

Run Neo4j locally for Module B:

```powershell
docker compose -f infra/docker-compose.yml up -d
```

Neo4j Browser:

```text
http://localhost:7474
```

Default local credentials:

```text
user: neo4j
password: password
bolt uri: bolt://localhost:7687
```

## Environment Files

`.env` is intentionally ignored by git because it can contain private OpenAI API keys.
Commit `.env.example` instead, then each teammate should copy it:

```powershell
Copy-Item .env.example .env
```

Then fill in `OPENAI_API_KEY`.
