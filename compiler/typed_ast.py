import copy
from dataclasses import dataclass
from typing import List, Optional, Tuple

from compiler.types import FLOAT, INT, STRING, FunctionType, Type


@dataclass
class Expression:
    type: Type


@dataclass
class Statement:
    pass


@dataclass
class GetVar(Expression):
    varname: str
    # Special variables can't be accessed by writing their name into a program.
    # Only the compiler can generate code to access them.
    is_special: bool = False


@dataclass
class GetAttribute(Expression):
    obj: Expression
    attribute: str

    def __init__(self, obj: Expression, attribute: str):
        the_type = {name: the_type for the_type, name in obj.type.members}[attribute]
        super().__init__(the_type)
        self.obj = obj
        self.attribute = attribute


@dataclass
class GetMethod(Expression):
    obj: Expression
    name: str

    def __init__(self, obj: Expression, name: str):
        the_type = copy.copy(obj.type.methods[name])  # shallow copy
        self_type = the_type.argtypes[0]
        assert self_type is obj.type
        the_type.argtypes = the_type.argtypes[1:]  # don't modify argtypes list in-place

        super().__init__(the_type)
        self.obj = obj
        self.name = name


@dataclass
class StringConstant(Expression):
    value: str

    def __init__(self, value: str):
        super().__init__(STRING)
        self.value = value


@dataclass
class IntConstant(Expression):
    value: int

    def __init__(self, value: int):
        super().__init__(INT)
        self.value = value


@dataclass
class FloatConstant(Expression):
    value: str

    def __init__(self, value: str):
        super().__init__(FLOAT)
        self.value = value


@dataclass
class VoidCall(Statement):
    func: Expression
    args: List[Expression]


@dataclass
class ReturningCall(Expression, Statement):
    func: Expression
    args: List[Expression]

    def __init__(self, func: Expression, args: List[Expression]):
        assert isinstance(func.type, FunctionType)
        assert func.type.returntype is not None
        super().__init__(func.type.returntype)
        self.func = func
        self.args = args


@dataclass
class CreateLocalVar(Statement):
    varname: str
    value: Expression


@dataclass
class SetLocalVar(Statement):
    varname: str
    value: Expression


@dataclass
class Continue(Statement):
    loop_id: str


@dataclass
class Break(Statement):
    loop_id: str


@dataclass
class Return(Statement):
    value: Optional[Expression]


@dataclass
class If(Statement):
    condition: Expression
    then: List[Statement]
    otherwise: List[Statement]


@dataclass
class Loop(Statement):
    loop_id: str
    init: List[Statement]
    cond: Expression
    incr: List[Statement]
    body: List[Statement]


@dataclass
class ToplevelStatement:
    pass


@dataclass
class FuncDef(ToplevelStatement):
    name: str
    type: FunctionType
    argnames: List[str]
    body: List[Statement]
    refs: List[Tuple[str, Type]]


@dataclass
class ClassDef(ToplevelStatement):
    type: Type
    body: List[FuncDef]


@dataclass
class SetRef(Expression):
    refname: str
    value: Expression


@dataclass
class DecRef(Statement):
    value: Expression


@dataclass
class Constructor(Expression):
    class_to_construct: Type
