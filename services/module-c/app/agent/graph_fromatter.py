from typing import Any, Dict, List
from app.schemas import RelationGraph, RelationNode, RelationLink
from neo4j import Record

class GraphFormatter:
    def format_for_visualization(self, graph_context: List[Dict[str, Any]]) -> RelationGraph:
        nodes_map = {}  # 중복 노드 방지를 위한 딕셔너리
        links = []
        
        for data in graph_context:
            # 1. 노드 처리 (clean_nodes를 단일 데이터 단위로 호출)
            # 리스트가 아닌 '단일 데이터'에서 노드를 추출해 nodes_map에 업데이트
            self.clean_nodes(data, nodes_map)
            
            # 2. 관계 처리 (map_relations를 단일 데이터 단위로 호출)
            # 리스트가 아닌 '단일 뎅터'에서 링크를 추출해 리스트에 추가
            link = self.map_relations(data)
            if link:
                links.append(link)
        
        return RelationGraph(nodes=list(nodes_map.values()), links=links)


    # 한 개의 데이터에서 노드들을 추출하고 중복을 체크하여 맵에 저장
    def clean_nodes(self, data: Dict[str, Any], nodes_map: Dict[str, RelationNode]):
        # 시작 노드 n, 끝 노드 m에 대해 수행
        for key in ['n', 'm']: 
            if key in data and data[key]:
                node_info = data[key]
                # 강제로 넣어준 'id'를 사용
                node_id = str(node_info.get('id'))
                
                if node_id not in nodes_map:
                    nodes_map[node_id] = RelationNode(
                        id=node_id,
                        label=node_info.get('name') or "Unknown"
                    )


    # 한 개의 데이터에서 관계(r)를 추출하여 Link 객체로 변환
    def map_relations(self, data: Dict[str, Any]) -> RelationLink:
        if 'r' in data and data['r']:
            rel_info = data['r']
            return RelationLink(
                source=str(rel_info.get('start_id')),
                target=str(rel_info.get('end_id')),
                relation=rel_info.get('type') or "CONNECTED"
            )
        return None