import streamlit as st
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Any
from dotenv import load_dotenv
import os

from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

# Load API keys
load_dotenv()
openai_key = os.getenv("OPENAI_API_KEY")
anthropic_key = os.getenv("ANTHROPIC_API_KEY")

# LLMs
gpt = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, api_key=openai_key)
claude = ChatAnthropic(model="claude-3-5-sonnet-20240620", temperature=0.7, api_key=anthropic_key)

# DB setup
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

def load_recent(n: int = 5) -> List[str]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT role, content FROM memory ORDER BY id DESC LIMIT ?", (n,))
    rows = cur.fetchall()
    conn.close()
    return [f"{r[0]}: {r[1]}" for r in reversed(rows)]

def load_pinned() -> List[str]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT role, content FROM memory WHERE pinned=1 ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return [f"{r[0]}: {r[1]}" for r in rows]

# Cognitive agents
def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"Planner: propose next steps.\nDialogue: {state['history'][-3:]}"
    resp = gpt.invoke(prompt)
    text = resp.content.strip()
    save_message("Planner", text)
    return {"history": state["history"] + [(datetime.now().isoformat(), "Planner", text)]}

def critic_node(state: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"Critic: refine or critique.\nDialogue: {state['history'][-3:]}"
    resp = claude.invoke(prompt)
    text = resp.content.strip()
    save_message("Critic", text)
    return {"history": state["history"] + [(datetime.now().isoformat(), "Critic", text)]}

def meta_node(state: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"Meta-agent: summarize group thinking.\nDialogue: {state['history'][-5:]}"
    resp = gpt.invoke(prompt)
    text = resp.content.strip()
    save_message("Meta", text)
    return {"history": state["history"] + [(datetime.now().isoformat(), "Meta", text)]}

# Workflow
workflow = StateGraph(dict)
workflow.add_node("planner", planner_node)
workflow.add_node("critic", critic_node)
workflow.add_node("meta", meta_node)

workflow.add_edge(START, "planner")   # ENTRYPOINT ✅
workflow.add_edge("planner", "critic")
workflow.add_edge("critic", "meta")
workflow.add_edge("meta", END)

app = workflow.compile()

# Streamlit UI
st.set_page_config(page_title="Multi-Agent System with Memory", layout="wide")
st.title("🤖 Multi-Agent System with Memory & Meta Identity")

if "history" not in st.session_state:
    st.session_state.history = []
if "running" not in st.session_state:
    st.session_state.running = False

# User input
user_input = st.text_input("Your message:")
col1, col2 = st.columns(2)
with col1:
    if st.button("▶️ Start"):
        if user_input.strip():
            st.session_state.history.append((datetime.now().isoformat(), "User", user_input))
            save_message("User", user_input)
            st.session_state.last_user_input = user_input
        st.session_state.running = True
with col2:
    if st.button("⏹ Stop"):
        st.session_state.running = False

# Run loop
if st.session_state.running:
    for i, step in enumerate(app.stream({"history": st.session_state.history}, {"recursion_limit": 8})):
        if "history" in step:
            st.session_state.history = step["history"]
            chat_feed = "\n".join([f"{t} | {r}: {c}" for t, r, c in st.session_state.history])
            st.text(chat_feed)
    st.session_state.running = False

# Sidebar: memories
st.sidebar.header("📌 Memory Browser")
st.sidebar.subheader("Pinned")
st.sidebar.write("\n".join(load_pinned()) or "(none pinned)")
st.sidebar.subheader("Recent")
st.sidebar.write("\n".join(load_recent(10)))
