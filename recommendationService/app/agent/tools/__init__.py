"""
Tools module for Ando LangChain Agent.
"""
from typing import Any, List, Optional

from app.agent.tools.itinerary_tool import build_itinerary_tool
from app.agent.tools.poi_search_tool import search_pois_tool
from app.agent.tools.recommendation_tool import build_recommendation_tool
from app.agent.tools.review_summary_tool import get_poi_reviews_summary_tool


def build_agent_tools(user_id: Optional[str]) -> List[Any]:
    """Las tools personales existen solo con sesión, y llevan el user_id del servidor, nunca uno elegido por el LLM."""
    tools: List[Any] = [search_pois_tool, get_poi_reviews_summary_tool]
    if user_id:
        tools += [build_recommendation_tool(user_id), build_itinerary_tool(user_id)]
    return tools


__all__ = ["build_agent_tools"]
