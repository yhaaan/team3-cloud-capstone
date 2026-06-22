import json

import streamlit.components.v1 as components
from pyvis.network import Network
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import uuid
import copy

st.set_page_config(
    page_title="클라우드",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

BACKEND_URL = "http://127.0.0.1:8000/chat"

if "history" not in st.session_state:
    st.session_state.history = []

if "messages" not in st.session_state:
    st.session_state.messages = []

if "rag_on" not in st.session_state:
    st.session_state.rag_on = False

if "scroll_to_top" not in st.session_state:
    st.session_state.scroll_to_top = False

if "scroll_target_id" not in st.session_state:
    st.session_state.scroll_target_id = None


PASTEL_COLORS = [
    {"background": "#e8f0ff", "border": "#7aa7ff"},
    {"background": "#e8fff1", "border": "#67d391"},
    {"background": "#fff4e8", "border": "#ffb366"},
    {"background": "#f3e8ff", "border": "#bb86fc"},
    {"background": "#ffe8ef", "border": "#ff8fb1"},
    {"background": "#e8fbff", "border": "#5ccfe6"},
]

PLOTLY_COLORS = [color["background"] for color in PASTEL_COLORS]
PLOTLY_LINE_COLORS = [color["border"] for color in PASTEL_COLORS]


def create_network_graph(graph_data, how):
    is_center_graph = how == "netcenter"

    net = Network(
        height="650px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#222222",
        directed=not is_center_graph
    )

    center_id = graph_data.get("center") if is_center_graph else None
    node_color_map = {}

    for idx, node in enumerate(graph_data.get("nodes", [])):
        node_id = node.get("id")
        node_name = node.get("name", node.get("label", node_id))

        if not node_id:
            continue

        is_center_node = (
            is_center_graph
            and center_id is not None
            and node_id == center_id
        )

        if is_center_node:
            node_color = {
                "background": "#f2f2f2",
                "border": "#cfcfcf"
            }
            font_size = 34
            border_width = 3
            min_width = 90
            min_height = 46
            title = f"<b>{node_name}</b><br>중심 노드"
        else:
            node_color = PASTEL_COLORS[idx % len(PASTEL_COLORS)]
            font_size = 20
            border_width = 1
            min_width = 70
            min_height = 35
            title = f"<b>{node_name}</b>"

        node_color_map[node_id] = node_color

        net.add_node(
            node_id,
            label=node_name,
            shape="ellipse",
            color=node_color,
            font={
                "color": "#111111" if is_center_node else "#1f2937",
                "size": font_size,
                "face": "Arial",
                "bold": True
            },
            borderWidth=border_width,
            widthConstraint={"minimum": min_width},
            heightConstraint={"minimum": min_height},
            title=title
        )

    links = graph_data.get("links", graph_data.get("linkes", []))

    for link in links:
        source = link.get("source")
        target = link.get("target")
        relation = link.get("relation", link.get("label", ""))

        if not source or not target:
            continue

        edge_color = node_color_map.get(
            source,
            {"border": "#7aa7ff"}
        )["border"]

        net.add_edge(
            source,
            target,
            label=relation,
            width=5,
            color={
                "color": edge_color,
                "highlight": edge_color,
                "hover": edge_color
            },
            arrows="to",
            arrowStrikethrough=False,
            font={
                "size": 18,
                "align": "top",
                "color": "#111827",
                "strokeWidth": 8,
                "strokeColor": "#ffffff"
            },
            title=f"관계: {relation}"
        )

    net.set_options("""
    const options = {
      "nodes": {
        "shape": "ellipse",
        "shadow": {
          "enabled": true,
          "color": "rgba(0,0,0,0.12)",
          "size": 10,
          "x": 2,
          "y": 4
        }
      },
      "edges": {
        "smooth": {
          "enabled": false
        },
        "length": 400
      },
      "physics": {
        "enabled": true,
        "solver": "repulsion",
        "stabilization": {
          "enabled": true,
          "iterations": 220,
          "fit": true
        },
        "repulsion": {
          "nodeDistance": 120,
          "centralGravity": 0.08,
          "springLength": 180,
          "springConstant": 0.03
        }
      },
      "interaction": {
        "hover": true,
        "dragNodes": true,
        "zoomView": true,
        "dragView": true
      }
    }
    """)

    html = net.generate_html()

    search_script = """
    <script>
    network.on("click", function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const node = nodes.get(nodeId);

            if (node && node.label) {
                const query = encodeURIComponent(node.label);
                window.open("https://www.google.com/search?q=" + query, "_blank");
            }
        }
    });
    </script>
    """

    html = html.replace("</body>", search_script + "</body>")
    return html


def create_plotly_graph(graph_data, how):
    title = graph_data.get("title", "")

    if how == "pie":
        df = pd.DataFrame({
            "label": graph_data.get("labels", []),
            "value": graph_data.get("values", [])
        })

        fig = px.pie(
            df,
            names="label",
            values="value",
            title=title,
            color_discrete_sequence=PLOTLY_COLORS
        )

        fig.update_traces(
            hole=0.42,
            pull=[0.02] * len(df),
            textinfo="percent+label",
            textposition="inside",
            marker=dict(
                line=dict(
                    color="white",
                    width=2
                )
            )
        )

    elif how == "bar":
        labels = graph_data.get("labels", {
            "x": "x",
            "y": "y"
        })

        df = pd.DataFrame({
            "x": graph_data.get("x", []),
            "y": graph_data.get("y", [])
        })

        fig = px.bar(
            df,
            x="x",
            y="y",
            text="y",
            color="x",
            title=title,
            labels=labels,
            color_discrete_sequence=PLOTLY_COLORS
        )

        fig.update_traces(
            textposition="outside",
            marker=dict(
                line=dict(
                    color="white",
                    width=1.5
                )
            )
        )

    elif how == "line":
        labels = graph_data.get("labels", {
            "x": "x",
            "y": "y",
            "name": "name"
        })

        rows = []

        for item in graph_data.get("data", []):
            name = item.get("name", "데이터")
            x_values = item.get("x", [])
            y_values = item.get("y", [])

            for x, y in zip(x_values, y_values):
                rows.append({
                    "x": x,
                    "y": y,
                    "name": name
                })

        df = pd.DataFrame(rows)

        fig = px.line(
            df,
            x="x",
            y="y",
            color="name",
            markers=True,
            title=title,
            labels=labels,
            color_discrete_sequence=PLOTLY_LINE_COLORS
        )

        fig.update_traces(
            line=dict(width=3),
            marker=dict(size=8)
        )

        fig.update_layout(
            legend_title_text=labels.get("name", "name")
        )

    else:
        return None

    fig.update_layout(
        height=520,
        margin=dict(l=30, r=30, t=60, b=30),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(
            family="Arial",
            size=14,
            color="#323232"
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)"
        ),
        showlegend=False if how in ["pie", "bar"] else True
    )

    if how != "pie":
        fig.update_xaxes(
            showgrid=True,
            gridcolor="#eeeeee",
            zeroline=False
        )

        fig.update_yaxes(
            showgrid=True,
            gridcolor="#eeeeee",
            zeroline=False
        )

    return fig


