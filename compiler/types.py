from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class Type:
    name: str
    refcounted: bool
    methods: Dict[str, "FunctionType"]

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.name}>"


@dataclass
class FunctionType(Type):
    argtypes: List[Type]
    returntype: Optional[Type]

    def __init__(self, argtypes: List[Type], returntype: Optional[Type]):
        super().__init__("function", False, {})
        self.argtypes = argtypes
        self.returntype = returntype


INT = Type("int", False, {})
BOOL = Type("bool", False, {})
FLOAT = Type("float", False, {})
STRING = Type("String", True, {})

FLOAT.methods["floor"] = FunctionType([FLOAT], INT)
FLOAT.methods["ceil"] = FunctionType([FLOAT], INT)
FLOAT.methods["truncate"] = FunctionType([FLOAT], INT)
FLOAT.methods["round"] = FunctionType([FLOAT], INT)

BOOL.methods["to_string"] = FunctionType([BOOL], STRING)


@dataclass
class ClassType(Type):
    members: List[Tuple[Type, str]]

    def get_constructor_type(self) -> FunctionType:
        return FunctionType([the_type for the_type, name in self.members], self)
