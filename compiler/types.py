from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class Type:
    name: str
    refcounted: bool
    methods: Dict[str, FunctionType]
    members: List[Tuple[Type, str]]
    constructor_argtypes: Optional[List[Type]]

    def __init__(self, name: str, refcounted: bool):
        self.name = name
        self.refcounted = refcounted
        self.methods = {}
        self.members = []
        self.constructor_argtypes = None

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.name}>"

    def get_constructor_type(self) -> FunctionType:
        assert self.constructor_argtypes is not None
        return FunctionType(self.constructor_argtypes, self)


@dataclass
class FunctionType(Type):
    argtypes: List[Type]
    returntype: Optional[Type]

    def __init__(self, argtypes: List[Type], returntype: Optional[Type]):
        super().__init__("<function>", False)
        self.argtypes = argtypes
        self.returntype = returntype


INT = Type("int", False)
BOOL = Type("bool", False)
FLOAT = Type("float", False)
STRING = Type("Str", True)

BOOL.methods["to_string"] = FunctionType([BOOL], STRING)

FLOAT.methods["ceil"] = FunctionType([FLOAT], INT)
FLOAT.methods["floor"] = FunctionType([FLOAT], INT)
FLOAT.methods["round"] = FunctionType([FLOAT], INT)
FLOAT.methods["to_string"] = FunctionType([FLOAT], STRING)
FLOAT.methods["truncate"] = FunctionType([FLOAT], INT)

INT.methods["to_string"] = FunctionType([INT], STRING)

STRING.methods["length"] = FunctionType([STRING], INT)
STRING.methods["unicode_length"] = FunctionType([STRING], INT)
STRING.methods["to_float"] = FunctionType([STRING], FLOAT)
STRING.methods["to_int"] = FunctionType([STRING], INT)
STRING.methods["slice"] = FunctionType([STRING, INT, INT], STRING)

builtin_types = {typ.name: typ for typ in [INT, FLOAT, BOOL, STRING]}
global_variables: Dict[str, Type] = {
    "print": FunctionType([STRING], None),
}