st.markdown("""
<style>
    #MainMenu {
        visibility: hidden;
    }

    .stAppDeployButton {
        visibility: hidden;
    }
</style>
""", unsafe_allow_html=True)


st.markdown('<div class="rag-btn">', unsafe_allow_html=True)
clicked = st.button("", key="rag_toggle_btn")
st.markdown('</div>', unsafe_allow_html=True)

if clicked:
    st.session_state.rag_on = not st.session_state.rag_on
    st.rerun()

state_class = "on" if st.session_state.rag_on else "off"


st.markdown(f"""
<style>
    .st-key-rag_toggle_btn {{
        position: fixed !important;
        top: 60px !important;
        right: 26px !important;
        width: 88px !important;
        height: 31px !important;
        z-index: 10001 !important;
    }}

    .st-key-rag_toggle_btn button {{
        width: 88px !important;
        height: 31px !important;
        border-radius: 999px !important;
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        color: transparent !important;
        box-shadow: none !important;
        cursor: pointer !important;
    }}

    .st-key-rag_toggle_btn button:hover,
    .st-key-rag_toggle_btn button:focus,
    .st-key-rag_toggle_btn button:active {{
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
    }}

    .rag-toggle {{
        position: fixed;
        top: 60px;
        right: 26px;
        width: 88px;
        height: 31px;
        border-radius: 999px;
        background: #333333;
        overflow: hidden;
        z-index: 10000;
        pointer-events: none;
        transition: background 0.25s ease;
    }}

    .rag-toggle.on {{
        background: #0759c9;
    }}

    .rag-slider {{
        position: absolute;
        top: 3.4px;
        left: 3px;
        width: 40px;
        height: 24px;
        border-radius: 999px;
        background: #f5f5f5;
        z-index: 2;
        transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
    }}

    .rag-toggle.on .rag-slider {{
        transform: translateX(42px);
    }}

    .rag-text {{
        position: absolute;
        top: 50%;
        transform: translateY(-50%);
        color: white;
        font-size: 16px;
        font-weight: 800;
        z-index: 1;
    }}

    .rag-toggle.off .rag-text {{
        right: 12px;
    }}

    .rag-toggle.on .rag-text {{
        left: 12px;
    }}
</style>
""", unsafe_allow_html=True)


