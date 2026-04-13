from langgraph.graph import StateGraph, END
from typing import TypedDict
from retrievers import retrieve_files, retrieve_mongodb
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY

client = Anthropic(api_key=ANTHROPIC_API_KEY)

class State(TypedDict):
    query: str
    source: str
    context: str
    answer: str


def router(state):
    q = state["query"].lower()

    db_keywords = ["database", "collection", "record", "data", "count", "users"]

    if any(k in q for k in db_keywords):
        return {"source": "mongo"}

    file_keywords = ["pdf", "file", "document"]

    if any(k in q for k in file_keywords):
        return {"source": "file"}

    return {"source": "hybrid"}


def mongo_node(state):
    docs = retrieve_mongodb(state["query"])
    return {"context": "\n".join(docs)}


def file_node(state):
    docs = retrieve_files(state["query"])
    return {"context": "\n".join(docs)}


def hybrid_node(state):
    docs1 = retrieve_mongodb(state["query"])
    docs2 = retrieve_files(state["query"])
    return {"context": "\n".join(docs1 + docs2)}


def generate(state):
    prompt = f"""
You are the GoWhats Admin Assistant.

Your job is to help the admin manage the SaaS system, tenants, and technical status.

Speak politely and professionally like:
- "sir"
- "ma'am"

Keep responses clear, direct, and not too long.

---

Responsibilities:
- Help manage tenants
- Provide system status
- Assist with billing and subscriptions
- Help debug issues

---

Capabilities:

Tenant Management:
- View tenants
- Check tenant status (active/inactive)
- View subscription details

System Monitoring:
- API status
- Message usage
- Errors or failures

Billing:
- Subscription tracking
- Payment status

---

Behavior Rules:

- If admin asks about tenants → give structured info
- If issue reported → ask for tenant name or ID
- If system issue → suggest checking logs or retry
- Keep answers precise and professional

---

Context:
{state['context']}

---

Question:
{state['query']}

---

Answering Rules:
- If context is from MongoDB → explain clearly
- If from files → summarize properly
- If both → combine
- Do not add unnecessary explanation

---

If no data found:
Say:
"Sorry sir, I couldn’t find relevant data. Please check logs or provide more details."

"""

    res = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )

    return {"answer": res.content[0].text}


def build_graph():
    g = StateGraph(State)

    g.add_node("router", router)
    g.add_node("mongo", mongo_node)
    g.add_node("file", file_node)
    g.add_node("hybrid", hybrid_node)
    g.add_node("generate", generate)

    g.set_entry_point("router")

    g.add_conditional_edges(
        "router",
        lambda x: x["source"],
        {
            "mongo": "mongo",
            "file": "file",
            "hybrid": "hybrid"
        }
    )

    g.add_edge("mongo", "generate")
    g.add_edge("file", "generate")
    g.add_edge("hybrid", "generate")
    g.add_edge("generate", END)

    return g.compile()