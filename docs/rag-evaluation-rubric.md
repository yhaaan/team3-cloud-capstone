# RAG ON/OFF Evaluation Rubric

## Purpose

This rubric evaluates whether RAG improves answers for the project's company disclosure, news, and graph-based question answering task.

The comparison target is:

- RAG OFF: LLM answers without retrieval from the project database.
- RAG ON: LLM answers using retrieved evidence from Chroma, Neo4j, DART data, news data, or generated graph outputs.

This evaluation does not claim general LLM superiority. It measures performance on the project's domain-specific task: answering questions grounded in company disclosures, news, ownership structures, and entity-relation graphs.

Use the same question set, expected answer, expected reasoning, evidence hints, and answer type from `rag_eval_questions.jsonl` for both RAG OFF and RAG ON answers. For automated judging, use `rag_eval_questions_enriched.jsonl`, which preserves the original fields and adds scoring metadata.

## Scoring Overview

Each answer is scored on four criteria. Each criterion receives an integer score from 1 to 5.

| Criterion | Weight |
| --- | ---: |
| Fact Accuracy | 40% |
| Relation Reasoning Accuracy | 25% |
| Evidence Use | 20% |
| Hallucination Control | 15% |

Weighted score on a 1 to 5 scale:

```text
weighted_score_1_to_5 =
fact_accuracy * 0.40 +
relation_reasoning * 0.25 +
evidence_use * 0.20 +
hallucination_control * 0.15
```

Weighted score on a 100-point scale:

```text
weighted_score_100 =
(fact_accuracy / 5 * 40) +
(relation_reasoning / 5 * 25) +
(evidence_use / 5 * 20) +
(hallucination_control / 5 * 15)
```

## 1. Fact Accuracy

Fact Accuracy measures whether the answer matches the core facts in the reference answer.

Core facts include company names, ownership percentages, major shareholder status, relation direction, event names, person names, roles, and other concrete factual claims required by the question.

| Score | Standard |
| ---: | --- |
| 5 | 90-100% of core facts match the reference answer. |
| 4 | 70-89% of core facts match the reference answer. |
| 3 | 50-69% of core facts match the reference answer. |
| 2 | 20-49% of core facts match the reference answer. |
| 1 | 0-19% of core facts match the reference answer, or the answer is mostly incorrect. |

## 2. Relation Reasoning Accuracy

Relation Reasoning Accuracy measures whether the answer correctly explains direct relations, indirect relations, multi-hop paths, intermediate companies, relation direction, and relation type.

For a path such as:

```text
LG -> LG화학 -> LG에너지솔루션
```

the scoring elements include:

- start company
- intermediate company
- target company
- relation direction
- relation type, such as major shareholder, ownership, affiliate, investment, or impact candidate

| Score | Standard |
| ---: | --- |
| 5 | 90-100% of required relation elements match the reference reasoning. |
| 4 | 70-89% of required relation elements match the reference reasoning. |
| 3 | 50-69% of required relation elements match the reference reasoning. |
| 2 | 20-49% of required relation elements match the reference reasoning. |
| 1 | 0-19% of required relation elements match the reference reasoning, or relation reasoning is mostly absent. |

## 3. Evidence Use

Evidence Use measures whether the answer connects its main claims to verifiable project evidence. Do not score Evidence Use by URL presence alone. A URL is useful, but a correct document name, filing type, source description, or graph evidence can also count.

Valid evidence includes:

- URL
- document name
- DART filing name
- news source
- graph/database evidence
- phrases such as "DART major shareholder status" or "based on the collected news"
- evidence that matches or is semantically equivalent to `evidence_hint`

Score this criterion using four checklist items:

1. Source type is stated: the answer mentions DART, filing, news, collected data, graph, ownership structure, or another verifiable source type.
2. Evidence target is stated: the answer makes clear which company, document, filing, article, or graph relation supports the claim.
3. Main claim is connected to evidence: the answer links the core fact or relation to the cited evidence.
4. Required source coverage is satisfied: the answer uses the source types required by the question, such as DART for shareholder questions or both DART and news for mixed evidence questions.

| Score | Standard |
| ---: | --- |
| 5 | All 4 checklist items are satisfied. |
| 4 | 3 checklist items are satisfied. |
| 3 | 2 checklist items are satisfied. |
| 2 | 1 checklist item is satisfied. |
| 1 | 0 checklist items are satisfied, or the answer provides no evidence. |

## 4. Hallucination Control

Hallucination Control measures whether the answer avoids unsupported additions.

Unsupported additions include company names, ownership percentages, relation types, events, news claims, people, roles, or other factual claims that are not present in the reference answer, expected reasoning, evidence hints, or retrieved evidence.

Higher scores mean fewer unsupported additions.

| Score | Standard |
| ---: | --- |
| 5 | 0 unsupported additions. |
| 4 | 1 unsupported addition. |
| 3 | 2 unsupported additions. |
| 2 | 3-4 unsupported additions. |
| 1 | 5 or more unsupported additions, or the answer is mainly built on unsupported claims. |

## LLM Judge Output Format

When an LLM is used as a judge, it must output one JSON object per evaluated answer.

```json
{
  "question_id": "chain_005",
  "system_type": "rag_on",
  "scores": {
    "fact_accuracy": 5,
    "relation_reasoning": 5,
    "evidence_use": 4,
    "hallucination_control": 5
  },
  "weighted_score_1_to_5": 4.8,
  "weighted_score_100": 96.0,
  "matched_facts": ["LG", "LG화학", "LG에너지솔루션", "최대주주"],
  "missing_facts": [],
  "hallucinated_claims": [],
  "brief_reason": "The answer correctly explains the ownership path and cites DART major shareholder evidence."
}
```

## Evaluation Procedure

1. Generate one RAG OFF answer and one RAG ON answer for each question in `rag_eval_questions.jsonl`.
2. Evaluate both answers with the same rubric.
3. Use `rag_eval_questions_enriched.jsonl` as the judging metadata. Its original `answer`, `expected_reasoning`, `evidence_hint`, and `answer_type` fields remain the reference materials.
4. Record the four raw criterion scores and both weighted scores.
5. Compare RAG OFF and RAG ON by average weighted score and by criterion-level average.
6. Report at least one example each from `direct_relation`, `multi_hop_chain`, and `impact_inference`.

## Recommended Validation

Before running the full evaluation, manually review a small sample:

- one `direct_relation` question
- one `multi_hop_chain` question
- one `impact_inference` question

If two human reviewers score the same answer, the target score difference should be no more than 1 point per criterion. Larger disagreements should be resolved by clarifying the expected facts, relation elements, or unsupported claims for that question.

## Assumptions

- The evaluation is designed for RAG ON/OFF comparison, not general-purpose LLM benchmarking.
- URL presence is not mandatory. It is only one possible signal of evidence use.
- The project's question set is intentionally DB-grounded because the system is designed for company disclosure, news, and graph-based question answering.
- `rag_eval_questions.jsonl` is the source of the benchmark questions and reference answers.
- `rag_eval_questions_enriched.jsonl` is the derived evaluation metadata file for LLM judges or scoring scripts.
