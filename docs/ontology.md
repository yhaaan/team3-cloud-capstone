# Module B Ontology

## Purpose

Module B extracts a compact graph from financial and company documents for Graph RAG.
The graph should prioritize relations that help users discover listed companies from
industry, product, service, investment, acquisition, executive, or event
questions.

The ontology is intentionally small. Extract only entities and relations supported by
source text. Do not infer facts that are not evidenced by the input document.

## Entity Types

### Company

A listed company allowed by Module B's whitelist.

Required fields:
- id
- type
- name

Optional fields:
- stock_code
- country
- industry
- description

Rules:
- Create Company entities only for companies in the allowed listed-company set supplied in the prompt.
- The whitelist already excludes rows without corp_code, but corp_code is not a graph field.
- Use stock_code as the stable listed-company identifier when available.
- Do not create Company nodes for unlisted companies, subsidiaries, public agencies, institutions, or foreign companies unless they are explicitly in the allowed set.

Examples:
- Samsung Electronics
- SK hynix
- Hyundai Motor

### Person

A person connected to a company or event.

Required fields:
- id
- type
- name

Optional fields:
- birth_ym
- gender
- main_career

Rules:
- Create Person entities only from DART executive_status documents.
- Do not create Person entities from news documents or non-executive DART documents.
- Put only the person's name in name.
- Put source title, board role, responsibility, tenure, and company-specific role text on the Person -> Company relation, not the Person entity.
- Do not merge company names or title phrases into Person.name.
- For DART executive_status records, use name plus birth_ym as the stable person identity when birth_ym is available.
- Preserve main_career as source-backed career text for later human-network analysis.

Examples:
- Lee Jae-yong
- Jensen Huang

### Event

A business or financial event worth representing as its own entity.

Required fields:
- id
- type
- name

Optional fields:
- event_type
- date
- description

Examples:
- acquisition announcement
- executive appointment
- business restructuring

### Industry

A sector, market, thematic category, business line, or operating area. Industry
can be broad or narrow; use `PART_OF` to connect narrower Industry nodes to
broader Industry nodes when hierarchy is useful.

Required fields:
- id
- type
- name

Optional fields:
- description

Rules:
- Use Industry for both broad categories and narrower business-area categories that users are likely to ask about.
- Prefer canonical Industry names and ids from `schemas/industry_taxonomy.json` when a source term matches an alias.
- Keep all Industry hierarchy inside the Industry type; do not reintroduce BusinessArea.
- Prefer concise names such as IT, cloud service, web, semiconductor, memory, foundry, battery, shipbuilding, insurance, construction, logistics, bio, energy, AI, platform, automotive, finance, or display.

Examples:
- Semiconductor
- Battery
- Cloud
- Shipbuilding
- Insurance
- Memory
- Foundry
- Cloud service

### ProductService

A concrete product, service, or offering.

Required fields:
- id
- type
- name

Optional fields:
- description

Rules:
- Use ProductService for specific products and services supported by source text.
- Names must be concise noun phrases, not full sentences.
- ProductService should usually connect upward to Industry with PART_OF.

Examples:
- DRAM
- HBM
- OLED
- EV battery
- LNG carrier
- Brokerage service
- Cloud service
- Smartphone

## Relation Types

### ACQUIRES

Meaning:
A company acquires, merges with, or takes over another listed company.

Direction:
Company -> Company

### INVESTS_IN

Meaning:
A company invests in another listed company.

Direction:
Company -> Company

### APPOINTED_TO

Meaning:
A person is appointed to a position at a company.

Direction:
Person -> Company

Relation fields:
- role
- role_raw
- role_label
- board_role
- full_time_status
- responsibility
- tenure
- tenure_end_on
- major_shareholder_relation

### AFFILIATED_WITH

Meaning:
A person is affiliated with or belongs to a company.

Direction:
Person -> Company

Relation fields:
- role
- role_raw
- role_label
- board_role
- full_time_status
- responsibility
- tenure
- tenure_end_on
- major_shareholder_relation

