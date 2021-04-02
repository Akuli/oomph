from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple


# Describes how exactly a type was created from a generic
@dataclass(eq=True)
class GenericSource:
    generic: Generic
    arg: Type


class Type:
    def __init__(
        self,
        name: str,
        refcounted: bool,
        definition_path: Optional[pathlib.Path] = None,
        *,
        create_to_string_method: bool = False,
    ):
        self._name = name
        self.refcounted = refcounted
        self.definition_path = definition_path
        self.methods: Dict[str, FunctionType] = {}
        self.members: List[Tuple[Type, str]] = []
        self.constructor_argtypes: Optional[List[Type]] = None
        self.generic_origin: Optional[GenericSource] = None
        self.create_to_string_method = create_to_string_method
        if create_to_string_method:
            self.methods["to_string"] = FunctionType([self], STRING)

    # To make the name more overridable
    @property
    def name(self) -> str:
        return self._name

    def get_id_string(self) -> str:
        if self.generic_origin is None:
            return self.name + str(self.definition_path)
        return (
            self.generic_origin.generic.name + self.generic_origin.arg.get_id_string()
        )

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.name}>"

    def __eq__(self, other: object) -> bool:
        if isinstance(self, AutoType) or isinstance(other, AutoType):
            return self is other
        if isinstance(self, UnionType) or isinstance(other, UnionType):
            return (
                isinstance(self, UnionType)
                and isinstance(other, UnionType)
                and self.type_members == other.type_members
            )
        return (
            isinstance(other, Type)
            and self.name == other.name
            and self.definition_path == other.definition_path
            and self.generic_origin == other.generic_origin
        )

    def __hash__(self) -> int:
        return hash(self.name)


class AutoType(Type):
    def __init__(self) -> None:
        super().__init__("auto_" + hex(id(self))[-4:], True)


class UnionType(Type):
    def __init__(self, type_members: Set[Type]):
        super().__init__("", True)
        self.custom_name: Optional[str] = None

        assert len(type_members) >= 2

        # Consistent order, with null first if any (used in lib/)
        self.type_members = sorted(type_members, key=(lambda t: t.get_id_string()))
        if NULL_TYPE in self.type_members:
            self.type_members.remove(NULL_TYPE)
            self.type_members.insert(0, NULL_TYPE)

        self.methods["equals"] = FunctionType([self, self], BOOL)
        self.methods["to_string"] = FunctionType([self], STRING)
        if len(self.type_members) == 2 and self.type_members[0] == NULL_TYPE:
            self.methods["get"] = FunctionType([self], self.type_members[1])

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {repr(self.name)}, type_members={self.type_members}>"

    @property
    def name(self) -> str:
        # Don't use custom names for 'Foo | null'
        if "get" in self.methods or self.custom_name is None:
            return "(%s)" % " | ".join(t.name for t in self.type_members)
        return self.custom_name

    def get_id_string(self) -> str:
        return "|".join(member.get_id_string() for member in self.type_members)


# does NOT inherit from type, optional isn't a type even though optional[str] is
@dataclass(eq=False)
class Generic:
    name: str

    def get_type(self, generic_arg: Type) -> Type:
        assert self is LIST
        result = Type(f"{self.name}[{generic_arg.name}]", True)
        result.constructor_argtypes = []
        # TODO: hide __contains better?
        result.methods["__contains"] = FunctionType([result, generic_arg], BOOL)
        result.methods["delete_at_index"] = FunctionType([result, INT], None)
        result.methods["delete_slice"] = FunctionType([result, INT, INT], result)
        result.methods["ends_with"] = FunctionType([result, result], BOOL)
        result.methods["first"] = FunctionType([result], generic_arg)
        result.methods["get"] = FunctionType([result, INT], generic_arg)
        result.methods["insert"] = FunctionType([result, INT, generic_arg], None)
        result.methods["last"] = FunctionType([result], generic_arg)
        result.methods["length"] = FunctionType([result], INT)
        result.methods["pop"] = FunctionType([result], generic_arg)
        result.methods["push"] = FunctionType([result, generic_arg], None)
        result.methods["push_all"] = FunctionType([result, result], None)
        result.methods["reversed"] = FunctionType([result], result)
        result.methods["slice"] = FunctionType([result, INT, INT], result)
        result.methods["starts_with"] = FunctionType([result, result], BOOL)
        result.methods["to_string"] = FunctionType([result], STRING)
        # TODO: this is only for strings, but List[auto] may become List[Str] later
        # if generic_arg is STRING:
        result.methods["join"] = FunctionType([result, STRING], STRING)
        result.generic_origin = GenericSource(self, generic_arg)

        result.methods["equals"] = FunctionType([result, result], BOOL)
        return result


