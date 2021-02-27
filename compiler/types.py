from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class Type:
    refcounted: bool
    methods: Dict[str, "FunctionType"]


@dataclass
class _NamedType(Type):
    name: str

    def __repr__(self) -> str:
        return self.name.upper()


INT = _NamedType(False, {}, "int")
BOOL = _NamedType(False, {}, "bool")
FLOAT = _NamedType(False, {}, "float")


@dataclass
class FunctionType(Type):
    argtypes: List[Type]
    returntype: Optional[Type]

    def __init__(self, argtypes: List[Type], returntype: Optional[Type]):
        super().__init__(False, {})
        self.argtypes = argtypes
        self.returntype = returntype


@dataclass
class ClassType(Type):
    name: str
    members: List[Tuple[Type, str]]

    def get_constructor_type(self) -> FunctionType:
        return FunctionType([the_type for the_type, name in self.members], self)
