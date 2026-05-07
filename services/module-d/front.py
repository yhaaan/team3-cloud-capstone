import streamlit as st

st.set_page_config(
    page_title="클라우드",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

import requests
import streamlit.components.v1 as components
from pyvis.network import Network


# =========================
# Backend
# =========================
BACKEND_URL = "http://localhost:5000/chat"


# =========================
# Session State
# =========================
if "history" not in st.session_state:
    st.session_state.history = []

if "messages" not in st.session_state:
    st.session_state.messages = []

if "rag_on" not in st.session_state:
    st.session_state.rag_on = False

# =========================
# PyVis Graph Function
# =========================
def create_network_graph(graph_data):

    net = Network(
        height="650px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#222222",
        directed=False
    )

    center = graph_data.get("center", "중심 기업")

    pastel_colors = [
        {"background": "#e8f0ff", "border": "#7aa7ff"},
        {"background": "#e8fff1", "border": "#67d391"},
        {"background": "#fff4e8", "border": "#ffb366"},
        {"background": "#f3e8ff", "border": "#bb86fc"},
        {"background": "#ffe8ef", "border": "#ff8fb1"},
        {"background": "#e8fbff", "border": "#5ccfe6"},
    ]

    node_color_map = {}

    # =========================
    # 중심 기업
    # =========================
    node_color_map[center] = {
        "background": "#f2f2f2",
        "border": "#cfcfcf"
    }

    net.add_node(
        center,
        label=center,
        shape="ellipse",

        color=node_color_map[center],

        font={
            "color": "#111111",
            "size": 48,
            "face": "Arial",
            "bold": True
        },

        borderWidth=1.5,
        borderRadius=999,
        widthConstraint={
            "minimum": 80
        },
        heightConstraint={
            "minimum": 40
        },

        title=f"<b>{center}</b><br>중심 기업"
    )

    # =========================
    # 주변 기업
    # =========================
    for idx, node in enumerate(graph_data.get("nodes", [])):

        share = node.get("share", 10)
        label = node.get("label", node["id"])

        node_color = pastel_colors[idx % len(pastel_colors)]

        node_color_map[node["id"]] = node_color

        net.add_node(
            node["id"],
            label=label,
            shape="ellipse",

            color=node_color,

            font={
                "color": "#1f2937",
                "size": 200,
                "face": "Arial",
                "bold": True
            },
            borderWidth=1,
            borderRadius=999,
            widthConstraint={
                "minimum": 70
            },
            heightConstraint={
                "minimum": 35
            },

            title=f"<b>{label}</b><br>지분율: {share}%"
        )

    # =========================
    # 간선
    # =========================
    for edge in graph_data.get("edges", []):

        share = edge.get("share", 10)

        from_id = edge["from"]
        to_id = edge["to"]

        # 선 색 = 연결된 노드 색
        if from_id == center:
            edge_base_node = to_id
        else:
            edge_base_node = from_id

        edge_color = node_color_map.get(
            edge_base_node,
            {"border": "#7aa7ff"}
        )["border"]

        net.add_edge(
            from_id,
            to_id,

            label=edge.get("label", f"{share}%"),

            width=max(4, share / 4),

            color={
                "color": edge_color,
                "highlight": edge_color,
                "hover": edge_color
            },

            arrows="",

            font={
                "size": 22,
                "align": "top",
                "color": "#111827",
                "strokeWidth": 8,
                "strokeColor": "#ffffff"
            },

            title=f"지분율: {share}%"
        )

    # =========================
    # 전체 옵션
    # =========================
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
      "nodeDistance": 50,
      "centralGravity": 0.08,
      "springLength": 150,
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

    return net.generate_html()

# =========================
# RAG Toggle Button
# =========================
st.markdown('<div class="rag-btn">', unsafe_allow_html=True)
clicked = st.button("", key="rag_toggle_btn")
st.markdown('</div>', unsafe_allow_html=True)

if clicked:
    st.session_state.rag_on = not st.session_state.rag_on
    st.rerun()

state_class = "on" if st.session_state.rag_on else "off"


# =========================
# CSS
# =========================
st.markdown(f"""
<style>

#MainMenu {{
    visibility: hidden;
}}
.stAppDeployButton {{
    visibility: hidden;
}}


/* =========================
   App 기본 스타일
========================= */
.stApp {{
    background-color: #ffffff;
    color: #323232;
}}

.block-container {{
    padding-top: 6rem;
    max-width: 950px;
}}


/* =========================
   RAG Toggle
========================= */
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


/* =========================
   사이드바 상태별 중앙 정렬
========================= */
[data-testid="stSidebar"][aria-expanded="true"] ~ div .main-title {{
    left: calc(50% + 162px);
}}

[data-testid="stSidebar"][aria-expanded="false"] ~ div .main-title {{
    left: 50%;
}}

[data-testid="stSidebar"][aria-expanded="true"] ~ div .fixed-footer {{
    transform: translateX(calc(-50% + 162px));
}}

[data-testid="stSidebar"][aria-expanded="false"] ~ div .fixed-footer {{
    transform: translateX(-50%);
}}


/* =========================
   Title
========================= */
.main-title {{
    position: fixed;
    left: 50%;
    transition: all 0.36s;

    font-weight: 800;
    color: #323232;
    text-align: center;
    white-space: nowrap;
    z-index: 9999;
}}

.main-title.center {{
    top: 40%;
    transform: translate(-50%, -50%);
    font-size: 34px;
}}

.main-title.top {{
    top: 60px;
    transform: translateX(-50%);
    font-size: 34px;
}}

.title-blur-zone {{
    position: fixed;
    top: 58px;
    left: 0;
    width: 100%;
    height: 130px;

    background: linear-gradient(
        to bottom,
        #ffffff 0%,
        #ffffff 60%,
        rgba(255,255,255,0) 100%
    );

    z-index: 9998;
    pointer-events: none;
}}


/* =========================
   Message
========================= */
.answer-box {{
    width: 100%;
    background: #ffffff;
    border-top: 1px solid #e8e8e8;
    padding: 28px 8px;
    margin-top: 30px;
    font-size: 16px;
    line-height: 1.8;
    color: #000000;
}}

.question-box {{
    background: #f8f8f8;
    border: 1px solid #e8e8e8;
    border-radius: 16px;
    padding: 16px 20px;
    margin-top: 24px;
    font-size: 16px;
    color: #323232;
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


/* =========================
   Network Graph
========================= */
.network-card {{
    width: 100%;
    background: #ffffff;
    border: 1px solid #e8e8e8;
    border-radius: 22px;
    padding: 14px;
    margin-top: 18px;
    box-shadow: 0 12px 30px rgba(7, 89, 201, 0.08);
}}

.network-title {{
    font-size: 15px;
    font-weight: 800;
    color: #323232;
    margin: 4px 0 12px 4px;
}}


/* =========================
   Sidebar
========================= */
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


/* =========================
   Chat Input
========================= */
.stChatInput {{
    max-width: 700px;
    margin: 0 auto;
    transition: all 0.36s;
}}

body:not(:has(.question-box)) [data-testid="stChatInput"] {{
    transform: translateY(-920%);
}}


/* =========================
   Footer
========================= */
.fixed-footer {{
    position: fixed;
    bottom: 30px;
    left: 50%;
    font-size: 12px;
    color: #999999;
    z-index: 9999;
    pointer-events: none;

    transform: translateX(-50%);
    transition: all 0.36s;
}}
</style>

<div class="rag-toggle {state_class}">
    <div class="rag-slider"></div>
    <div class="rag-text">RAG</div>
</div>
""", unsafe_allow_html=True)


# =========================
# Sidebar
# =========================
with st.sidebar:
    st.markdown("## 클라우드")
    st.markdown("---")

    if st.button("새 질문"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("### 이전 검색 기록")

    if len(st.session_state.history) == 0:
        st.caption("아직 질문 기록이 없습니다.")
    else:
        for idx, item in enumerate(st.session_state.history):
            q = item["question"]
            short_q = q if len(q) <= 24 else q[:24] + "..."

            if st.button(short_q, key=f"history_{idx}"):
                st.session_state.messages = item["messages"]
                st.rerun()


# =========================
# Main UI
# =========================
is_chat_started = len(st.session_state.messages) > 0
title_class = "main-title top" if is_chat_started else "main-title center"

st.markdown(
    f'<div class="{title_class}">상장사 복합 관계 분석 서비스</div>',
    unsafe_allow_html=True
)

if is_chat_started:
    st.markdown('<div class="title-blur-zone"></div>', unsafe_allow_html=True)


for msg in st.session_state.messages:
    msg_type = msg.get("type", "text")

    if msg_type == "text":
        if msg["role"] == "user":
            st.markdown(
                f'<div class="question-box">{msg["content"]}</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f'<div class="answer-box">{msg["content"].replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True
            )

    elif msg_type == "network":
        components.html(msg["content"], height=680)


# =========================
# Chat Input
# =========================
question = st.chat_input("질문을 입력하세요")

if question:
    st.session_state.messages.append({
        "role": "user",
        "type": "text",
        "content": question
    })

    with st.spinner("답변을 생성하는 중입니다..."):
        try:
            response = requests.post(
                BACKEND_URL,
                json={
                    "question": question,
                    "rag_on": st.session_state.rag_on
                },
                timeout=30
            )

            response.raise_for_status()
            data = response.json()

            answer = data.get("answer", "답변을 받지 못했습니다.")
            graph_data = data.get("graph")

            answer += f"""

현재 RAG 상태: {"ON" if st.session_state.rag_on else "OFF"}
"""

            st.session_state.messages.append({
                "role": "assistant",
                "type": "text",
                "content": answer
            })

            if graph_data:
                graph_html = create_network_graph(graph_data)

                st.session_state.messages.append({
                    "role": "assistant",
                    "type": "network",
                    "content": graph_html
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
        "question": question,
        "messages": st.session_state.messages.copy(),
        "rag_on": st.session_state.rag_on
    })

    st.session_state.history = st.session_state.history[:10]

    st.rerun()


# =========================
# Footer
# =========================
st.markdown(
    '<div class="fixed-footer">기업 관계 분석 전문 서비스입니다. 관련 질문을 입력해 주세요.</div>',
    unsafe_allow_html=True
)