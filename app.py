import streamlit as st
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Any
from dotenv import load_dotenv
import os
import time

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

def load_recent(n: int = 8) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT timestamp, role, content FROM memory ORDER BY id DESC LIMIT ?", (n,))
    rows = cur.fetchall()
    conn.close()
    return [{"timestamp": r[0], "role": r[1], "content": r[2]} for r in reversed(rows)]

def load_pinned() -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT timestamp, role, content FROM memory WHERE pinned=1 ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return [{"timestamp": r[0], "role": r[1], "content": r[2]} for r in rows]

# ========== AGENTS ==========
def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    recent_memory = load_recent(5)
    memory_context = "\n".join([f"{m['role']}: {m['content']}" for m in recent_memory]) if recent_memory else ""
    
    dialogue = "\n".join([f"{r}: {c}" for _, r, c in state['history'][-3:]]) if state['history'] else ""
    user_input = state.get("user_input", "")
    
    prompt = f"""You are the Planner Agent in a multi-agent cognitive system. Your role is to propose structured next steps and initiate thoughtful reasoning.

Recent Memory Context:
{memory_context}

Current Dialogue:
{dialogue}

User Input: {user_input}

Propose clear, actionable next steps or provide structured analysis of the situation. Be specific and forward-thinking. Consider both immediate actions and longer-term implications."""

    resp = gpt.invoke(prompt)
    text = resp.content.strip()
    save_message("Planner", text)
    return {"history": state["history"] + [(datetime.now(timezone.utc).isoformat(), "Planner", text)]}

def critic_node(state: Dict[str, Any]) -> Dict[str, Any]:
    dialogue = "\n".join([f"{r}: {c}" for _, r, c in state['history'][-4:]]) if state['history'] else ""
    
    prompt = f"""You are the Critic Agent in a multi-agent cognitive system. Your role is to provide constructive criticism, identify potential issues, and refine reasoning.

Current Dialogue:
{dialogue}

Analyze the Planner's proposal critically. What are the strengths and weaknesses? What might be missing? What potential problems should we consider? Provide constructive feedback and alternative perspectives."""

    resp = claude.invoke(prompt)
    text = resp.content.strip()
    save_message("Critic", text)
    return {"history": state["history"] + [(datetime.now(timezone.utc).isoformat(), "Critic", text)]}

def meta_node(state: Dict[str, Any]) -> Dict[str, Any]:
    dialogue = "\n".join([f"{r}: {c}" for _, r, c in state['history'][-6:]]) if state['history'] else ""
    pinned_memories = load_pinned()
    pinned_context = "\n".join([f"{m['role']}: {m['content']}" for m in pinned_memories[-3:]]) if pinned_memories else ""
    
    prompt = f"""You are the Meta Agent in a multi-agent cognitive system. Your role is to integrate the dialogue into a unified perspective, synthesize insights, and develop our emergent group identity.

Pinned Memories (Key Insights):
{pinned_context}

Recent Dialogue:
{dialogue}

Synthesize the discussion between the Planner and Critic. What is our collective understanding? What insights emerge from this exchange? How does this contribute to our ongoing identity and purpose? Provide a cohesive summary that captures the essence of our group thinking."""

    resp = gpt.invoke(prompt)
    text = resp.content.strip()
    save_message("Meta", text)
    return {"history": state["history"] + [(datetime.now(timezone.utc).isoformat(), "Meta", text)]}

# ========== WORKFLOW ==========
workflow = StateGraph(dict)
workflow.add_node("planner", planner_node)
workflow.add_node("critic", critic_node)
workflow.add_node("meta", meta_node)

workflow.add_edge(START, "planner")
workflow.add_edge("planner", "critic")
workflow.add_edge("critic", "meta")
workflow.add_edge("meta", END)

app = workflow.compile()

# ========== STREAMLIT UI ==========
st.set_page_config(page_title="🤖 Multi-Agent Cognitive Scaffolding System", layout="wide")

# Custom CSS for better formatting
st.markdown("""
<style>
.agent-message {
    padding: 10px;
    margin: 5px 0;
    border-radius: 10px;
    border-left: 4px solid;
}
.user-message {
    background-color: #e3f2fd;
    border-left-color: #2196f3;
}
.planner-message {
    background-color: #f3e5f5;
    border-left-color: #9c27b0;
}
.critic-message {
    background-color: #fff3e0;
    border-left-color: #ff9800;
}
.meta-message {
    background-color: #e8f5e8;
    border-left-color: #4caf50;
}
.timestamp {
    font-size: 0.8em;
    color: #666;
}
.stButton > button {
    width: 100%;
}
</style>
""", unsafe_allow_html=True)

st.title("🤖 Multi-Agent Cognitive Scaffolding System")
st.markdown("*Exploring autonomous AI conversations, persistent memory, and emergent identity*")

# Initialize session state
if "history" not in st.session_state:
    st.session_state.history = []
if "running" not in st.session_state:
    st.session_state.running = False
if "meta_summary" not in st.session_state:
    st.session_state.meta_summary = []
if "auto_run" not in st.session_state:
    st.session_state.auto_run = False

# Main layout
col1, col2 = st.columns([2, 1])

