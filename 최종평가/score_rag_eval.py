from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


EVAL_DIR = Path(__file__).resolve().parent
ANSWERS_FILE = EVAL_DIR / "rag_eval_answers_final.jsonl"
QUESTIONS_FILE = EVAL_DIR / "rag_eval_questions_enriched.jsonl"
SCORES_FILE = EVAL_DIR / "rag_eval_scores_final.jsonl"
SUMMARY_FILE = EVAL_DIR / "rag_eval_scores_summary.md"

WEIGHTS = {
    "fact_accuracy": 0.40,
    "relation_reasoning": 0.25,
    "evidence_use": 0.20,
    "hallucination_control": 0.15,
}

SOURCE_ALIASES = {
    "dart": ("dart", "dsaf001", "rcpno", "major_shareholder", "shareholder"),
    "news": ("news", "article", "press", "naver"),
    "graph": ("graph", "neo4j", "relationship", "path"),
    "ftc": ("ftc", "affiliate"),
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.lower()
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def keyword_present(answer: str, keyword: Any) -> bool:
    raw = "" if keyword is None else str(keyword).strip()
    if not raw or raw == "-":
        return False
    if raw.lower() in answer.lower():
        return True

    normalized_answer = normalize_text(answer)
    normalized_keyword = normalize_text(raw)
    if not normalized_keyword:
        return False

    if normalized_keyword in normalized_answer:
        return True

    if "%" in raw:
        numeric = raw.replace("%", "")
        return numeric in answer

    return False


def score_from_ratio(ratio: float) -> int:
    if ratio >= 0.90:
        return 5
    if ratio >= 0.70:
        return 4
    if ratio >= 0.50:
        return 3
    if ratio >= 0.20:
        return 2
    return 1


def score_evidence(answer: str, question: dict[str, Any], matched_facts: list[str]) -> tuple[int, list[str]]:
    lowered = answer.lower()
    evidence_keywords = [str(item) for item in as_list(question.get("evidence_keywords"))]
    required_sources = [str(item).lower() for item in as_list(question.get("required_source_types"))]
    evidence_units = as_list(question.get("evidence_units"))

    source_type_stated = any(alias in lowered for aliases in SOURCE_ALIASES.values() for alias in aliases)
    source_type_stated = source_type_stated or "http" in lowered or "https://" in lowered
    source_type_stated = source_type_stated or any(
        keyword.lower() in {"dart", "news", "graph", "neo4j", "ftc"}
        and keyword_present(answer, keyword)
        for keyword in evidence_keywords
    )

    evidence_targets = []
    for unit in evidence_units:
        if not isinstance(unit, dict):
            continue
        evidence_targets.extend(
            [
                unit.get("company_name"),
                unit.get("stock_code"),
                unit.get("document_type"),
                unit.get("hint"),
            ]
        )
    evidence_targets.extend(question.get("evidence_hint") or [])
    target_stated = any(keyword_present(answer, target) for target in evidence_targets)

    claim_connected = source_type_stated and bool(matched_facts)

    required_coverage = True
    for source in required_sources:
        aliases = SOURCE_ALIASES.get(source, (source,))
        if not any(alias in lowered for alias in aliases):
            required_coverage = False
            break

    checklist = [
        ("source_type_stated", source_type_stated),
        ("evidence_target_stated", target_stated),
        ("claim_connected_to_evidence", claim_connected),
        ("required_source_coverage", required_coverage),
    ]
    satisfied = [name for name, ok in checklist if ok]
    return max(1, min(5, len(satisfied) + 1)), satisfied


def extract_percentages(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?%", text))


def score_hallucination(answer: str, question: dict[str, Any], fact_score: int, relation_score: int) -> tuple[int, list[str]]:
    reference_text = " ".join(
        str(question.get(key) or "")
        for key in ["answer", "expected_reasoning"]
    )
    reference_text += " " + " ".join(str(item) for item in as_list(question.get("expected_facts")))

    answer_percentages = extract_percentages(answer)
    reference_percentages = extract_percentages(reference_text)
    unexpected_percentages = sorted(answer_percentages - reference_percentages)

    unsupported = [f"unexpected_percentage:{item}" for item in unexpected_percentages]

    if answer.strip().startswith("[Error]"):
        unsupported.append("answer_error")

    if fact_score <= 2 and relation_score <= 2:
        unsupported.append("mostly_unmatched_core_claims")

    if "확인" in answer and "필요" in answer and fact_score <= 2:
        unsupported.append("unsupported_generic_disclaimer")

    count = len(unsupported)
    if count == 0:
        return 5, unsupported
    if count == 1:
        return 4, unsupported
    if count == 2:
        return 3, unsupported
    if count <= 4:
        return 2, unsupported
    return 1, unsupported


def grade_answer(answer_record: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    answer = str(answer_record.get("answer") or "")
    expected_facts = [str(item) for item in as_list(question.get("expected_facts")) if str(item).strip()]
    relation_keywords = [str(item) for item in as_list(question.get("relation_keywords")) if str(item).strip()]

    matched_facts = [fact for fact in expected_facts if keyword_present(answer, fact)]
    missing_facts = [fact for fact in expected_facts if fact not in matched_facts]
    fact_ratio = len(matched_facts) / len(expected_facts) if expected_facts else 0.0
    fact_score = score_from_ratio(fact_ratio)

    matched_relations = [keyword for keyword in relation_keywords if keyword_present(answer, keyword)]
    relation_denominator = max(1, len(relation_keywords))
    relation_ratio = len(matched_relations) / relation_denominator
    if question.get("answer_type") in {"multi_hop_path", "multi_hop_chain"}:
        relation_ratio = min(1.0, (relation_ratio + fact_ratio) / 2)
    relation_score = score_from_ratio(relation_ratio)

    evidence_score, evidence_checks = score_evidence(answer, question, matched_facts)
    hallucination_score, hallucinated_claims = score_hallucination(
        answer,
        question,
        fact_score,
        relation_score,
    )

    scores = {
        "fact_accuracy": fact_score,
        "relation_reasoning": relation_score,
        "evidence_use": evidence_score,
        "hallucination_control": hallucination_score,
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
        "hallucinated_claims": hallucinated_claims,
        "evidence_checks": evidence_checks,
        "brief_reason": build_reason(scores, matched_facts, missing_facts, hallucinated_claims),
    }


def build_reason(
    scores: dict[str, int],
    matched_facts: list[str],
    missing_facts: list[str],
    hallucinated_claims: list[str],
) -> str:
    return (
        f"Matched {len(matched_facts)} expected facts and missed {len(missing_facts)}. "
        f"Scores: fact={scores['fact_accuracy']}, relation={scores['relation_reasoning']}, "
        f"evidence={scores['evidence_use']}, hallucination={scores['hallucination_control']}. "
        f"Unsupported claims: {len(hallucinated_claims)}."
    )


def summarize(scores: list[dict[str, Any]]) -> str:
    by_system: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_category_system: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in scores:
        by_system[row["system_type"]].append(row)
        by_category_system[(str(row["category"]), row["system_type"])].append(row)

    lines = [
        "# RAG ON/OFF Evaluation Summary",
        "",
        "## Overall",
        "",
        "| System | Count | Avg 1-5 | Avg 100 | Fact | Relation | Evidence | Hallucination |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for system in ["rag_on", "rag_off"]:
        rows = by_system.get(system, [])
        lines.append(summary_row(system, rows))

    if by_system.get("rag_on") and by_system.get("rag_off"):
        on = mean(row["weighted_score_100"] for row in by_system["rag_on"])
        off = mean(row["weighted_score_100"] for row in by_system["rag_off"])
        lines.extend(
            [
                "",
                f"- RAG ON average: {on:.1f}/100",
                f"- RAG OFF average: {off:.1f}/100",
                f"- Difference: {on - off:+.1f} points",
            ]
        )

    lines.extend(
        [
            "",
            "## By Category",
            "",
            "| Category | System | Count | Avg 100 | Fact | Relation | Evidence | Hallucination |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    categories = sorted({str(row["category"]) for row in scores})
    for category in categories:
        for system in ["rag_on", "rag_off"]:
            rows = by_category_system.get((category, system), [])
            lines.append(category_summary_row(category, system, rows))

    lines.extend(["", "## Representative Examples", ""])
    for category in ["direct_relation", "multi_hop_chain", "impact_inference"]:
        examples = [row for row in scores if row.get("category") == category]
        if not examples:
            continue
        best_on = max((row for row in examples if row["system_type"] == "rag_on"), key=lambda row: row["weighted_score_100"])
        best_off = max((row for row in examples if row["system_type"] == "rag_off"), key=lambda row: row["weighted_score_100"])
        lines.append(
            f"- {category}: best rag_on {best_on['question_id']}={best_on['weighted_score_100']:.1f}, "
            f"best rag_off {best_off['question_id']}={best_off['weighted_score_100']:.1f}"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Scores use the rubric weights from `docs/rag-evaluation-rubric.md`.",
            "- The source answer/question files are preserved unchanged.",
            "- The answer corpus appears mojibake-encoded, so matching uses both raw substring and normalized text comparison.",
        ]
    )
    return "\n".join(lines) + "\n"


def summary_row(system: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"| {system} | 0 | - | - | - | - | - | - |"
    return (
        f"| {system} | {len(rows)} | {mean(row['weighted_score_1_to_5'] for row in rows):.2f} "
        f"| {mean(row['weighted_score_100'] for row in rows):.1f} "
        f"| {mean(row['scores']['fact_accuracy'] for row in rows):.2f} "
        f"| {mean(row['scores']['relation_reasoning'] for row in rows):.2f} "
        f"| {mean(row['scores']['evidence_use'] for row in rows):.2f} "
        f"| {mean(row['scores']['hallucination_control'] for row in rows):.2f} |"
    )


def category_summary_row(category: str, system: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"| {category} | {system} | 0 | - | - | - | - | - |"
    return (
        f"| {category} | {system} | {len(rows)} "
        f"| {mean(row['weighted_score_100'] for row in rows):.1f} "
        f"| {mean(row['scores']['fact_accuracy'] for row in rows):.2f} "
        f"| {mean(row['scores']['relation_reasoning'] for row in rows):.2f} "
        f"| {mean(row['scores']['evidence_use'] for row in rows):.2f} "
        f"| {mean(row['scores']['hallucination_control'] for row in rows):.2f} |"
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
    SUMMARY_FILE.write_text(summarize(scores), encoding="utf-8")

    print(f"Wrote {SCORES_FILE}")
    print(f"Wrote {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
