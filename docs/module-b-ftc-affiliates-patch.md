# Module B FTC 계열사 그래프 패치 내역

## 작업 목적

사용자가 "삼성 계열사", "현대자동차그룹 소속 상장사", "이 회사가 어느 계열집단인지"처럼 계열사 기반 질문을 했을 때 그래프에서 탐색할 수 있도록 Module B 그래프 적재 단계에 FTC 계열집단 데이터를 추가했다.

이번 작업의 계열사 데이터는 자회사/모회사 지분 관계가 아니라, 공정거래위원회 기준의 동일 기업집단 소속 관계다.

## 사용 데이터

- 기본 사용 파일: `docs/ftc_affiliates.jsonl`
- 참고 가능 파일: `docs/ftc_affiliates_all.jsonl`
- 스키마 설명 파일: `schemas/ftc_affiliates_schema.txt`

현재 v1 구현에서는 `ftc_affiliates.jsonl`만 사용한다. 이 파일은 계열집단에 포함된 상장사를 정리한 데이터다.

`ftc_affiliates_all.jsonl`은 비상장사까지 포함하므로 DB 복잡도를 줄이기 위해 이번 기본 적재 대상에서는 제외했다.

## 추가된 노드

### AffiliateGroup

공정위 기준 계열집단을 나타내는 노드다.

예시:

```cypher
(:AffiliateGroup {
  id: "affiliate_group_삼성",
  type: "AffiliateGroup",
  name: "삼성",
  presentn_year: "2025",
  source: "ftc_affiliates"
})
```

주요 속성:

| 속성 | 설명 |
| --- | --- |
| `id` | 그래프 내부에서 사용하는 계열집단 ID. 예: `affiliate_group_삼성` |
| `type` | 노드 타입. 항상 `AffiliateGroup` |
| `name` | 계열집단명. 예: `삼성`, `현대자동차`, `SK` |
| `presentn_year` | FTC 데이터의 기준 연도 |
| `source` | 데이터 출처. 현재는 `ftc_affiliates` |
| `unity_group_code` | 원천 데이터에 존재하는 경우 사용하는 기업집단 코드 |

## 추가된 관계

### MEMBER_OF

상장사 `Company`가 특정 `AffiliateGroup`에 속한다는 관계다.

```cypher
(:Company)-[:MEMBER_OF]->(:AffiliateGroup)
```

예시:

```cypher
(:Company {id: "company_005930", name: "삼성전자"})
  -[:MEMBER_OF {
    presentn_year: "2025",
    jurirno: "...",
    bizrno: "...",
    representative_name: "...",
    founded_on: "...",
    joined_on: "...",
    source: "ftc_affiliates"
  }]->
(:AffiliateGroup {id: "affiliate_group_삼성", name: "삼성"})
```

이 관계는 소유, 지배, 자회사, 모회사 관계가 아니다. 단순히 FTC 계열집단 기준으로 같은 기업집단에 포함된다는 의미다.

## MEMBER_OF 관계 속성 설명

| 속성 | 설명 |
| --- | --- |
| `presentn_year` | 원천 데이터의 기준 연도다. 같은 회사라도 연도별 계열집단 편입 상태가 달라질 수 있으므로 관계 속성으로 보관한다. |
| `jurirno` | 법인등록번호다. 회사 법인 식별에 사용되는 번호이며, 원천 데이터에 값이 있을 때 관계 속성으로 보관한다. |
| `bizrno` | 사업자등록번호다. 회사 사업자 식별에 사용되는 번호이며, 원천 데이터에 값이 있을 때 관계 속성으로 보관한다. |
| `representative_name` | 원천 데이터에 기록된 대표자명이다. 해당 계열사 레코드의 대표자 정보를 보존하기 위한 속성이다. |
| `founded_on` | 회사 설립일이다. 원천 데이터의 설립일 정보를 관계 속성으로 보존한다. |
| `joined_on` | 계열집단 편입일이다. 해당 회사가 해당 계열집단에 편입된 날짜를 의미한다. |
| `source` | 관계 생성에 사용한 데이터 출처다. 현재 값은 `ftc_affiliates`다. |

## 스키마 변경

`schemas/graph_schema.json`에 다음 타입을 추가했다.

노드 타입:

```text
AffiliateGroup
```

관계 타입:

```text
MEMBER_OF
```

관계 속성:

```text
presentn_year
jurirno
bizrno
representative_name
founded_on
joined_on
source
```

## 적재 코드 변경

추가 파일:

```text
services/module-b/src/ftc_affiliates.py
```

주요 역할:

- `docs/ftc_affiliates.jsonl` 로딩
- 회사명 정규화
- 상장사 리스트와 매칭
- `AffiliateGroup` 노드 생성
- `Company -> AffiliateGroup` `MEMBER_OF` 관계 생성

`services/module-b/src/load_neo4j.py`에는 FTC 계열사 적재 옵션을 추가했다.


## 매칭 검증 결과

`docs/ftc_affiliates.jsonl` 기준 검증 결과:

```text
총 221개 row
64개 계열집단
221개 모두 상장사 리스트와 매칭
미매칭 0개
```

회사명 정규화에서는 다음 차이를 제거한다.

- `(주)`
- `㈜`
- `주식회사`
- 공백

예시:

```text
삼성전자(주) -> 삼성전자
(주)현대자동차 -> 현대자동차
```

## 테스트

`services/module-b/tests/test_module_b.py`에 FTC 계열사 관련 테스트를 추가했다.

검증 내용:

- FTC 계열사 JSONL 로딩
- 상장사 리스트 매칭
- `AffiliateGroup` 노드 생성
- `Company -> AffiliateGroup` `MEMBER_OF` 관계 생성
- 삼성전자(`005930`)가 삼성 계열집단에 연결되는지 확인

실행 결과:

```text
Ran 26 tests in 22.767s
OK
```

## Module C 담당자 참고

Module B 적재 후 그래프에는 다음 구조가 존재할 수 있다.

```cypher
(company:Company)-[:MEMBER_OF]->(group:AffiliateGroup)
```

따라서 Module C에서 계열사 기반 질문을 지원하려면 질의 생성 프롬프트 또는 쿼리 생성 로직에서 `AffiliateGroup` 노드와 `MEMBER_OF` 관계를 인식하도록 별도 반영이 필요하다.

예상 질의 예시:

```cypher
MATCH (c:Company)-[:MEMBER_OF]->(g:AffiliateGroup)
WHERE g.name = "삼성"
RETURN c.name, c.stock_code
```

```cypher
MATCH (c:Company {name: "삼성전자"})-[:MEMBER_OF]->(g:AffiliateGroup)
RETURN g.name
```

