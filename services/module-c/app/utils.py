import numpy as np
from openai import OpenAI


def get_embeddings(client: OpenAI, text_list):
        """텍스트 리스트를 2048개씩 쪼개서 임베딩 벡터로 변환"""
        if not text_list: 
            return None
            
        all_embeddings = []
        chunk_size = 2048  # OpenAI 제한 수치

        # 2048개씩 리스트를 쪼개서 반복 호출
        for i in range(0, len(text_list), chunk_size):
            chunk = text_list[i : i + chunk_size]
            response = client.embeddings.create(
                input=chunk,
                model="text-embedding-3-small"
            )
            # 각 청크의 결과를 리스트에 추가
            all_embeddings.extend([d.embedding for d in response.data])
            
        return np.array(all_embeddings)