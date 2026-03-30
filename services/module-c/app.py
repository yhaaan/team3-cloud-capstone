import streamlit as st
import requests
import uuid

st.title("Module C 테스트 클라이언트")

# 1. 세션 관리 (탭 끄면 사라짐)
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []

# 2. 채팅 인터페이스
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("질문을 입력하세요"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 3. 백엔드(FastAPI) 서버로 요청 보내기
    with st.chat_message("assistant"):
        payload = {
            "query": prompt,
            "session_id": st.session_state.session_id
        }
        
        try:
            # 백엔드 서버 주소
            response = requests.post("http://127.0.0.1:8000/chat", json=payload)
            answer = response.json().get("answer")
            st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
        except Exception as e:
            st.error(f"백엔드 연결 실패: {e}")