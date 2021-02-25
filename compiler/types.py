from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Type:
    pass


@dataclass
class _NamedType(Type):
    name: str


INT = _NamedType('int')


@dataclass
class FunctionType(Type):
    argtypes: List[Type]
    returntype: Optional[Type]


@dataclass
class ClassType(Type):
    name: str