st.markdown(f"""
<style>
.stApp {{
    background-color: #ffffff;
    color: #323232;
}}

.block-container {{
    max-width: 950px;
    padding-top: 6rem;
    padding-left: 1.2rem;
    padding-right: 1.2rem;
    padding-bottom: 120px;
}}

.main-title {{
    position: fixed;
    left: 50%;
    transform: translateX(-50%);
    font-weight: 800;
    color: #323232;
    text-align: center;
    white-space: nowrap;
    z-index: 9999;
    transition: top 0.36s ease, font-size 0.36s ease;
}}

.main-title.center {{
    top: 35%;
    transform: translate(-50%, -50%);
    font-size: clamp(24px, 4vw, 34px);
    transition:
        top 0.28s ease,
        transform 0.28s ease,
        font-size 0.28s ease;
}}      

.main-title.top {{
    top: 60px;
    font-size: clamp(24px, 4vw, 34px);
}}

.title-blur-zone {{
    position: fixed;
    top: 50px;
    left: 0;
    width: 100%;
    height: 140px;
    background: linear-gradient(
        to bottom,
        #ffffff 0%,
        #ffffff 65%,
        rgba(255,255,255,0) 100%
    );
    z-index: 9998;
    pointer-events: none;
}}

.question-box {{
    background: #f8f8f8;
    border: 1px solid #e8e8e8;
    border-radius: 16px;
    padding: 16px 20px;
    margin-top: 24px;
    font-size: 16px;
    color: #323232;
    scroll-margin-top: 120px;
}}

.answer-box {{
    width: 100%;
    background: #ffffff;
    border: 1px solid #e5e5e5;
    border-radius: 22px;
    padding: 15px 15px;
    margin-top: 30px;
    font-size: 16px;
    line-height: 1.8;
    color: #000000;
}}

.warning-box {{
    background: #fff8e6;
    border: 1px solid #ffd666;
    border-radius: 12px;
    padding: 14px 18px;
    margin-top: 16px;
    color: #323232;
    font-weight: 600;
}}

[data-testid="stSidebar"] {{
    background-color: #fcfdff;
    border-right: 1px solid #e8e8e8;
}}

.stButton > button {{
    width: 100%;
    border-radius: 12px;
    border: none;
    background-color: #ffffff;
    color: #323232;
    font-size: 15px;
    padding: 10px;
}}

.stButton > button:hover {{
    background-color: #e6edfd;
    color: #004aad;
}}

[data-testid="stChatInput"] {{
    max-width: 700px;
    margin: 0 auto;
}}

body:not(:has(.question-box)) [data-testid="stChatInput"] {{
    position: fixed;
    top: 50%;
    left: 50%;
    bottom: auto;
    width: min(700px, 92vw);
    transform: translate(-50%, -50%);
    z-index: 9997;
}}

body:has(.question-box) [data-testid="stChatInput"] {{
    position: fixed;
    left: 50%;
    bottom: 70px;
    width: min(700px, 92vw);
    transform: translateX(-50%);
    z-index: 9997;
}}

.fixed-footer {{
    position: fixed;
    bottom: 30px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 12px;
    color: #999999;
    z-index: 9996;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    pointer-events: none;
}}

@media (min-width: 769px) {{

    :root {{
        --sidebar-offset: 0px;
    }}

    body:has([data-testid="stSidebar"][aria-expanded="true"]) {{
        --sidebar-offset: 160px;
    }}

    .main-title {{
        left: calc(50% + var(--sidebar-offset));

        transition:
            left 300ms ease,
            top 0.36s ease,
            font-size 0.36s ease;
    }}

    body:not(:has(.question-box)) [data-testid="stChatInput"] {{
        left: calc(50% + var(--sidebar-offset));

        transition:
            left 300ms ease,
            top 300ms ease,
            transform 300ms ease;
    }}

    body:has(.question-box) [data-testid="stChatInput"] {{
        left: calc(50% + var(--sidebar-offset));

        transition:
            left 300ms ease,
            bottom 300ms ease,
            transform 300ms ease;
    }}

    .fixed-footer {{
        left: calc(50% + var(--sidebar-offset));

        transition: left 300ms ease;
    }}
}}

@media (max-width: 768px) {{
    .block-container {{
        padding-top: 5rem;
        padding-left: 1rem;
        padding-right: 1rem;
        padding-bottom: 100px;
    }}

    .main-title.center {{
        top: 40%;
        font-size: clamp(25px, 7vw, 34px);
        width: 92vw;
        white-space: normal;
        line-height: 1.25;
    }}

    .main-title.top {{
        top: 20px;
        width: 92vw;
        font-size: clamp(20px, 3vw, 22px);
        white-space: normal;
        line-height: 1.25;
    }}

    body:not(:has(.question-box)) [data-testid="stChatInput"] {{
        top: 50%;
        width: 92vw;
    }}

    body:has(.question-box) [data-testid="stChatInput"] {{
        bottom: max(14px, env(safe-area-inset-bottom));
        width: 92vw;
    }}

    .fixed-footer {{
        display: none !important;
    }}

    .st-key-rag_toggle_btn {{
        top: 82px !important;
        right: 20px !important;
        width: 76px !important;
        height: 28px !important;
    }}

    .st-key-rag_toggle_btn button {{
        width: 76px !important;
        height: 28px !important;
    }}

    .rag-toggle {{
        top: 82px;
        right: 20px;
        width: 76px;
        height: 28px;
    }}

    .rag-slider {{
        top: 3px;
        left: 3px;
        width: 34px;
        height: 22px;
    }}

    .rag-toggle.on .rag-slider {{
        transform: translateX(36px);
    }}

    .rag-text {{
        font-size: 14px;
    }}

    .rag-toggle.off .rag-text {{
        right: 9px;
    }}

    .rag-toggle.on .rag-text {{
        left: 9px;
    }}
}}
</style>

<div class="rag-toggle {state_class}">
    <div class="rag-slider"></div>
    <div class="rag-text">RAG</div>
</div>
""", unsafe_allow_html=True)


