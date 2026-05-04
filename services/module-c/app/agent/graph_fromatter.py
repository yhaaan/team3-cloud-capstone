from typing import Any, Dict, List
from app.schemas import RelationGraph, RelationNode, RelationLink


class GraphFormatter:
    @staticmethod
    def format_for_visualization(graph_structured_data: List[Dict[str, Any]]) -> RelationGraph:
        unique_nodes: Dict[str, RelationNode] = {}
        unique_links: List[RelationLink] = []
        
        # 중복 링크 체크를 위한 셋 (source-target-relation 조합)
        seen_links = set()

        for path_data in graph_structured_data:
            # [수정 1] path_data가 dict인지 먼저 확인 (문자열 에러 방지)
            if not isinstance(path_data, dict):
                continue

            # 1. 노드 정리 (all_nodes 활용)
            # .keys() 없이 'in'을 사용하는 것이 더 안전하고 빠릅니다.
            if 'all_nodes' in path_data:
                for node_id, node_info in path_data['all_nodes'].items():
                    if node_id not in unique_nodes:
                        unique_nodes[node_id] = RelationNode(
                            id=node_id,
                            name=node_info.get('properties', {}).get('name', 'Unknown')
                        )

            # 2. 링크 정리 (r 리스트 활용)
            if 'r' in path_data:
                # [수정 2] r이 리스트인지 단일 객체인지 한 번 더 체크 (방어 로직)
                rel_list = path_data['r']
                if not isinstance(rel_list, list):
                    rel_list = [rel_list]

                for rel in rel_list:
                    # 데이터가 dict 형태인지 확인 (안전장치)
                    if not isinstance(rel, dict): continue
                    
                    link_id = f"{rel.get('start_id')}-{rel.get('end_id')}-{rel.get('type')}"
                    
                    if link_id not in seen_links:
                        unique_links.append(RelationLink(
                            source=rel.get('start_id'),
                            target=rel.get('end_id'),
                            relation=rel.get('type')
                        ))
                        seen_links.add(link_id)

        return RelationGraph(
            nodes=list(unique_nodes.values()),
            links=unique_links
        )
    



# class GraphFormatter:
#     def format_for_visualization(self, graph_context: List[Dict[str, Any]]) -> RelationGraph:
#         nodes_map = {}  # 중복 노드 방지를 위한 딕셔너리
#         links = []
        
#         for data in graph_context:
#             # 1. 노드 처리 (clean_nodes를 단일 데이터 단위로 호출)
#             # 리스트가 아닌 '단일 데이터'에서 노드를 추출해 nodes_map에 업데이트
#             self.clean_nodes(data, nodes_map)
            
#             # 2. 관계 처리 (map_relations를 단일 데이터 단위로 호출)
#             # 리스트가 아닌 '단일 데이터'에서 링크를 추출해 리스트에 추가
#             new_links = self.map_relations(data)
#             if new_links:
#                 links.extend(new_links)
        
#         return RelationGraph(nodes=list(nodes_map.values()), links=links)


#     # 한 개의 데이터에서 노드들을 추출하고 중복을 체크하여 맵에 저장
#     def clean_nodes(self, data: Dict[str, Any], nodes_map: Dict[str, RelationNode]):
#         # 시작 노드 n, 끝 노드 m에 대해 수행
#         for key in ['n', 'm']: 
#             if key in data and data[key]:
#                 node_data = data[key]
#                 print(node_data)
                
#                 node_id = node_data.get("id")
#                 print(f"!!!!! {node_id}\n")

#                 # node_props = dict(node_data) if not isinstance(node_data, dict) else node_data
                
#                 if node_id and node_id not in nodes_map:
#                     nodes_map[node_id] = {
#                         "id": str(node_id),
#                         "label": node_data.get("name")
#                     }


#     # 한 개의 데이터에서 관계(r)를 추출하여 Link 객체로 변환
#     def map_relations(self, data: Dict[str, Any]) -> List[RelationLink]:
#         links = []
        
#         if 'r' in data.keys() and data['r']:
#             rel_data = data['r']
            
#             # 리스트로 여러 관계가 들어온 경우 (현재 상황)
#             if isinstance(rel_data, list):
#                 for rel in rel_data:
#                     # 각 관계 딕셔너리에서 ID 추출
#                     source = rel.get('start_id')
#                     target = rel.get('end_id')
                    
#                     if source and target:
#                         links.append(RelationLink(
#                             source=str(source),
#                             target=str(target),
#                             relation=rel.get('type') or "CONNECTED"
#                         ))
            
#             # 단일 딕셔너리로 들어온 경우
#             elif isinstance(rel_data, dict):
#                 links.append(RelationLink(
#                     source=str(rel_data.get('start_id')),
#                     target=str(rel_data.get('end_id')),
#                     relation=rel_data.get('type') or "CONNECTED"
#                 ))
                
#         return links