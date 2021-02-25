import itertools
from typing import Dict, List, Union

from compiler import typed_ast as tast
from compiler import untyped_ast as uast
from compiler.types import INT, ClassType, FunctionType, Type


_ref_names = (f'ref{n}' for n in itertools.count())


class _BlockTyper:

    def __init__(self, variables: Dict[str, Type], types: Dict[str, Type]):
        self.variables = variables
        self.types = types
        self.reflist: List[str] = []

    def do_call(self, ast: uast.Call) -> Union[tast.VoidCall, tast.ReturningCall, tast.SetRef]:
        func = self.do_expression(ast.func)
        assert isinstance(func.type, FunctionType)
        args = [self.do_expression(arg) for arg in ast.args]
        assert len(args) == len(func.type.argtypes)
        for arg, argtype in zip(args, func.type.argtypes):
            assert arg.type == argtype

        if func.type.returntype is None:
            return tast.VoidCall(func, args)

        result = tast.ReturningCall(func.type.returntype, func, args)
        if result.type.refcounted:
            refname = next(_ref_names)
            self.reflist.append(refname)
            return tast.SetRef(result.type, refname, result)
        return result

    def do_expression(self, ast: uast.Expression) -> tast.Expression:
        if isinstance(ast, uast.IntConstant):
            assert -(2**63) <= ast.value < 2**63
            return tast.IntConstant(INT, ast.value)
        if isinstance(ast, uast.Call):
            call = self.do_call(ast)
            assert not isinstance(call, tast.VoidCall)
            return call
        if isinstance(ast, uast.GetVar):
            return tast.GetVar(self.variables[ast.varname], ast.varname)
        if isinstance(ast, uast.Constructor):
            klass = self.types[ast.type]
            assert isinstance(klass, ClassType)
            return tast.Constructor(
                FunctionType(False, [the_type for the_type, name in klass.members], klass),
                klass)
        if isinstance(ast, uast.GetAttribute):
            obj = self.do_expression(ast.obj)
            if isinstance(obj.type, ClassType):
                for the_type, name in obj.type.members:
                    if name == ast.attribute:
                        return tast.GetAttribute(the_type, obj, name)
            raise LookupError(ast.attribute)
        raise NotImplementedError(ast)

    def do_statement(self, ast: uast.Statement) -> tast.Statement:
        if isinstance(ast, uast.Call):
            result = self.do_call(ast)
            if isinstance(result, tast.SetRef):
                return tast.DecRefObject(result.value)
            return result
        if isinstance(ast, uast.LetStatement):
            assert ast.varname not in self.variables
            value = self.do_expression(ast.value)
            self.variables[ast.varname] = value.type
            return tast.LetStatement(ast.varname, value)
        raise NotImplementedError(ast)

    def do_block(self, block: List[uast.Statement]) -> List[tast.Statement]:
        typed_statements = [self.do_statement(s) for s in block]

        newrefs: List[tast.Statement] = [tast.NewRef(refname) for refname in self.reflist]
        decrefs: List[tast.Statement] = [tast.DecRef(varname) for varname in self.reflist]
        return newrefs + typed_statements + decrefs[::-1]


def _do_toplevel_statement(
    variables: Dict[str, Type],
    types: Dict[str, Type],
    top_statement: uast.ToplevelStatement,
) -> tast.ToplevelStatement:
    if isinstance(top_statement, uast.FuncDef):
        assert top_statement.name not in variables
        functype = FunctionType(
            False,
            [types[typename] for typename, argname in top_statement.args],
            None if top_statement.returntype is None else types[top_statement.returntype],
        )
        variables[top_statement.name] = functype
        local_vars = variables.copy()
        for (typename, argname), the_type in zip(top_statement.args, functype.argtypes):
            assert argname not in local_vars
            local_vars[argname] = the_type
        return tast.FuncDef(
            top_statement.name,
            functype,
            [argname for typename, argname in top_statement.args],
            _BlockTyper(local_vars, types).do_block(top_statement.body),
        )
    elif isinstance(top_statement, uast.ClassDef):
        classtype = ClassType(
            True,
            top_statement.name,
            [(types[typename], membername) for typename, membername in top_statement.members],
        )
        result = tast.ClassDef(classtype)
        assert top_statement.name not in types
        types[top_statement.name] = classtype
        return result
    raise NotImplementedError(top_statement)


def convert_program(program: List[uast.ToplevelStatement]) -> List[tast.ToplevelStatement]:
    types: Dict[str, Type] = {'int': INT}
    variables: Dict[str, Type] = {
        'add': FunctionType(False, [INT, INT], INT),
        'print_int': FunctionType(False, [INT], None),
    }
    return [_do_toplevel_statement(variables, types, toplevel_statement)
            for toplevel_statement in program]
