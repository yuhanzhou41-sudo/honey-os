# Turn Router Shadow Integration

Status: SHADOW ONLY.

The API server still resolves the real runtime toolsets exactly as before:

`enabled_toolsets = sorted(_get_platform_tools(user_config, "api_server"))`

Immediately after that, the Turn Router computes a shadow decision for the
current user message.

The shadow decision is used only for structured logging. It does not alter:
- enabled toolsets
- tool definitions
- tool execution
- MemoryManager
- model selection
- chat response behavior

If the local router is unavailable or returns invalid output, the shadow path
logs the failure and the existing runtime continues unchanged.

Raw user message text is not logged.
