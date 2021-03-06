from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


class Type:
    def __init__(
        self,
        name: str,
        refcounted: bool,
    ):
        self.name = name
        self.refcounted = refcounted


@dataclass(eq=False)
class FunctionType(Type):
    argtypes: List[Type]
    returntype: Optional[Type]

    def __init__(self, argtypes: List[Type], returntype: Optional[Type]):
        super().__init__("<function>", False)
        self.argtypes = argtypes
        self.returntype = returntype


STRING = Type("Str", True)
builtin_types = {"Str": STRING}
