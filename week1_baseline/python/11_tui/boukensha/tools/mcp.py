from ..mcp.client import Client


class ToolCollisionError(Exception):
    """Two servers advertised the same tool name.

    Registry.tool would otherwise let the second registration silently clobber
    the first, which is a bug that would be maddening to debug: the agent would
    call `search` and reach the wrong server, with nothing anywhere saying so.
    Prefixing makes this unlikely, not impossible — two entries can share a
    prefix — so the check stays regardless.
    """


def register(registry, *, command, args=None, env=None, prefix=None, label=None):
    """Register tools discovered from any MCP server.

    This module contains **no MUD knowledge**: no telnet, no primitives, no
    login, not one tool name. It knows a command to spawn and it knows MCP.
    Point it at a filesystem server, a calculator, or `mud-manager` and it
    registers whatever that server advertises.

    Spawning a subprocess with a command, args and env is not coupling — it is
    the MCP stdio transport's standard configuration shape, the same triple
    every MCP host uses. Passing credentials through the server's environment
    is likewise standard: the spec has no "send credentials over the wire"
    concept for stdio servers, deliberately.

    Returns the live client. The caller owns it and must close it.
    """
    client = Client.spawn(command=command, args=args or [], env=env or {})
    label = label or client.server_info.get("name") or str(command)

    for tool in client.tools:
        _register_one(registry, client, tool, prefix, label)

    return client


def _register_one(registry, client, tool, prefix, label):
    remote_name = tool["name"]
    local_name = remote_name if not prefix else f"{prefix}__{remote_name}"

    existing = registry.context.tools.get(local_name)
    if existing:
        raise ToolCollisionError(
            f"tool {local_name!r} from {label} collides with one already registered "
            f"({str(existing.description)[:60]}…). Give one of the servers a distinct "
            f"`prefix` in mcp_servers."
        )

    @registry.tool(
        local_name,
        description=str(tool.get("description") or ""),
        parameters=_parameters_from(tool.get("inputSchema") or {}),
    )
    def call(**args):
        # Drop Nones rather than forwarding them: the server validates
        # arguments, and an explicit null reads as "provided but empty" where
        # the model meant "not provided".
        supplied = {str(k): v for k, v in args.items() if v is not None}
        result = client.call_tool(remote_name, supplied)

        # A failed tool call comes back as text, not an exception. The agent
        # loop feeds it straight to the model, which can then correct itself —
        # raising here would abort the run instead.
        return result["text"]

    return call


def _parameters_from(schema):
    """Translate a JSON Schema inputSchema into the shape Tool wants.

    The schema's `required` list is discarded, because the backends declare
    *every* parameter required regardless of what is passed. Plumbing `required`
    through Tool is the correct fix, but it changes all tools rather than just
    MCP ones, so it belongs in its own plan. Harmless against our own daemon,
    which treats blank strings as absent; it will bite against third-party
    schemas with genuinely optional parameters.
    """
    properties = schema.get("properties") or {}
    out = {}

    for name, prop in properties.items():
        entry = {
            "type": prop.get("type") or "string",
            "description": str(prop.get("description") or ""),
        }
        # Enums are the server's anti-drift guarantee — carry them through so
        # the model sees the same allowed values the server validates against.
        values = prop.get("enum")
        if values:
            entry["enum"] = values
            entry["description"] = f"{entry['description']} (one of: {', '.join(values)})".strip()
        out[name] = entry

    return out
