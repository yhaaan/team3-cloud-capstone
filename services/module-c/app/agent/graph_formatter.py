from typing import Any, Dict, List
from app.schemas import RelationGraph, RelationNode, RelationLink


class GraphFormatter:
    @staticmethod
    def format_for_visualization(graph_structured_data: List[Dict[str, Any]], center_id: str) -> RelationGraph:
        name_to_node: Dict[str, RelationNode] = {}
        id_to_name: Dict[str, str] = {}
        unique_links: List[RelationLink] = []
        seen_links = set()

        # 1. 노드 정보 수집 (n, m, p 모두 포함)
        for path_data in graph_structured_data:
            nodes_to_process = []
            if 'n' in path_data: nodes_to_process.append(path_data['n'])
            if 'm' in path_data: nodes_to_process.append(path_data['m'])
            # 이제 process_data_for_all에서 p에 노드 리스트를 넣어주므로 바로 확장 가능!
            if 'p' in path_data and isinstance(path_data['p'], list):
                nodes_to_process.extend(path_data['p'])

            for node in nodes_to_process:
                if isinstance(node, dict) and 'name' in node:
                    name = node['name'].strip() # 공복 제거로 중복 방지
                    node_id = node.get('id')
                    
                    if name not in name_to_node:
                        name_to_node[name] = RelationNode(
                            id=name, 
                            name=name,
                            type=node.get('type', 'Entity')
                        )
                    
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

                # id_to_name에 없더라도 에러가 나지 않도록 방어 로직
                source_name = id_to_name.get(s_id, s_id)
                target_name = id_to_name.get(e_id, e_id)

                # 만약 방금 생성된 이름이 노드 리스트에 없다면 강제로 추가 (에러 방지)
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