with st.sidebar:
    st.markdown("## 클라우드")
    st.markdown("---")

    if st.button("새 질문"):
        st.session_state.messages = []
        st.session_state.scroll_to_top = True
        st.session_state.scroll_target_id = None
        st.rerun()

    st.markdown("### 이전 검색 기록")

    if len(st.session_state.history) == 0:
        st.caption("아직 질문 기록이 없습니다.")
    else:
        for item in st.session_state.history:
            q = item["question"]
            short_q = q if len(q) <= 24 else q[:24] + "..."

            history_id = item.get("id")

            if history_id is None:
                history_id = str(uuid.uuid4())
                item["id"] = history_id

            if st.button(
                short_q,
                key=f"history_{history_id}"
            ):
                st.session_state.messages = copy.deepcopy(
                    item["messages"]
                )

                st.session_state.rag_on = item.get(
                    "rag_on",
                    st.session_state.rag_on
                )

                st.session_state.scroll_target_id = item.get("target_id")
                st.session_state.scroll_to_top = False

                st.rerun()


is_chat_started = len(st.session_state.messages) > 0

if st.session_state.scroll_to_top:
    components.html(
        """
        <script>
        const scrollTop = () => {
            window.parent.scrollTo({
                top: 0,
                behavior: "instant"
            });

            window.parent.document.documentElement.scrollTop = 0;
            window.parent.document.body.scrollTop = 0;
        };

        scrollTop();

        setTimeout(scrollTop, 50);
        setTimeout(scrollTop, 150);
        setTimeout(scrollTop, 300);
        </script>
        """,
        height=0
    )

    st.session_state.scroll_to_top = False


