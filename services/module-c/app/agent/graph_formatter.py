from typing import Any, Dict, List
from app.schemas import RelationGraph, RelationNode, RelationLink


class GraphFormatter:
    @staticmethod
    def format_for_visualization(graph_structured_data: List[Dict[str, Any]], center_id: str) -> RelationGraph:
        name_to_node: Dict[str, RelationNode] = {}
        id_to_name: Dict[str, str] = {}
        unique_links: List[RelationLink] = []
        seen_links = set()

        # 1. 노드 정보 수집
        for path_data in graph_structured_data:
            nodes_to_process = []
            if 'n' in path_data and path_data['n']: nodes_to_process.append(path_data['n'])
            if 'm' in path_data and path_data['m']: nodes_to_process.append(path_data['m'])
            if 'path' in path_data and isinstance(path_data['path'], list):
                nodes_to_process.extend(path_data['path'])

            for node in nodes_to_process:
                if isinstance(node, dict) and 'name' in node:
                    name = node['name'].strip()
                    node_id = node.get('id') # 이제 무조건 element_id가 들어옵니다.
                    
                    if name not in name_to_node:
                        # 시각화 컴포넌트 편의를 위해 id=name 구조 유지
                        name_to_node[name] = RelationNode(
                            id=name, 
                            name=name,
                            type=node.get('type', 'Entity')
                        )
                    
                    # [매우 중요] 내부 해시 ID와 실제 한국어 이름을 매핑 테이블에 동기화
                    if node_id:
                        id_to_name[node_id] = name

        # 2. 관계 데이터를 돌며 링크 생성
        for path_data in graph_structured_data:
            rels = path_data.get('r', [])
            if not isinstance(rels, list): rels = [rels]

            for rel in rels:
                s_id = rel.get('start_id')
                e_id = rel.get('end_id')
                rel_type = rel.get('type')

                # 정제된 id_to_name에서 실제 한글 이름을 조회합니다.
                source_name = id_to_name.get(s_id, s_id)
                target_name = id_to_name.get(e_id, e_id)

                # 매핑에 실패한 유령 ID가 올 경우 최소한 무형의 Unknown 노드로 강제 추가 방어
                for name in [source_name, target_name]:
                    if name not in name_to_node:
                        name_to_node[name] = RelationNode(id=name, name=name, type='Unknown')

                link_key = f"{source_name}-{target_name}-{rel_type}"
                if link_key not in seen_links:
                    unique_links.append(RelationLink(
                        source=source_name,
                        target=target_name,
                        relation=rel_type
                    ))
                    seen_links.add(link_key)

        return RelationGraph(
            center=center_id,
            nodes=list(name_to_node.values()),
            links=unique_links
        )