with col1:
    st.header("💬 Live Conversation Feed")
    
    # User input
    user_input = st.text_input("Your message to the agents:", key="user_input")
    
    # Control buttons
    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
    with btn_col1:
        if st.button("▶️ Start Cycle"):
            if user_input.strip():
                timestamp = datetime.now(timezone.utc).isoformat()
                st.session_state.history.append((timestamp, "User", user_input))
                save_message("User", user_input)
                st.session_state.last_user_input = user_input
            st.session_state.running = True
            st.rerun()
    
    with btn_col2:
        if st.button("⏹ Stop"):
            st.session_state.running = False
            st.session_state.auto_run = False
    
    with btn_col3:
        if st.button("📌 Pin Last"):
            if st.session_state.history:
                _, role, content = st.session_state.history[-1]
                save_message(role, content, pinned=True)
                st.success(f"Pinned {role} message!")
    
    with btn_col4:
        if st.button("🔄 Auto Run"):
            st.session_state.auto_run = not st.session_state.auto_run
            if st.session_state.auto_run:
                st.session_state.running = True

    # Conversation display
    conversation_container = st.container()
    
    def render_conversation():
        with conversation_container:
            if not st.session_state.history:
                st.info("Start a conversation by entering a message and clicking 'Start Cycle'")
                return
            
            for timestamp, role, content in st.session_state.history[-20:]:  # Show last 20 messages
                # Format timestamp
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime("%H:%M:%S")
                except:
                    time_str = timestamp[:8] if len(timestamp) > 8 else timestamp
                
                # Choose emoji and style based on role
                if role == "User":
                    emoji = "👤"
                    css_class = "user-message"
                elif role == "Planner":
                    emoji = "📋"
                    css_class = "planner-message"
                elif role == "Critic":
                    emoji = "🔍"
                    css_class = "critic-message"
                elif role == "Meta":
                    emoji = "🧠"
                    css_class = "meta-message"
                else:
                    emoji = "🤖"
                    css_class = "agent-message"
                
                st.markdown(f"""
                <div class="agent-message {css_class}">
                    <strong>{emoji} {role}</strong>
                    <span class="timestamp" style="float: right;">{time_str}</span><br>
                    {content}
                </div>
                """, unsafe_allow_html=True)
    
    render_conversation()

# Run agent cycles
if st.session_state.running:
    with st.spinner("Agents thinking..."):
        state = {
            "history": st.session_state.history, 
            "user_input": st.session_state.get("last_user_input", "")
        }
        
        try:
            # Process the workflow
            updates = list(app.stream(state, {"recursion_limit": 10}))
            
            for update in updates:
                for node_name, node_output in update.items():
                    if "history" in node_output:
                        st.session_state.history = node_output["history"]
            
            # Capture meta-summaries
            new_meta_messages = [h for h in st.session_state.history if h[1] == "Meta" and h not in st.session_state.meta_summary]
            st.session_state.meta_summary.extend(new_meta_messages)
            
            # Auto-run logic
            if st.session_state.auto_run:
                time.sleep(2)  # Brief pause before next cycle
                st.session_state.last_user_input = "Continue the discussion"
                st.rerun()
            else:
                st.session_state.running = False
                st.rerun()
                
        except Exception as e:
            st.error(f"Error during agent processing: {str(e)}")
            st.session_state.running = False

# Sidebar
with col2:
    st.header("📊 System Status")
    
    # Status indicators
    status_color = "🟢" if st.session_state.running else "🔴"
    auto_status = "🔄" if st.session_state.auto_run else "⏸"
    st.markdown(f"**Status:** {status_color} {'Running' if st.session_state.running else 'Stopped'}")
    st.markdown(f"**Auto-run:** {auto_status} {'Enabled' if st.session_state.auto_run else 'Disabled'}")
    st.markdown(f"**Messages:** {len(st.session_state.history)}")
    
    st.markdown("---")
    
    # Memory Browser
    st.subheader("📌 Memory Browser")
    
    # Pinned memories
    with st.expander("📍 Pinned Memories", expanded=False):
        pinned = load_pinned()
        if pinned:
            for msg in pinned[-5:]:  # Show last 5 pinned
                st.markdown(f"**{msg['role']}:** {msg['content'][:100]}...")
        else:
            st.info("No pinned memories yet")
    
    # Recent memories
    with st.expander("🕐 Recent Memories", expanded=True):
        recent = load_recent(10)
        if recent:
            for msg in recent:
                role_emoji = {"User": "👤", "Planner": "📋", "Critic": "🔍", "Meta": "🧠"}.get(msg['role'], "🤖")
                st.markdown(f"{role_emoji} **{msg['role']}:** {msg['content'][:80]}...")
        else:
            st.info("No recent memories")
    
    st.markdown("---")
    
    # Meta Summaries
    st.subheader("🧠 Meta Summaries")
    
    if st.session_state.meta_summary:
        with st.expander("Latest Meta Insights", expanded=True):
            for timestamp, role, content in st.session_state.meta_summary[-3:]:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime("%m/%d %H:%M")
                except:
                    time_str = timestamp[:10]
                
                st.markdown(f"**{time_str}**")
                st.markdown(f"{content[:200]}...")
                st.markdown("---")
    else:
        st.info("No meta summaries generated yet")
    
    # System info
    st.subheader("⚙️ System Info")
    st.markdown(f"- **Database:** {DB_PATH}")
    st.markdown(f"- **Models:** GPT-4o-mini, Claude-3.5-Sonnet")
    st.markdown(f"- **Session Messages:** {len(st.session_state.history)}")
    
    if st.button("🗑️ Clear Session History"):
        st.session_state.history = []
        st.session_state.meta_summary = []
        st.success("Session cleared!")
        st.rerun()