if not is_chat_started:
    st.markdown(
        """
        <div class="main-title center">
            상장사 복합 관계 분석 서비스
        </div>
        """,
        unsafe_allow_html=True
    )
else:
    st.markdown(
        """
        <div class="main-title top">
            상장사 복합 관계 분석 서비스
        </div>
        """,
        unsafe_allow_html=True
    )

if is_chat_started:
    st.markdown('<div class="title-blur-zone"></div>', unsafe_allow_html=True)


for msg in st.session_state.messages:
    msg_type = msg.get("type", "text")

    if msg_type == "text":
        if msg["role"] == "user":
            msg_id = msg.get("msg_id", "")

            st.markdown(
                f'<div id="msg-{msg_id}" class="question-box">{msg["content"]}</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f'<div class="answer-box">\n\n{msg["content"]}\n\n</div>',
                unsafe_allow_html=True
            )

    elif msg_type == "network":
        components.html(msg["content"], height=680)

    elif msg_type == "plotly":
        st.plotly_chart(
            msg["content"],
            use_container_width=True
        )


if st.session_state.scroll_target_id:
    target_id = st.session_state.scroll_target_id

    components.html(
        f"""
        <script>
        const scrollToTarget = () => {{
            const el = window.parent.document.getElementById("msg-{target_id}");

            if (el) {{
                el.scrollIntoView({{
                    behavior: "instant",
                    block: "start"
                }});

                window.parent.scrollBy(0, -100);
            }}
        }};

        scrollToTarget();

        setTimeout(scrollToTarget, 50);
        setTimeout(scrollToTarget, 150);
        setTimeout(scrollToTarget, 300);
        setTimeout(scrollToTarget, 500);
        </script>
        """,
        height=0
    )

    st.session_state.scroll_target_id = None


question = st.chat_input("질문을 입력하세요")

