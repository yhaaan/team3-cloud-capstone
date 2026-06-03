from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from score_rag_eval import (
    as_list,
    keyword_present,
    read_jsonl,
    score_evidence,
    score_from_ratio,
)


OUTPUT_DIR = EVAL_DIR / "최종"
ANSWERS_FILE = EVAL_DIR / "rag_eval_answers_final.jsonl"
QUESTIONS_FILE = EVAL_DIR / "rag_eval_questions_enriched.jsonl"
SCORES_FILE = OUTPUT_DIR / "rag_eval_scores_3criteria.jsonl"
SUMMARY_FILE = OUTPUT_DIR / "rag_eval_scores_summary_3criteria.md"
SUMMARY_KO_FILE = OUTPUT_DIR / "rag_eval_scores_summary_3criteria_ko.md"

WEIGHTS = {
    "fact_accuracy": 0.50,
    "relation_reasoning": 0.30,
    "evidence_use": 0.20,
}


def grade_answer(answer_record: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    answer = str(answer_record.get("answer") or "")
    expected_facts = [
        str(item)
        for item in as_list(question.get("expected_facts"))
        if str(item).strip()
    ]
    relation_keywords = [
        str(item)
        for item in as_list(question.get("relation_keywords"))
        if str(item).strip()
    ]

    matched_facts = [fact for fact in expected_facts if keyword_present(answer, fact)]
    missing_facts = [fact for fact in expected_facts if fact not in matched_facts]
    fact_ratio = len(matched_facts) / len(expected_facts) if expected_facts else 0.0
    fact_score = score_from_ratio(fact_ratio)

    matched_relations = [
        keyword
        for keyword in relation_keywords
        if keyword_present(answer, keyword)
    ]
    relation_ratio = len(matched_relations) / max(1, len(relation_keywords))
    if question.get("answer_type") in {"multi_hop_path", "multi_hop_chain"}:
        relation_ratio = min(1.0, (relation_ratio + fact_ratio) / 2)
    relation_score = score_from_ratio(relation_ratio)

    evidence_score, evidence_checks = score_evidence(answer, question, matched_facts)

    scores = {
        "fact_accuracy": fact_score,
        "relation_reasoning": relation_score,
        "evidence_use": evidence_score,
    }
    weighted_1_to_5 = sum(scores[key] * weight for key, weight in WEIGHTS.items())
    weighted_100 = sum((scores[key] / 5) * weight * 100 for key, weight in WEIGHTS.items())

    return {
        "question_id": answer_record["question_id"],
        "system_type": answer_record["system_type"],
        "category": question.get("category"),
        "difficulty": question.get("difficulty"),
        "scores": scores,
        "weighted_score_1_to_5": round(weighted_1_to_5, 2),
        "weighted_score_100": round(weighted_100, 1),
        "matched_facts": matched_facts,
        "missing_facts": missing_facts,
        "evidence_checks": evidence_checks,
        "brief_reason": (
            f"Matched {len(matched_facts)} expected facts and missed {len(missing_facts)}. "
            f"Scores: fact={fact_score}, relation={relation_score}, evidence={evidence_score}."
        ),
    }


def summarize(scores: list[dict[str, Any]], korean: bool = False) -> str:
    by_system: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_category_system: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in scores:
        by_system[row["system_type"]].append(row)
        by_category_system[(str(row["category"]), row["system_type"])].append(row)

    if korean:
        lines = [
            "# RAG ON/OFF 3항목 평가 요약",
            "",
            "## 전체 결과",
            "",
            "| 시스템 | 답변 수 | 평균 점수(1-5) | 평균 점수(100점) | 사실 정확성 | 관계 추론 | 근거 활용 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    else:
        lines = [
            "# RAG ON/OFF 3-Criteria Evaluation Summary",
            "",
            "## Overall",
            "",
            "| System | Count | Avg 1-5 | Avg 100 | Fact | Relation | Evidence |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]

    for system in ["rag_on", "rag_off"]:
        rows = by_system.get(system, [])
        lines.append(summary_row(system, rows))

    if by_system.get("rag_on") and by_system.get("rag_off"):
        on = mean(row["weighted_score_100"] for row in by_system["rag_on"])
        off = mean(row["weighted_score_100"] for row in by_system["rag_off"])
        if korean:
            lines.extend(
                [
                    "",
                    f"- RAG ON 평균 점수: {on:.1f}/100",
                    f"- RAG OFF 평균 점수: {off:.1f}/100",
                    f"- 점수 차이: RAG ON이 {on - off:+.1f}점 높음",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    f"- RAG ON average: {on:.1f}/100",
                    f"- RAG OFF average: {off:.1f}/100",
                    f"- Difference: {on - off:+.1f} points",
                ]
            )

    if korean:
        lines.extend(
            [
                "",
                "## 카테고리별 결과",
                "",
                "| 카테고리 | 시스템 | 답변 수 | 평균 점수(100점) | 사실 정확성 | 관계 추론 | 근거 활용 |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## By Category",
                "",
                "| Category | System | Count | Avg 100 | Fact | Relation | Evidence |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )

    for category in sorted({str(row["category"]) for row in scores}):
        for system in ["rag_on", "rag_off"]:
            rows = by_category_system.get((category, system), [])
            lines.append(category_summary_row(category, system, rows))

    if korean:
        lines.extend(
            [
                "",
                "## 해석",
                "",
                "- 이 결과는 환각억제력 항목을 제외하고 사실 정확성, 관계 추론, 근거 활용도만 반영한 3항목 평가다.",
                "- 가중치는 사실 정확성 50%, 관계 추론 30%, 근거 활용도 20%를 사용했다.",
                "- 기존 4항목 평가 결과는 보존되어 있으며, 이 파일은 3항목 기준 비교용이다.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Notes",
                "",
                "- This evaluation excludes hallucination control.",
                "- Weights are fact accuracy 50%, relation reasoning 30%, and evidence use 20%.",
                "- The original 4-criteria outputs are preserved separately.",
            ]
        )

    return "\n".join(lines) + "\n"


def summary_row(system: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"| {system} | 0 | - | - | - | - | - |"
    return (
        f"| {system} | {len(rows)} | {mean(row['weighted_score_1_to_5'] for row in rows):.2f} "
        f"| {mean(row['weighted_score_100'] for row in rows):.1f} "
        f"| {mean(row['scores']['fact_accuracy'] for row in rows):.2f} "
        f"| {mean(row['scores']['relation_reasoning'] for row in rows):.2f} "
        f"| {mean(row['scores']['evidence_use'] for row in rows):.2f} |"
    )


def category_summary_row(category: str, system: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"| {category} | {system} | 0 | - | - | - | - |"
    return (
        f"| {category} | {system} | {len(rows)} "
        f"| {mean(row['weighted_score_100'] for row in rows):.1f} "
        f"| {mean(row['scores']['fact_accuracy'] for row in rows):.2f} "
        f"| {mean(row['scores']['relation_reasoning'] for row in rows):.2f} "
        f"| {mean(row['scores']['evidence_use'] for row in rows):.2f} |"
    )


def validate(scores: list[dict[str, Any]], answers: list[dict[str, Any]]) -> None:
    if len(scores) != 90:
        raise RuntimeError(f"Expected 90 scored answers, got {len(scores)}")
    system_counts = Counter(row["system_type"] for row in scores)
    if system_counts != Counter({"rag_on": 45, "rag_off": 45}):
        raise RuntimeError(f"Unexpected system counts: {system_counts}")

    answer_keys = {(row["question_id"], row["system_type"]) for row in answers}
    score_keys = {(row["question_id"], row["system_type"]) for row in scores}
    if answer_keys != score_keys:
        raise RuntimeError("Scored answer keys do not match source answer keys")

    for row in scores:
        if set(row["scores"]) != set(WEIGHTS):
            raise RuntimeError(f"Missing score fields for {row['question_id']}:{row['system_type']}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    answers = read_jsonl(ANSWERS_FILE)
    questions = {row["id"]: row for row in read_jsonl(QUESTIONS_FILE)}

    scores = [
        grade_answer(answer, questions[answer["question_id"]])
        for answer in sorted(answers, key=lambda row: (row["question_id"], row["system_type"]))
    ]
    validate(scores, answers)

    SCORES_FILE.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in scores) + "\n",
        encoding="utf-8",
    )
    SUMMARY_FILE.write_text(summarize(scores, korean=False), encoding="utf-8")
    SUMMARY_KO_FILE.write_text(summarize(scores, korean=True), encoding="utf-8")

    print(f"Wrote {SCORES_FILE}")
    print(f"Wrote {SUMMARY_FILE}")
    print(f"Wrote {SUMMARY_KO_FILE}")


if __name__ == "__main__":
    main()