LIST = Generic("List")


@dataclass(eq=False)
class FunctionType(Type):
    argtypes: List[Type]
    returntype: Optional[Type]

    def __init__(self, argtypes: List[Type], returntype: Optional[Type]):
        super().__init__("<function>", False)
        self.argtypes = argtypes
        self.returntype = returntype

    # Currently not used
    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, FunctionType)
            and self.argtypes == other.argtypes
            and self.returntype == other.returntype
        )

    def __hash__(self) -> int:
        return hash(tuple(self.argtypes)) ^ hash(self.returntype)


BOOL = Type("Bool", False)
FLOAT = Type("Float", False)
INT = Type("Int", False)
NULL_TYPE = Type("null", False)
STRING = Type("Str", True)

BOOL.methods["equals"] = FunctionType([BOOL, BOOL], BOOL)
BOOL.methods["to_string"] = FunctionType([BOOL], STRING)

FLOAT.methods["ceil"] = FunctionType([FLOAT], INT)
FLOAT.methods["equals"] = FunctionType([FLOAT, FLOAT], BOOL)
FLOAT.methods["floor"] = FunctionType([FLOAT], INT)
FLOAT.methods["round"] = FunctionType([FLOAT], INT)
FLOAT.methods["to_string"] = FunctionType([FLOAT], STRING)
FLOAT.methods["truncate"] = FunctionType([FLOAT], INT)

INT.methods["equals"] = FunctionType([INT, INT], BOOL)
INT.methods["to_string"] = FunctionType([INT], STRING)

NULL_TYPE.methods["equals"] = FunctionType([NULL_TYPE, NULL_TYPE], BOOL)
NULL_TYPE.methods["to_string"] = FunctionType([NULL_TYPE], STRING)

STRING.methods["center_pad"] = FunctionType([STRING, INT, STRING], STRING)
STRING.methods["contains"] = FunctionType([STRING, STRING], BOOL)
STRING.methods["count"] = FunctionType([STRING, STRING], INT)
STRING.methods["ends_with"] = FunctionType([STRING, STRING], BOOL)
STRING.methods["equals"] = FunctionType([STRING, STRING], BOOL)
STRING.methods["get_utf8"] = FunctionType([STRING], LIST.get_type(INT))
STRING.methods["left_pad"] = FunctionType([STRING, INT, STRING], STRING)
STRING.methods["left_trim"] = FunctionType([STRING], STRING)
STRING.methods["length"] = FunctionType([STRING], INT)
STRING.methods["remove_prefix"] = FunctionType([STRING, STRING], STRING)
STRING.methods["remove_suffix"] = FunctionType([STRING, STRING], STRING)
STRING.methods["repeat"] = FunctionType([STRING, INT], STRING)
STRING.methods["replace"] = FunctionType([STRING, STRING, STRING], STRING)
STRING.methods["right_pad"] = FunctionType([STRING, INT, STRING], STRING)
STRING.methods["right_trim"] = FunctionType([STRING], STRING)
STRING.methods["split"] = FunctionType([STRING, STRING], LIST.get_type(STRING))
STRING.methods["starts_with"] = FunctionType([STRING, STRING], BOOL)
STRING.methods["to_float"] = FunctionType([STRING], FLOAT)
STRING.methods["to_int"] = FunctionType([STRING], INT)
STRING.methods["to_string"] = FunctionType([STRING], STRING)  # does nothing
STRING.methods["trim"] = FunctionType([STRING], STRING)

builtin_types = {typ.name: typ for typ in [INT, FLOAT, BOOL, STRING, NULL_TYPE]}
builtin_generic_types = {gen.name: gen for gen in [LIST]}