if question:
    user_msg_id = str(uuid.uuid4())

    st.session_state.messages.append({
        "role": "user",
        "type": "text",
        "content": question,
        "msg_id": user_msg_id
    })

    # 🚀 기존 st.spinner 대신 실시간 상태 갱신을 위해 st.status를 사용합니다.
    with st.status("시장 공시 및 다차원 기업 정보 분석 엔진 가동 중...", expanded=True) as status:
        status_text = st.empty()  # 텍스트가 바뀔 공간 확보
        
        try:
            recent_history = st.session_state.messages[:-1][-8:]

            # 🚀 stream=True 옵션을 반드시 주어 스트리밍 요청으로 받아야 합니다.
            response = requests.post(
                BACKEND_URL,
                json={
                    "question": question,
                    "rag_on": st.session_state.rag_on,
                    "recent_history": recent_history
                },
                stream=True,  # 🌟 핵심 수정
                timeout=150
            )

            response.raise_for_status()
            
            # 초기화용 변수들
            answer = ""
            how = None
            graph_data = None

            # 🚀 백엔드가 한 줄씩 던지는 JSON 청크를 실시간으로 파싱합니다.
            for line in response.iter_lines():
                if line:
                    data = json.loads(line.decode('utf-8'))
                    
                    # 1️⃣ 백엔드가 보낸 노드별 상태 메시지면 로딩 바 텍스트 변경
                    if data.get("type") == "status":
                        status_text.write(data.get("content"))
                    
                    # 2️⃣ 백엔드가 보낸 최종 답변 및 시각화 데이터 세트인 경우
                    elif data.get("type") == "answer":
                        # 만약 백엔드에서 통째로 보낸 형식이면 내부 content에서 꺼냄
                        if isinstance(data.get("content"), dict):
                            # 🚀 'content' 대신 'answer'로 키값을 수정합니다!
                            answer = data["content"].get("answer", "답변을 받지 못했습니다.")
                            how = data["content"].get("how")
                            graph_data = data["content"].get("graph")
                        else:
                            # 딕셔너리가 아닌 일반 문자열(RAG OFF 모드 등) 대응
                            answer = data.get("content", "답변을 받지 못했습니다.")
                            how = data.get("how")
                            graph_data = data.get("graph")
            
            # 성공적으로 종료되면 로딩바를 완료 상태로 닫아버립니다.
            status.update(label="✔️ 분석 및 답변 생성 완료!", state="complete", expanded=False)

            answer += f"""\n\n현재 RAG 상태: {"ON" if st.session_state.rag_on else "OFF"}"""

            st.session_state.messages.append({
                "role": "assistant",
                "type": "text",
                "content": answer
            })

            if graph_data and how:

                if how in ["network", "netcenter"]:
                    graph_html = create_network_graph(
                        graph_data=graph_data,
                        how=how
                    )

                    st.session_state.messages.append({
                        "role": "assistant",
                        "type": "network",
                        "content": graph_html
                    })

                elif how in ["pie", "bar", "line"]:
                    fig = create_plotly_graph(
                        graph_data=graph_data,
                        how=how
                    )

                    if fig is not None:
                        st.session_state.messages.append({
                            "role": "assistant",
                            "type": "plotly",
                            "content": fig
                        })

                else:
                    st.session_state.messages.append({
                        "role": "assistant",
                        "type": "text",
                        "content": f"지원하지 않는 그래프 형식입니다: {how}"
                    })

        except Exception as e:
            error_message = f"""
            ⚠️ 백엔드 서버와 연결할 수 없습니다.

            서버가 실행 중인지 확인해주세요.

            오류 내용:
            {e}

            현재 RAG 상태: {"ON" if st.session_state.rag_on else "OFF"}
            """

            st.session_state.messages.append({
                "role": "assistant",
                "type": "text",
                "content": error_message
            })

    st.session_state.messages = st.session_state.messages[-20:]

    st.session_state.history.insert(0, {
        "id": str(uuid.uuid4()),
        "question": question,
        "messages": copy.deepcopy(
            st.session_state.messages
        ),
        "rag_on": st.session_state.rag_on,
        "target_id": user_msg_id
    })

    st.session_state.history = st.session_state.history[:10]

    st.session_state.scroll_target_id = user_msg_id
    st.session_state.scroll_to_top = False

    st.rerun()


st.markdown(
    '<div class="fixed-footer">기업 관계 분석 전문 서비스입니다. 관련 질문을 입력해 주세요.</div>',
    unsafe_allow_html=True
)
