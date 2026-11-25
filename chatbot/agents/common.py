"""Pieces shared by all agents: domain-filtered file search."""
from agents import FileSearchTool

from chatbot.config import VECTOR_STORE_ID


def file_search_for(*domains: str) -> FileSearchTool:
    """File search on the Coltek vector store, limited to chunks whose 'domain' attribute is one of `domains`.

    Domain labels are set at upload by scripts/upload_knowledge.py: services, academy, opendoor, company.
    """
    return FileSearchTool(
        vector_store_ids=[VECTOR_STORE_ID],
        max_num_results=5,
        include_search_results=True,
        filters={
            "type": "or",
            "filters": [{"type": "eq", "key": "domain", "value": d} for d in domains],
        },
    )
