"""CrewAI multi-agent chatbot system for SecureOffice2."""

import os

# Disable CrewAI tracing prompt BEFORE any crewai import
# This prevents the "Would you like to view your execution traces? [y/N]" blocking prompt
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

from app.services.crew.crew import ChatbotCrew

__all__ = ["ChatbotCrew"]
