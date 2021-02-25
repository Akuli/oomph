from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Type:
    pass


@dataclass
class NamedType(Type):
    name: str


@dataclass
class FunctionType(Type):
    argtypes: List[Type]
    returntype: Optional[Type]


@dataclass
class ClassType(Type):
    name: str
    constructor_type: FunctionType
