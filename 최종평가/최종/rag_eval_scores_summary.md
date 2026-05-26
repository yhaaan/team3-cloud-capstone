# RAG ON/OFF Evaluation Summary

## Overall

| System | Count | Avg 1-5 | Avg 100 | Fact | Relation | Evidence | Hallucination |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rag_on | 45 | 3.90 | 78.0 | 3.69 | 3.56 | 4.78 | 3.87 |
| rag_off | 45 | 3.08 | 61.6 | 2.82 | 3.07 | 2.31 | 4.82 |

- RAG ON average: 78.0/100
- RAG OFF average: 61.6/100
- Difference: +16.4 points

## By Category

| Category | System | Count | Avg 100 | Fact | Relation | Evidence | Hallucination |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| direct_contract | rag_on | 1 | 92.0 | 5.00 | 4.00 | 5.00 | 4.00 |
| direct_contract | rag_off | 1 | 80.0 | 4.00 | 5.00 | 2.00 | 5.00 |
| direct_relation | rag_on | 16 | 84.1 | 3.81 | 4.44 | 4.94 | 3.88 |
| direct_relation | rag_off | 16 | 64.8 | 2.50 | 3.75 | 2.94 | 4.75 |
| impact_inference | rag_on | 12 | 67.8 | 3.17 | 2.50 | 4.67 | 3.75 |
| impact_inference | rag_off | 12 | 55.1 | 2.58 | 2.50 | 1.92 | 4.75 |
| multi_hop_chain | rag_on | 16 | 78.8 | 3.88 | 3.44 | 4.69 | 3.94 |
| multi_hop_chain | rag_off | 16 | 62.2 | 3.25 | 2.69 | 2.00 | 4.94 |

## Representative Examples

- direct_relation: best rag_on direct_002=100.0, best rag_off precise_014=84.0
- multi_hop_chain: best rag_on chain_006=100.0, best rag_off chain_002=75.0
- impact_inference: best rag_on impact_004=78.0, best rag_off impact_002=62.0

## Notes

- Scores use the rubric weights from `docs/rag-evaluation-rubric.md`.
- The source answer/question files are preserved unchanged.
- The answer corpus appears mojibake-encoded, so matching uses both raw substring and normalized text comparison.
