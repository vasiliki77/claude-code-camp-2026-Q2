class RunDSL:
    """The object handed to a `run(..., tools=...)` callback. It exposes only
    `tool`, keeping the surface intentionally small — nothing else on the
    Registry (dispatch in particular) is reachable through it.

    Ruby makes this read as a bare `tool "name"` by running the block through
    instance_eval, which rebinds `self`. Python cannot rebind name resolution
    inside a function body, so the receiver stays visible: `@dsl.tool(...)`."""

    def __init__(self, registry):
        self.registry = registry

    # Straight passthrough, returning Registry.tool's decorator unchanged.
    def tool(self, name, *, description, parameters=None):
        return self.registry.tool(
            name, description=description, parameters=parameters
        )
