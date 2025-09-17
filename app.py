import streamlit as st
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Any
from dotenv import load_dotenv
import os

from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

# ========== ENV & LLM CONFIG ==========
load_dotenv()
openai_key = os.getenv("OPENAI_API_KEY")
anthropic_key = os.getenv("ANTHROPIC_API_KEY")

gpt = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, api_key=openai_key)
claude = ChatAnthropic(model="claude-3-5-sonnet-20240620", temperature=0.7, api_key=anthropic_key)

# ========== DATABASE ==========
DB_PATH = "memory.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            pinned INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_message(role: str, content: str, pinned: bool = False):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory (timestamp, role, content, pinned) VALUES (?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), role, content, 1 if pinned else 0),
    )
    conn.commit()
    conn.close()

def load_recent(n: int = 8) -> List[str]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT timestamp, role, content FROM memory ORDER BY id DESC LIMIT ?", (n,))
    rows = cur.fetchall()
    conn.close()
    return [f"{r[0]} | {r[1]}: {r[2]}" for r in reversed(rows)]

def load_pinned() -> List[str]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT timestamp, role, content FROM memory WHERE pinned=1 ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return [f"{r[0]} | {r[1]}: {r[2]}" for r in rows]

# ========== AGENTS ==========
def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    dialogue = "\n".join([f"{t} | {r}: {c}" for t, r, c in state['history'][-3:]])
    prompt = f"Planner: propose next steps.\nDialogue:\n{dialogue}"
    resp = gpt.invoke(prompt)
    text = resp.content.strip()
    save_message("Planner", text)
    return {"history": state["history"] + [(datetime.now(timezone.utc).isoformat(), "Planner", text)]}

def critic_node(state: Dict[str, Any]) -> Dict[str, Any]:
    dialogue = "\n".join([f"{t} | {r}: {c}" for t, r, c in state['history'][-3:]])
    prompt = f"Critic: refine or critique.\nDialogue:\n{dialogue}"
    resp = claude.invoke(prompt)
    text = resp.content.strip()
    save_message("Critic", text)
    return {"history": state["history"] + [(datetime.now(timezone.utc).isoformat(), "Critic", text)]}

def meta_node(state: Dict[str, Any]) -> Dict[str, Any]:
    dialogue = "\n".join([f"{t} | {r}: {c}" for t, r, c in state['history'][-5:]])
    prompt = f"Meta-agent: summarize group thinking.\nDialogue:\n{dialogue}"
    resp = gpt.invoke(prompt)
    text = resp.content.strip()
    save_message("Meta", text)
    return {"history": state["history"] + [(datetime.now(timezone.utc).isoformat(), "Meta", text)]}

# ========== WORKFLOW ==========
workflow = StateGraph(dict)
workflow.add_node("planner", planner_node)
workflow.add_node("critic", critic_node)
workflow.add_node("meta", meta_node)

workflow.add_edge(START, "planner")   # entrypoint
workflow.add_edge("planner", "critic")
workflow.add_edge("critic", "meta")
workflow.add_edge("meta", END)

app = workflow.compile()

# ========== STREAMLIT UI ==========
st.set_page_config(page_title="Multi-Agent System with Memory", layout="wide")
st.title("🤖 Multi-Agent System with Memory, Meta Identity, & Autonomy")

# Session state
if "history" not in st.session_state:
    st.session_state.history = []
if "running" not in st.session_state:
    st.session_state.running = False
if "meta_summary" not in st.session_state:
    st.session_state.meta_summary = []

# User input
user_input = st.text_input("Your message:")
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("▶️ Start"):
        if user_input.strip():
            st.session_state.history.append((datetime.now(timezone.utc).isoformat(), "User", user_input))
            save_message("User", user_input)
            st.session_state.last_user_input = user_input
        st.session_state.running = True
with col2:
    if st.button("⏹ Stop"):
        st.session_state.running = False
with col3:
    if st.button("📌 Pin Last"):
        if st.session_state.history:
            _, role, content = st.session_state.history[-1]
            save_message(role, content, pinned=True)

# Chat display
st.subheader("Conversation")
chat_box = st.empty()

def render_history():
    formatted = [f"{t} | {r}: {c}" for t, r, c in st.session_state.history]
    chat_box.text("\n".join(formatted))

render_history()

# Run loop
def run_cycles(n_cycles: int = 1):
    state = {"history": st.session_state.history, "user_input": st.session_state.get("last_user_input", "")}
    steps = max(4 * n_cycles, 4)
    for update in app.stream(state, {"recursion_limit": steps + 2}):
        if "history" in update:
            st.session_state.history = update["history"]
            render_history()
    # capture meta-summaries
    st.session_state.meta_summary.extend([h for h in st.session_state.history if h[1] == "Meta"])

if st.session_state.running:
    run_cycles(1)
    st.session_state.running = False

# Sidebar: memories + meta
st.sidebar.header("📌 Memory Browser")
st.sidebar.subheader("Pinned")
st.sidebar.write("\n".join(load_pinned()) or "(none pinned)")
st.sidebar.subheader("Recent")
st.sidebar.write("\n".join(load_recent(10)))

st.sidebar.header("🧠 Meta Summaries")
meta_out = "\n".join([f"{t} | {r}: {c}" for t, r, c in st.session_state.meta_summary])
st.sidebar.write(meta_out or "(none yet)")
