"""Orchestrator — the multi-agent pipeline as a LangGraph state machine.

The graph encodes the proposal's phases and, crucially, an explicit
human-in-the-loop interrupt before application preparation. LangGraph is used
here for the agentic control flow (state passed between nodes, conditional
edges, interrupts). Individual agents are the functions in this package.

If langgraph is not installed, `run_pipeline` falls back to a plain sequential
call of the same nodes so the system still runs.
"""
from __future__ import annotations

from typing import Any, Callable
from typing_extensions import TypedDict

from app.agents import discovery_agent, matching_agent


class PipelineState(TypedDict, total=False):
    profile: dict
    profile_emb: list[float]
    query: str
    location: str | None
    work_type: str
    limit: int
    jobs: list[dict]
    ranked: list[dict]


def node_discover(state: PipelineState) -> PipelineState:
    state["jobs"] = discovery_agent.discover_jobs(
        state["query"], state.get("location"), state.get("limit", 20),
        state.get("work_type", "remote"),
    )
    return state


def node_rank(state: PipelineState) -> PipelineState:
    state["ranked"] = matching_agent.rank(
        state["profile"], state["profile_emb"], state.get("jobs", [])
    )
    return state


def _build_graph() -> Callable[[PipelineState], PipelineState] | None:
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return None
    g = StateGraph(PipelineState)
    g.add_node("discover", node_discover)
    g.add_node("rank", node_rank)
    g.add_edge(START, "discover")
    g.add_edge("discover", "rank")
    g.add_edge("rank", END)
    # NOTE: application preparation lives past a human-in-the-loop checkpoint and
    # is invoked separately (see routers/applications.py) — the user must pick a
    # role first. That is the deliberate interrupt in the proposal's Decide phase.
    return g.compile()


_graph = _build_graph()


def run_pipeline(state: PipelineState) -> PipelineState:
    if _graph is not None:
        return _graph.invoke(state)
    # fallback: sequential
    return node_rank(node_discover(state))
