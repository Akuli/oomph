from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple


# Describes how exactly a type was created from a generic
@dataclass(eq=True)
class GenericSource:
    generic: Generic
    args: List[Type]


class Type:
    def __init__(
        self,
        name: str,
        refcounted: bool,
        definition_path: Optional[pathlib.Path] = None,
        methods_to_create: Optional[Set[str]] = None,
    ):
        self._name = name
        self.refcounted = refcounted
        self.definition_path = definition_path
        self.methods: Dict[str, FunctionType] = {}
        self.members: List[Tuple[Type, str]] = []
        self.constructor_argtypes: Optional[List[Type]] = None
        self.generic_origin: Optional[GenericSource] = None
        self.methods_to_create = methods_to_create or set()

        for method in self.methods_to_create:
            if method == "to_string":
                self.methods["to_string"] = FunctionType([self], STRING)
            elif method == "equals":
                self.methods["equals"] = FunctionType([self, self], BOOL)
            elif method == "hash":
                self.methods["hash"] = FunctionType([self], INT)
            else:
                raise NotImplementedError(method)

    # To make the name more overridable
    @property
    def name(self) -> str:
        return self._name

    def get_id_string(self) -> str:
        if self.generic_origin is None:
            return self.name + str(self.definition_path)
        return self.generic_origin.generic.name + ",".join(
            arg.get_id_string() for arg in self.generic_origin.args
        )

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.name}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Type):
            return False

        if isinstance(self, AutoType) or isinstance(other, AutoType):
            return self is other
        if isinstance(self, UnionType) or isinstance(other, UnionType):
            return (
                isinstance(self, UnionType)
                and isinstance(other, UnionType)
                and self.type_members == other.type_members
            )
        if self.generic_origin is not None or other.generic_origin is not None:
            return self.generic_origin == other.generic_origin
        return self.name == other.name and self.definition_path == other.definition_path

    def __hash__(self) -> int:
        if self.generic_origin is not None:
            return hash(tuple(self.generic_origin.args))
        return hash(self.name)


class AutoType(Type):
    def __init__(self) -> None:
        super().__init__("auto_" + hex(id(self))[-4:], True)

    def get_id_string(self) -> str:
        raise RuntimeError


class UnionType(Type):
    def __init__(self, type_members: List[Type]):
        super().__init__("", True)
        self.custom_name: Optional[str] = None

        # Don't allow nested unions
        # TODO: what if member is autotype and gets later substituted with union?
        self.type_members: List[Type] = []
        for member in type_members:
            if isinstance(member, UnionType):
                self.type_members.extend(member.type_members)
            else:
                self.type_members.append(member)
        assert len(self.type_members) >= 2
        assert len(self.type_members) == len(set(self.type_members))

        # Consistent order
        self.type_members.sort(key=(lambda member: member.get_id_string()))

        self.methods["equals"] = FunctionType([self, self], BOOL)
        self.methods["to_string"] = FunctionType([self], STRING)
        if all("hash" in member.methods for member in self.type_members):
            self.methods["hash"] = FunctionType([self], INT)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {repr(self.name)}, type_members={self.type_members}>"

    def get_id_string(self) -> str:
        return "|".join(member.get_id_string() for member in self.type_members)

    # Equal unions may have different typedef names, Type.__hash__ isn't good
    def __hash__(self) -> int:
        return hash(tuple(self.type_members))

    @property
    def name(self) -> str:
        if self.custom_name is None:
            return "(%s)" % " | ".join(t.name for t in self.type_members)
        return self.custom_name


