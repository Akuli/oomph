from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class Type:
    refcounted: bool


@dataclass
class _NamedType(Type):
    name: str

    def __repr__(self):
        return self.name.upper()


INT = _NamedType(False, "int")
BOOL = _NamedType(False, "bool")


@dataclass
class FunctionType(Type):
    argtypes: List[Type]
    returntype: Optional[Type]


@dataclass
class ClassType(Type):
    name: str
    members: List[Tuple[Type, str]]
    methods: Dict[str, FunctionType]
