import copy
from dataclasses import dataclass
from typing import List, Optional, Tuple

from compiler.types import FLOAT, INT, STRING, FunctionType, Type


@dataclass(eq=False)
class Expression:
    type: Type


@dataclass(eq=False)
class Statement:
    pass


@dataclass(eq=False)
class GetVar(Expression):
    varname: str
    # Special variables can't be accessed by writing their name into a program.
    # Only the compiler can generate code to access them.
    is_special: bool = False


@dataclass(eq=False)
class GetAttribute(Expression):
    obj: Expression
    attribute: str

    def __init__(self, obj: Expression, attribute: str):
        the_type = {name: the_type for the_type, name in obj.type.members}[attribute]
        super().__init__(the_type)
        self.obj = obj
        self.attribute = attribute


@dataclass(eq=False)
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


@dataclass(eq=False)
class StringConstant(Expression):
    value: str

    def __init__(self, value: str):
        super().__init__(STRING)
        self.value = value


@dataclass(eq=False)
class IntConstant(Expression):
    value: int

    def __init__(self, value: int):
        super().__init__(INT)
        self.value = value


@dataclass(eq=False)
class FloatConstant(Expression):
    value: str

    def __init__(self, value: str):
        super().__init__(FLOAT)
        self.value = value


@dataclass(eq=False)
class VoidCall(Statement):
    func: Expression
    args: List[Expression]


@dataclass(eq=False)
class ReturningCall(Expression, Statement):
    func: Expression
    args: List[Expression]

    def __init__(self, func: Expression, args: List[Expression]):
        assert isinstance(func.type, FunctionType)
        assert func.type.returntype is not None
        super().__init__(func.type.returntype)
        self.func = func
        self.args = args


@dataclass(eq=False)
class CreateLocalVar(Statement):
    varname: str
    value: Expression


@dataclass(eq=False)
class DeleteLocalVar(Statement):
    varname: str


@dataclass(eq=False)
class SetLocalVar(Statement):
    varname: str
    value: Expression


@dataclass(eq=False)
class Continue(Statement):
    loop_id: str


@dataclass(eq=False)
class Break(Statement):
    loop_id: str


@dataclass(eq=False)
class Return(Statement):
    value: Optional[Expression]


@dataclass(eq=False)
class If(Statement):
    condition: Expression
    then: List[Statement]
    otherwise: List[Statement]


@dataclass(eq=False)
class Loop(Statement):
    loop_id: str
    init: List[Statement]
    cond: Expression
    incr: List[Statement]
    body: List[Statement]


@dataclass(eq=False)
class ToplevelStatement:
    pass


@dataclass(eq=False)
class FuncDef(ToplevelStatement):
    name: str
    type: FunctionType
    argnames: List[str]
    body: List[Statement]
    refs: List[Tuple[str, Type]]


@dataclass(eq=False)
class ClassDef(ToplevelStatement):
    type: Type
    body: List[FuncDef]


@dataclass(eq=False)
class SetRef(Expression):
    refname: str
    value: Expression


@dataclass(eq=False)
class DecRef(Statement):
    value: Expression


@dataclass(eq=False)
class Constructor(Expression):
    class_to_construct: Type
