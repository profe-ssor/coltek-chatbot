"""Coltek agents: triage with handoffs to the Services, Academy and OpenDoor specialists."""
from chatbot.agents.triage import (
    DEPARTMENTS,
    SPECIALISTS,
    academy_agent,
    department_for,
    get_starting_agent,
    opendoor_agent,
    services_agent,
    triage_agent,
)

__all__ = [
    "DEPARTMENTS",
    "SPECIALISTS",
    "department_for",
    "academy_agent",
    "get_starting_agent",
    "opendoor_agent",
    "services_agent",
    "triage_agent",
]