# does NOT inherit from type, optional isn't a type even though optional[str] is
@dataclass(eq=False)
class Generic:
    name: str

    def get_type(self, generic_args: List[Type]) -> Type:
        result = Type(
            self.name + "[" + ", ".join(arg.name for arg in generic_args) + "]", True
        )
        if self is LIST:
            [itemtype] = generic_args
            result.constructor_argtypes = []
            # TODO: hide __contains better?
            result.methods["__contains"] = FunctionType([result, itemtype], BOOL)
            result.methods["copy"] = FunctionType([result], result)
            result.methods["delete_at_index"] = FunctionType([result, INT], itemtype)
            result.methods["delete_slice"] = FunctionType([result, INT, INT], result)
            result.methods["ends_with"] = FunctionType([result, result], BOOL)
            result.methods["find_first"] = FunctionType([result, itemtype], INT)
            result.methods["find_last"] = FunctionType([result, itemtype], INT)
            result.methods["find_only"] = FunctionType([result, itemtype], INT)
            result.methods["first"] = FunctionType([result], itemtype)
            result.methods["delete_first"] = FunctionType([result, itemtype], None)
            result.methods["delete_last"] = FunctionType([result, itemtype], None)
            result.methods["delete_only"] = FunctionType([result, itemtype], None)
            result.methods["get"] = FunctionType([result, INT], itemtype)
            result.methods["insert"] = FunctionType([result, INT, itemtype], None)
            result.methods["last"] = FunctionType([result], itemtype)
            result.methods["length"] = FunctionType([result], INT)
            result.methods["pop"] = FunctionType([result], itemtype)
            result.methods["push"] = FunctionType([result, itemtype], None)
            result.methods["push_all"] = FunctionType([result, result], None)
            result.methods["reversed"] = FunctionType([result], result)
            result.methods["set"] = FunctionType([result, INT, itemtype], itemtype)
            result.methods["slice"] = FunctionType([result, INT, INT], result)
            result.methods["starts_with"] = FunctionType([result, result], BOOL)
            result.methods["to_string"] = FunctionType([result], STRING)
            # TODO: this is only for strings, but List[auto] may become List[Str] later
            # if itemtype is STRING:
            result.methods["join"] = FunctionType([result, STRING], STRING)
        elif self is MAPPING:
            [keytype, valtype] = generic_args
            itemlist = LIST.get_type([MAPPING_ENTRY.get_type([keytype, valtype])])
            result.constructor_argtypes = []
            result.methods["copy"] = FunctionType([result], result)
            result.methods["delete"] = FunctionType([result, keytype], None)
            result.methods["equals"] = FunctionType([result, result], BOOL)
            result.methods["get"] = FunctionType([result, keytype], valtype)
            result.methods["has_key"] = FunctionType([result, keytype], BOOL)
            result.methods["items"] = FunctionType([result], itemlist)
            result.methods["length"] = FunctionType([result], INT)
            result.methods["set"] = FunctionType([result, keytype, valtype], None)
            result.methods["to_string"] = FunctionType([result], STRING)
        elif self is MAPPING_ENTRY:
            [keytype, valtype] = generic_args
            result.members.append((keytype, "key"))
            result.members.append((valtype, "value"))
            result.methods["equals"] = FunctionType([result], result)
            result.methods["to_string"] = FunctionType([result], STRING)
        else:
            raise NotImplementedError
        result.generic_origin = GenericSource(self, generic_args)

        result.methods["equals"] = FunctionType([result, result], BOOL)
        return result


LIST = Generic("List")
MAPPING = Generic("Mapping")
MAPPING_ENTRY = Generic("MappingItem")


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
BOOL.methods["hash"] = FunctionType([BOOL], INT)

FLOAT.methods["ceil"] = FunctionType([FLOAT], INT)
FLOAT.methods["equals"] = FunctionType([FLOAT, FLOAT], BOOL)
FLOAT.methods["floor"] = FunctionType([FLOAT], INT)
FLOAT.methods["round"] = FunctionType([FLOAT], INT)
FLOAT.methods["to_string"] = FunctionType([FLOAT], STRING)
FLOAT.methods["truncate"] = FunctionType([FLOAT], INT)

INT.methods["equals"] = FunctionType([INT, INT], BOOL)
INT.methods["to_string"] = FunctionType([INT], STRING)
INT.methods["hash"] = FunctionType([INT], INT)

NULL_TYPE.methods["hash"] = FunctionType([NULL_TYPE], INT)
NULL_TYPE.methods["equals"] = FunctionType([NULL_TYPE, NULL_TYPE], BOOL)
NULL_TYPE.methods["to_string"] = FunctionType([NULL_TYPE], STRING)

STRING.methods["__contains"] = FunctionType([STRING, STRING], BOOL)
STRING.methods["center_pad"] = FunctionType([STRING, INT, STRING], STRING)
STRING.methods["count"] = FunctionType([STRING, STRING], INT)
STRING.methods["ends_with"] = FunctionType([STRING, STRING], BOOL)
STRING.methods["equals"] = FunctionType([STRING, STRING], BOOL)
STRING.methods["get_utf8"] = FunctionType([STRING], LIST.get_type([INT]))
STRING.methods["hash"] = FunctionType([STRING], INT)
STRING.methods["left_pad"] = FunctionType([STRING, INT, STRING], STRING)
STRING.methods["left_trim"] = FunctionType([STRING], STRING)
STRING.methods["length"] = FunctionType([STRING], INT)
STRING.methods["remove_prefix"] = FunctionType([STRING, STRING], STRING)
STRING.methods["remove_suffix"] = FunctionType([STRING, STRING], STRING)
STRING.methods["repeat"] = FunctionType([STRING, INT], STRING)
STRING.methods["replace"] = FunctionType([STRING, STRING, STRING], STRING)
STRING.methods["right_pad"] = FunctionType([STRING, INT, STRING], STRING)
STRING.methods["right_trim"] = FunctionType([STRING], STRING)
STRING.methods["split"] = FunctionType([STRING, STRING], LIST.get_type([STRING]))
STRING.methods["starts_with"] = FunctionType([STRING, STRING], BOOL)
STRING.methods["to_float"] = FunctionType([STRING], FLOAT)
STRING.methods["to_int"] = FunctionType([STRING], INT)
STRING.methods["to_string"] = FunctionType([STRING], STRING)  # does nothing
STRING.methods["trim"] = FunctionType([STRING], STRING)

builtin_types = {typ.name: typ for typ in [INT, FLOAT, BOOL, STRING, NULL_TYPE]}
builtin_generic_types = {gen.name: gen for gen in [LIST, MAPPING]}
