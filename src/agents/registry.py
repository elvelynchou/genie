import importlib.util
import os
import inspect
import logging
from typing import Dict, Any, Type, List
from agents.base import BaseAgent

logger = logging.getLogger("AgentRegistry")

class AgentRegistry:
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}

    def register_agent(self, agent_instance: BaseAgent):
        self.agents[agent_instance.name] = agent_instance
        logger.info(f"Agent [{agent_instance.name}] registered.")

    def get_agent(self, name: str) -> BaseAgent:
        return self.agents.get(name)

    def load_agent_from_file(self, file_path: str, class_name: str, **kwargs):
        """
        Dynamically loads and registers an agent class from a given file.
        """
        try:
            # 1. Load module
            module_name = f"dynamic_agent_{os.path.basename(file_path).replace('.py', '')}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None:
                raise ImportError(f"Could not find spec for {file_path}")
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 2. Get class and instantiate
            if hasattr(module, class_name):
                agent_class = getattr(module, class_name)
                # Note: Pass any shared dependencies (orchestrator, redis, etc.) via kwargs
                agent_instance = agent_class(**kwargs)
                self.register_agent(agent_instance)
                return agent_instance
            else:
                raise AttributeError(f"Class {class_name} not found in {file_path}")
        except Exception as e:
            logger.error(f"Failed to load dynamic agent {class_name} from {file_path}: {e}")
            raise

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Returns all agent declarations for Gemini Tool configuration."""
        return [agent.get_tool_declaration() for agent in self.agents.values()]

# Global registry instance
registry = AgentRegistry()
