import streamlit.components.v1 as components
from pyvis.network import Network
import streamlit as st
import requests


st.set_page_config(
    page_title="클라우드",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# Backend =================
BACKEND_URL = "http://localhost:5000/chat"
# Backend =================


# Session State ===========
if "history" not in st.session_state:
    st.session_state.history = []

if "messages" not in st.session_state:
    st.session_state.messages = []

if "rag_on" not in st.session_state:
    st.session_state.rag_on = False
# Session State ===========


# PyVis Graph Function ====
def create_network_graph(graph_data, has_center=False):

    net = Network(
        height="650px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#222222",
        directed=False
    )

    center_name = graph_data.get("center") if has_center else None

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
    # Nodes
    # =========================
    for idx, node in enumerate(graph_data.get("nodes", [])):

        node_id = node["id"]
        node_name = node.get("name", node_id)

        is_center_node = (
            has_center
            and center_name is not None
            and node_name == center_name
        )

        if is_center_node:
            node_color = {
                "background": "#f2f2f2",
                "border": "#cfcfcf"
            }
            font_size = 34
            border_width = 2
            title = f"<b>{node_name}</b><br>중심 노드"
        else:
            node_color = pastel_colors[idx % len(pastel_colors)]
            font_size = 20
            border_width = 1
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
            borderRadius=999,
            widthConstraint={
                "minimum": 80 if is_center_node else 70
            },
            heightConstraint={
                "minimum": 42 if is_center_node else 35
            },
            title=title
        )

    # =========================
    # Links
    # =========================
    for link in graph_data.get("links", []):

        source = link["source"]
        target = link["target"]
        relation = link.get("relation", "")

        edge_base_node = source
        edge_color = node_color_map.get(
            edge_base_node,
            {"border": "#7aa7ff"}
        )["border"]

        net.add_edge(
            source,
            target,
            label=relation,
            width=3,
            color={
                "color": edge_color,
                "highlight": edge_color,
                "hover": edge_color
            },
            arrows="",
            font={
                "size": 18,
                "align": "top",
                "color": "#111827",
                "strokeWidth": 8,
                "strokeColor": "#ffffff"
            },
            title=f"관계: {relation}"
        )

    # =========================
    # Options
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
# PyVis Graph Function ====


# CSS 제거 ================
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
# CSS 제거 ================


# RAG Toggle ==============
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
# RAG Toggle ==============


# CSS =====================
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
    top: 40%;
    transform: translate(-50%, -50%);
    font-size: clamp(24px, 4vw, 34px);
}}

.main-title.top {{
    top: 60px;
    font-size: clamp(22px, 3.5vw, 34px);
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
/* =========================
   PC Sidebar Offset
========================= */
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
# CSS =====================


# Sidebar =================
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
                st.session_state.rag_on = item.get("rag_on", st.session_state.rag_on)
                st.rerun()
# Sidebar =================


# Main UI =================
is_chat_started = len(st.session_state.messages) > 0

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
        st.markdown(
            """
            <div class="network-card">
                <div class="network-title">관계 그래프</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        components.html(msg["content"], height=680)


# Chat Input ==============
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

            has_center = data.get("center", False)
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
                graph_html = create_network_graph(
                    graph_data=graph_data,
                    has_center=has_center
                )

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


# Footer ==================
st.markdown(
    '<div class="fixed-footer">기업 관계 분석 전문 서비스입니다. 관련 질문을 입력해 주세요.</div>',
    unsafe_allow_html=True
)