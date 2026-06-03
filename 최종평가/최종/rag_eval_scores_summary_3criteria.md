# RAG ON/OFF 3-Criteria Evaluation Summary

## Overall

| System | Count | Avg 1-5 | Avg 100 | Fact | Relation | Evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| rag_on | 45 | 3.87 | 77.3 | 3.69 | 3.56 | 4.78 |
| rag_off | 45 | 2.79 | 55.9 | 2.82 | 3.07 | 2.31 |

- RAG ON average: 77.3/100
- RAG OFF average: 55.9/100
- Difference: +21.5 points

## By Category

| Category | System | Count | Avg 100 | Fact | Relation | Evidence |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| direct_contract | rag_on | 1 | 94.0 | 5.00 | 4.00 | 5.00 |
| direct_contract | rag_off | 1 | 78.0 | 4.00 | 5.00 | 2.00 |
| direct_relation | rag_on | 16 | 84.5 | 3.81 | 4.44 | 4.94 |
| direct_relation | rag_off | 16 | 59.2 | 2.50 | 3.75 | 2.94 |
| impact_inference | rag_on | 12 | 65.3 | 3.17 | 2.50 | 4.67 |
| impact_inference | rag_off | 12 | 48.5 | 2.58 | 2.50 | 1.92 |
| multi_hop_chain | rag_on | 16 | 78.1 | 3.88 | 3.44 | 4.69 |
| multi_hop_chain | rag_off | 16 | 56.6 | 3.25 | 2.69 | 2.00 |

## Notes

- This evaluation excludes hallucination control.
- Weights are fact accuracy 50%, relation reasoning 30%, and evidence use 20%.
- The original 4-criteria outputs are preserved separately.
