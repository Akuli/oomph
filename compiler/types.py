from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Type:
    pass


@dataclass
class SpecialType(Type):
    name: str


INT = SpecialType('int')


@dataclass
class FunctionType(Type):
    argtypes: List[Type]
    returntype: Optional[Type]
