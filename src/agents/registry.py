import importlib
import os
import inspect
from typing import Dict, Any, Type, List
from agents.base import BaseAgent

class AgentRegistry:
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}

    def register_agent(self, agent_instance: BaseAgent):
        self.agents[agent_instance.name] = agent_instance
        print(f"Agent [{agent_instance.name}] registered.")

    def get_agent(self, name: str) -> BaseAgent:
        return self.agents.get(name)

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Returns all agent declarations for Gemini Tool configuration."""
        # Note: In new google-genai SDK, tools are passed as a list of functions
        # or special Tool objects. We'll format this appropriately in the Orchestrator.
        return [agent.get_tool_declaration() for agent in self.agents.values()]

# Global registry instance
registry = AgentRegistry()