### BELONGS_TO

Meaning:
A listed company belongs to a broad or narrow industry category.

Direction:
Company -> Industry

Use when:
- The source text supports an industry, market, operating area, or business-line classification.
- Create direct Company -> Industry links for both broad and narrow Industry nodes when evidence supports them.

### PRODUCES

Meaning:
A listed company produces, sells, or provides a product or service.

Direction:
Company -> ProductService

Examples:
- Samsung Electronics -> DRAM
- Samsung SDI -> EV battery
- HD Hyundai Heavy Industries -> LNG carrier

### PART_OF

Meaning:
A narrower concept belongs to a broader business area or industry.

Allowed directions:
- Industry -> Industry
- ProductService -> Industry

Examples:
- Memory -> Semiconductor
- HBM -> Semiconductor
- LNG carrier -> Shipbuilding

### RELATED_TO

Meaning:
Two Industry nodes are associated but neither is clearly part of the other.

Direction:
Industry -> Industry

Use when:
- The source text or clear general industry knowledge supports an association.
- The relationship is not a narrower -> broader hierarchy.

Examples:
- Semiconductor -> Display
- Cloud service -> Web
- Battery -> Automotive

## Preferred Industry Discovery Paths

When evidence allows, prefer paths that make industry questions resolve to companies:

- Company -> Industry
- Company -> ProductService -> Industry
- Industry -> Industry

Use Company -> Industry for both broad categories and specific business-area categories.
Module B normalizes Industry aliases to canonical ids with `industry_taxonomy.json`, then injects taxonomy-backed `PART_OF` ancestors and `RELATED_TO` associations.

## Common Rules

- Every entity must have id, type, and name.
- Every relation must have type, from, to, and evidence.
- Every relation endpoint must exist in the entities array.
- Evidence must come from the input document.
- Do not create entities or relations from unsupported assumptions.
- Do not add fields outside schemas/graph_schema.json.
- Use dates in YYYY-MM-DD format when available.

## ID Rules

Recommended id prefixes:
- company_{stock_code_or_normalized_name}
- person_{normalized_name}
- event_{normalized_event_name}
- industry_{normalized_name}
- product_service_{normalized_name}

Module B canonicalizes listed Company ids to stock_code-based ids during normalization.

## Example

Input sentence:
Samsung Electronics operates memory and foundry businesses and produces DRAM and HBM
for the semiconductor market.

Expected entities:
- Company: Samsung Electronics
- Industry: Memory
- Industry: Foundry
- ProductService: DRAM
- ProductService: HBM
- Industry: Semiconductor

Expected relations:
- Samsung Electronics BELONGS_TO Memory
- Samsung Electronics BELONGS_TO Foundry
- Samsung Electronics BELONGS_TO Semiconductor
- Samsung Electronics PRODUCES DRAM
- Samsung Electronics PRODUCES HBM
- DRAM PART_OF Semiconductor
- HBM PART_OF Semiconductor
- Memory PART_OF Semiconductor
- Foundry PART_OF Semiconductor


### AffiliateGroup

A Fair Trade Commission designated business group. This is not a parent company or subsidiary node; it represents group membership scope for affiliate-based search.

Required fields:
- id
- type
- name

Optional fields:
- presentn_year
- unity_group_code
- source

Rules:
- Create AffiliateGroup nodes only from `docs/ftc_affiliates.jsonl` reference data.
- Do not infer AffiliateGroup nodes from DART/news extraction.

### MEMBER_OF

Meaning:
A listed company belongs to an FTC designated business group.

Direction:
Company -> AffiliateGroup

Use when:
- Loading `docs/ftc_affiliates.jsonl` reference data.
- Answering affiliate-group scoped questions such as “삼성 계열 상장사” or “현대자동차그룹 소속 상장사”.

Do not use MEMBER_OF as ownership, parent-company, subsidiary, or equity evidence.
