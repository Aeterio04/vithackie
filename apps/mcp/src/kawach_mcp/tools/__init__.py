"""Tools package for Kawach MCP Server."""

from kawach_mcp.tools.registry import TOOL_REGISTRY, ToolSpec, register_tool

# Import all tool modules to register them in TOOL_REGISTRY
import kawach_mcp.tools.system
import kawach_mcp.tools.read_tools
import kawach_mcp.tools.action_tools
import kawach_mcp.tools.write_tools

__all__ = ["TOOL_REGISTRY", "ToolSpec", "register_tool"]
