# Module B DB ER Diagram

Module B stores data in two different databases:

- ChromaDB: document chunks for vector retrieval
- Neo4j: entities and relationships for graph retrieval

Strictly speaking, the Neo4j side is a property graph rather than a classic RDB ER model. The diagram below is an ER-style logical model based on the code and schemas in this repository.

## 1. ChromaDB logical ER

This section starts from the input document schema that Module B receives from Module A.

```mermaid
erDiagram
    INPUT_DOCUMENT ||--o{ CHUNK : splits_into

    INPUT_DOCUMENT {
        string source_id PK
        string title
        string content
        string source
        string published_at
        string url
    }

    CHUNK {
        string chunk_id PK
        string doc_id FK
        string text
        int chunk_index
        string title
        string source
        string published_at
        string url
        string company_hint
    }
```

Notes:

- `INPUT_DOCUMENT` is the input JSON schema passed from Module A to Module B.
- `INPUT_DOCUMENT` itself is not persisted as a separate DB table or collection in the current implementation.
- `CHUNK` is the logical record inserted into the Chroma collection `module_b_chunks`.
- `company_hint` is a search-assist metadata field. It is generated as a list in code, then stored as a comma-joined string in Chroma metadata.

## 2. Neo4j logical ER

This version is simplified for Notion Mermaid compatibility. It models only direct entity-to-entity relationships.

```mermaid
erDiagram
    ENTITY_COMPANY {
        string id
        string type
        string name
        string stock_code
        string country
        string industry
    }

    ENTITY_PERSON {
        string id
        string type
        string name
        string role
        string affiliated_company
    }

    ENTITY_EVENT {
        string id
        string type
        string name
        string event_type
        string date
        string description
    }

    ENTITY_INDUSTRY {
        string id
        string type
        string name
        string description
    }

    ENTITY_COMPANY ||--o{ ENTITY_COMPANY : acquires
    ENTITY_COMPANY ||--o{ ENTITY_COMPANY : invests_in
    ENTITY_PERSON ||--o{ ENTITY_COMPANY : appointed_to
    ENTITY_PERSON ||--o{ ENTITY_COMPANY : affiliated_with
    ENTITY_COMPANY }o--|| ENTITY_INDUSTRY : belongs_to
```

## 3. Actual graph interpretation in Neo4j

Internally, Module B loads Neo4j with:

- one shared base label: `Entity`
- one subtype label: `Company`, `Person`, `Event`, or `Industry`
- typed relationships:
  - `ACQUIRES`
  - `INVESTS_IN`
  - `APPOINTED_TO`
  - `AFFILIATED_WITH`
  - `BELONGS_TO`

Equivalent graph view:

```mermaid
flowchart LR
    Company[Entity:Company]
    Person[Entity:Person]
    Event[Entity:Event]
    Industry[Entity:Industry]

    Company -- ACQUIRES --> Company
    Company -- INVESTS_IN --> Company
    Person -- APPOINTED_TO --> Company
    Person -- AFFILIATED_WITH --> Company
    Company -- BELONGS_TO --> Industry
```

## 4. Implementation-based field summary

Input document fields:

- `source_id`
- `title`
- `content`
- `source`
- `published_at`
- `url`

Chroma chunk fields:

- `chunk_id`
- `doc_id`
- `text`
- `title`
- `source`
- `published_at`
- `url`
- `chunk_index`
- `company_hint`

Neo4j entity fields:

- common: `id`, `type`, `name`
- company: `stock_code`, `country`, `industry`
- person: `role`, `affiliated_company`
- event: `event_type`, `date`, `description`
- industry: `description`

Neo4j relation fields:

- `type`
- `from`
- `to`
- `evidence`

## 5. Design note

`source_id` exists in the graph JSON root, but the current Neo4j loader does not persist document-to-entity or document-to-relation provenance as a separate node/table. If you want, I can extend this into a v2 ERD that adds `Document`, `Chunk`, `Entity`, and `RelationEvidence` linkage for traceability.
