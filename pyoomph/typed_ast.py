from __future__ import annotations

import copy
import pathlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

from pyoomph.types import BOOL, FLOAT, INT, LIST, STRING, FunctionType, Type, UnionType


@dataclass(eq=False)
class Expression:
    type: Type


@dataclass(eq=False)
class Statement:
    pass


@dataclass(eq=False)
class Variable:
    name: str
    type: Type


# There can be different local variables with same name, even in the same
# function. They are represented as different instances of this class.
@dataclass(eq=False)
class LocalVariable(Variable):
    pass


# Currently these are always functions. These would be called "global
# variables" in Python, but that's confusing, because they are less global
# than ExportVariables.
@dataclass(eq=False)
class ThisFileVariable(Variable):
    pass


@dataclass(eq=False)
class ExportVariable(Variable):
    pass


@dataclass(eq=False)
class BuiltinVariable(Variable):
    pass


@dataclass(eq=False)
class SpecialVariable(Variable):
    pass


builtin_variables = {
    var.name: var
    for var in [
        BuiltinVariable("__io_mkdir", FunctionType([STRING], None)),
        BuiltinVariable("__io_read_file", FunctionType([STRING], STRING)),
        BuiltinVariable("__io_write_file", FunctionType([STRING, STRING], None)),
        BuiltinVariable("__subprocess_run", FunctionType([LIST.get_type(STRING)], INT)),
        BuiltinVariable("assert", FunctionType([BOOL], None)),
        BuiltinVariable("false", BOOL),
        BuiltinVariable("print", FunctionType([STRING], None)),
        BuiltinVariable("true", BOOL),
    ]
}

special_variables = {
    var.name: var
    for var in [
        SpecialVariable("bool_eq", FunctionType([BOOL, BOOL], BOOL)),
        SpecialVariable("bool_not", FunctionType([BOOL], BOOL)),
        SpecialVariable("float_add", FunctionType([FLOAT, FLOAT], FLOAT)),
        SpecialVariable("float_div", FunctionType([FLOAT, FLOAT], FLOAT)),
        SpecialVariable("float_eq", FunctionType([FLOAT, FLOAT], BOOL)),
        SpecialVariable("float_gt", FunctionType([FLOAT, FLOAT], BOOL)),
        SpecialVariable("float_mod", FunctionType([FLOAT, FLOAT], FLOAT)),
        SpecialVariable("float_mul", FunctionType([FLOAT, FLOAT], FLOAT)),
        SpecialVariable("float_neg", FunctionType([FLOAT], FLOAT)),
        SpecialVariable("float_sub", FunctionType([FLOAT, FLOAT], FLOAT)),
        SpecialVariable("int2float", FunctionType([INT], FLOAT)),
        SpecialVariable("int_add", FunctionType([INT, INT], INT)),
        SpecialVariable("int_eq", FunctionType([INT, INT], BOOL)),
        SpecialVariable("int_gt", FunctionType([INT, INT], BOOL)),
        SpecialVariable("int_mod", FunctionType([INT, INT], INT)),
        SpecialVariable("int_mul", FunctionType([INT, INT], INT)),
        SpecialVariable("int_neg", FunctionType([INT], INT)),
        SpecialVariable("int_sub", FunctionType([INT, INT], INT)),
        SpecialVariable("string_concat", FunctionType([STRING, STRING], STRING)),
        SpecialVariable("string_eq", FunctionType([STRING, STRING], BOOL)),
    ]
}


@dataclass(eq=False)
class GetVar(Expression):
    var: Variable
    incref: bool
    lineno: Optional[int]

    def __init__(self, var: Variable, incref: bool, lineno: Optional[int] = None):
        super().__init__(var.type)
        self.var = var
        self.incref = incref
        self.lineno = lineno


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
class Null(Expression):
    pass


# And,Or are not function calls with is_special=True because evaluation order
# is different than for function calls.
class BoolAnd(Expression):
    lhs: Expression
    rhs: Expression

    def __init__(self, lhs: Expression, rhs: Expression):
        super().__init__(BOOL)
        self.lhs = lhs
        self.rhs = rhs


class BoolOr(Expression):
    lhs: Expression
    rhs: Expression

    def __init__(self, lhs: Expression, rhs: Expression):
        super().__init__(BOOL)
        self.lhs = lhs
        self.rhs = rhs


# Can't be a function call because arguments can be many different types
@dataclass(eq=False)
class PointersEqual(Expression):
    lhs: Expression
    rhs: Expression

    def __init__(self, lhs: Expression, rhs: Expression):
        super().__init__(BOOL)
        self.lhs = lhs
        self.rhs = rhs


# Arguments have to be in local variables because this way their evaluation
# order is guaranteed, even though it's undefined in C. Also, to decref them
# after calling, they need to be in variables anyway.
@dataclass(eq=False)
class VoidCall(Statement):
    func: Expression
    args: List[LocalVariable]


@dataclass(eq=False)
class ReturningCall(Statement):
    func: Expression
    args: List[LocalVariable]

    def __init__(self, func: Expression, args: List[LocalVariable]):
        assert isinstance(func.type, FunctionType)
        assert func.type.returntype is not None
        super().__init__(func.type.returntype)
        self.func = func
        self.args = args


@dataclass(eq=False)
class InstantiateUnion(Expression):
    type: UnionType  # more specific than Expression.type
    value: Expression


# Evaluate statement, then output the value of the expression
# TODO: delete this and somehow rewrite things properly
@dataclass(eq=False)
class StatementsAndExpression(Expression):
    statements: List[Statement]
    expression: Expression

    def __init__(self, statements: List[Statement], expression: Expression):
        super().__init__(expression.type)
        self.statements = statements
        self.expression = expression


@dataclass(eq=False)
class CreateLocalVar(Statement):
    var: LocalVariable
    value: Expression


@dataclass(eq=False)
class SetLocalVar(Statement):
    var: LocalVariable
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
class Switch(Statement):
    union: Expression
    cases: Dict[LocalVariable, List[Statement]]


@dataclass(eq=False)
class ToplevelDeclaration:
    pass


@dataclass(eq=False)
class FuncDef(ToplevelDeclaration):
    var: Union[ThisFileVariable, ExportVariable]
    argvars: List[LocalVariable]
    body: List[Statement]


@dataclass(eq=False)
class MethodDef:
    name: str
    type: FunctionType
    argvars: List[LocalVariable]
    body: List[Statement]


@dataclass(eq=False)
class ClassDef(ToplevelDeclaration):
    type: Type
    body: List[MethodDef]
    export: bool


@dataclass(eq=False)
class UnionDef(ToplevelDeclaration):
    type: UnionType


@dataclass(eq=False)
class DecRef(Statement):
    value: Expression


@dataclass(eq=False)
class Constructor(Expression):
    class_to_construct: Type


@dataclass(eq=False)
class Export:
    path: pathlib.Path
    name: str
    value: Union[ExportVariable, Type]  # Type includes UnionType
