from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict


@dataclass
class Type:
    refcounted: bool


@dataclass
class _NamedType(Type):
    name: str


INT = _NamedType(False, 'int')


@dataclass
class FunctionType(Type):
    argtypes: List[Type]
    returntype: Optional[Type]


@dataclass
class ClassType(Type):
    name: str
    members: List[Tuple[Type, str]]
    methods: Dict[str, FunctionType]
