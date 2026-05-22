# Module B Ontology

## Purpose

Module B extracts a compact graph from financial and company documents for Graph RAG.
The graph should prioritize relations that help users discover listed companies from
industry, business-area, product, service, investment, acquisition, executive, or event
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
- role
- role_raw
- role_label
- birth_ym
- gender
- main_career
- executive_type
- full_time_status
- responsibility
- tenure
- tenure_end_on
- major_shareholder_relation
- affiliated_company

Rules:
- Create Person entities only from DART executive_status documents.
- Do not create Person entities from news documents or non-executive DART documents.
- Put only the person's name in name.
- Put source title text in role when present. Module B normalizes roles after extraction.
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

A broad sector, market, or thematic industry category.

Required fields:
- id
- type
- name

Optional fields:
- description

Rules:
- Use Industry for broad categories that users are likely to ask about.
- Prefer concise names such as semiconductor, battery, cloud, shipbuilding, insurance, construction, bio, energy, AI, platform, automotive, finance, or display.

Examples:
- Semiconductor
- Battery
- Cloud
- Shipbuilding
- Insurance

### BusinessArea

A company's operating segment, business line, or business area.

Required fields:
- id
- type
- name

Optional fields:
- description

Rules:
- Use BusinessArea for segment-level concepts that connect a company to a broader Industry.
- Names must be concise noun phrases, not full sentences.
- BusinessArea should usually connect upward to Industry with PART_OF.

Examples:
- Memory
- Foundry
- Financial services
- Shipbuilding
- Construction
- Logistics
- Cloud business

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
- ProductService should usually connect upward to BusinessArea with PART_OF.

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

### AFFILIATED_WITH

Meaning:
A person is affiliated with or belongs to a company.

Direction:
Person -> Company

### BELONGS_TO

Meaning:
A listed company belongs to a broad industry category.

Direction:
Company -> Industry

Use when:
- The source text supports only broad industry classification.
- There is not enough evidence for a more specific BusinessArea or ProductService path.

### OPERATES_IN

Meaning:
A listed company operates in a business area or segment.

Direction:
Company -> BusinessArea

Examples:
- Samsung Electronics -> Memory
- Hyundai Heavy Industries -> Shipbuilding

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
- BusinessArea -> Industry
- ProductService -> BusinessArea

Examples:
- Memory -> Semiconductor
- HBM -> Memory
- LNG carrier -> Shipbuilding

## Preferred Industry Discovery Paths

When evidence allows, prefer paths that make industry questions resolve to companies:

- Company -> BusinessArea -> Industry
- Company -> ProductService -> BusinessArea -> Industry
- Company -> Industry

Use Company -> Industry only when the document gives broad industry evidence without
specific business areas or products/services.

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
- business_area_{normalized_name}
- product_service_{normalized_name}

Module B canonicalizes listed Company ids to stock_code-based ids during normalization.

## Example

Input sentence:
Samsung Electronics operates memory and foundry businesses and produces DRAM and HBM
for the semiconductor market.

Expected entities:
- Company: Samsung Electronics
- BusinessArea: Memory
- BusinessArea: Foundry
- ProductService: DRAM
- ProductService: HBM
- Industry: Semiconductor

Expected relations:
- Samsung Electronics OPERATES_IN Memory
- Samsung Electronics OPERATES_IN Foundry
- Samsung Electronics PRODUCES DRAM
- Samsung Electronics PRODUCES HBM
- DRAM PART_OF Memory
- HBM PART_OF Memory
- Memory PART_OF Semiconductor
- Foundry PART_OF Semiconductor
