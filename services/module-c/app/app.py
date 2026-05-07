import time
import streamlit as st
import requests
import uuid

st.title("Module C 테스트 클라이언트")

# # 백엔드 상태 확인 함수
# def get_server_status():
#     try:
#         # 타임아웃을 짧게(예: 2초) 설정해서 대기 시간을 줄이는 것이 좋습니다.
#         response = requests.get("http://localhost:8000/check-status", timeout=10)
#         return response.json()
#     except:
#         return {"status": "error", "message": "백엔드 서버가 실행되지 않았습니다."}

def wait_for_server(url="http://localhost:8000/check-status", max_retries=10, delay=1):
    """서버가 켜질 때까지 max_retries번만큼 반복해서 확인하는 함수"""
    for i in range(max_retries):
        try:
            # 타임아웃을 짧게(1초) 잡아서 서버가 응답 가능한지 빨리 확인합니다.
            response = requests.get(url, timeout=1)
            if response.status_code == 200:
                return response.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            # 서버가 아직 재시작 중이라 연결이 안 되는 상태
            # 사용자에게 기다려달라는 메시지를 표시할 수도 있어요.
            with st.spinner(f"서버 재시작 중... 잠시만 기다려주세요 ({i+1}/{max_retries})"):
                time.sleep(delay)  # 1초 기다렸다가 다시 시도
    
    return {"status": "error", "message": "서버가 응답하지 않습니다. 도커나 서버 로그를 확인하세요."}
    

# 세션 상태 초기화 (최초 1회만 실행)
if "backend_ok" not in st.session_state or not st.session_state.backend_ok:
    try:
        status_info = wait_for_server()
        # status_info = get_server_status()
        if status_info.get("status") == "ok":
            st.session_state.backend_ok = True
        else:
            st.session_state.backend_ok = False
            # 메시지가 없을 경우를 대비한 기본 문구
            st.session_state.error_msg = status_info.get('message', '알 수 없는 서버 오류')
    except Exception as e:
        st.session_state.backend_ok = False
        st.session_state.error_msg = "서버와 통신할 수 없습니다. 도커가 켜져 있는지 확인해주세요."

    # status_info = get_server_status()
    # if status_info.get("status") == "ok":
    #     st.session_state.backend_ok = True
    # else:
    #     st.session_state.backend_ok = False
    #     st.session_state.error_msg = status_info['message']


# 상태에 따른 화면 렌더링
if not st.session_state.get("backend_ok", False):
    # 에러가 있으면 화면 상단에 에러를 띄우고 입력을 막음
    st.error(f"⚠️ 시스템 사용 불가\n\n {st.session_state.get('error_msg', '알 수 없는 오류')}")
    st.info("현재 시스템 오류 복구 중입니다. 잠시 후 새로고침(F5)을 하시면 정상적으로 이용하실 수 있습니다.")
    st.chat_input("시스템 오류로 인해 질문할 수 없습니다.", disabled=True)
else:
    # --- 시스템 정상 작동 시 채팅 UI 시작 ---

    # 세션 관리 (탭 끄면 사라지는 uuid)
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []

    # 이전 메시지 출력
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    # 채팅 입력창
    if prompt := st.chat_input("질문을 입력하세요"):
        # 유저 메시지 표시 및 저장
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 챗봇 응답 처리
        with st.chat_message("assistant"):
            payload = {
                "query": prompt,
                "session_id": st.session_state.session_id
            }
            
            # 답변 생성 중임을 알리는 스피너
            with st.spinner("지식을 탐색하고 답변을 생성하는 중입니다..."):
                try:
                    # 백엔드 서버 주소 (timeout은 릴리님의 기획 임계치를 고려해 15초 정도로 설정)
                    response = requests.post("http://127.0.0.1:8000/chat", json=payload, timeout=30)
                    response.raise_for_status() # 400, 500 에러 발생 시 예외 처리로 이동
                    
                    data = response.json()
                    final_response = data.get("final_response")
                    relation_graph = data.get("relation_graph")

                    # 3. 화면 출력
                    st.markdown(final_response)

                    if relation_graph:
                        st.markdown("---")
                        st.markdown("### 📊 관계 그래프 데이터 (JSON)")
                        with st.expander("그래프 데이터 보기"):
                            st.json(relation_graph)
                    
                    # 4. 세션 상태에 저장 (나중에 다시 그릴 때 사용)
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": final_response,
                        "graph": relation_graph # 그래프 데이터도 함께 저장
                    })

                except Exception as e:
                    # 릴리님의 기획안: 백엔드 Retry(2회) 실패 또는 타임아웃 발생 시
                    st.error("서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.")
                    # 디버깅을 위해 콘솔에만 상세 에러 로그를 남깁니다.
                    print(f"[DEBUG] Backend Error: {e}")

