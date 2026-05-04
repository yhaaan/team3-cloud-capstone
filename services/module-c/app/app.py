import streamlit as st
import requests
import uuid

st.title("Module C 테스트 클라이언트")

# 백엔드 상태 확인 함수
def get_server_status():
    try:
        response = requests.get("http://localhost:8000/check-status")
        return response.json()
    except:
        return {"status": "error", "message": "백엔드 서버가 실행되지 않았습니다."}

# 상태 체크 실행
status_info = get_server_status()

if status_info.get("status") == "error":
    # 에러가 있으면 화면 상단에 에러를 띄우고 입력을 막음
    st.error(f"⚠️ 시스템 사용 불가\n\n {status_info['message']}")
    st.info("현재 시스템 오류 복구 중입니다. 잠시 후 새로고침(F5)을 하시면 정상적으로 이용하실 수 있습니다.")
    # st.chat_input을 아예 렌더링하지 않거나 disabled 처리
    st.chat_input("시스템 오류로 인해 질문할 수 없습니다.", disabled=True)
else:
    # 상태가 정상이면 채팅 UI 활성화
    # st.success("시스템 정상 작동 중")

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
                # 1. 응답 전체를 JSON으로 받기
                data = response.json()

                # 2. 최종 답변(텍스트) 추출 및 출력
                final_response = data.get("final_response")
                st.markdown(final_response)

                # 3. 그래프 데이터(JSON) 추출 및 출력
                relation_graph = data.get("relation_graph")

                if relation_graph:
                    st.markdown("---")
                    st.markdown("### 📊 관계 그래프 데이터 (JSON)")
                    # JSON 데이터를 확장 가능한 박스(expander) 안에 넣어 깔끔하게 보여줍니다.
                    with st.expander("그래프 데이터 보기"):
                        st.json(relation_graph)
                else:
                    st.info("표시할 그래프 데이터가 없습니다.")
            except Exception as e:
                st.error(f"백엔드 연결 실패: {e}")

