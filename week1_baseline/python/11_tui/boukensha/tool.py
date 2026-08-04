from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    block: Callable

    def __str__(self):
        params = "[" + ", ".join(f":{key}" for key in self.parameters) + "]"
        return (
            f"#<Tool name={self.name} "
            f"description={str(self.description)[:41]} params={params}>"
        )

    __repr__ = __str__
