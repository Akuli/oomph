# Oomph lexer for Pygments, based on the Python lexer
# https://github.com/pygments/pygments/blob/master/pygments/lexers/python.py
import re

from pygments.lexer import RegexLexer, bygroups, combined, default, include, words
from pygments.token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
)

from pyoomph.tokenizer import KEYWORDS

line_re = re.compile(".*?\n")


class CustomLexer(RegexLexer):
    name = "Oomph"
    aliases = ["oomph"]
    filenames = ["*.oomph"]
    mimetypes = []

    flags = re.MULTILINE | re.UNICODE

    id_regex = "[A-Za-z_][A-Za-z0-9_]*"

    def innerstring_rules(ttype):
        return [
            # the new style '{}'.format(...) string formatting
            (
                r"\{"
                r"((\w+)((\.\w+)|(\[[^\]]+\]))*)?"  # field name
                r"(\![sra])?"  # conversion
                r"(\:(.?[<>=\^])?[-+ ]?#?0?(\d+)?,?(\.\d+)?[E-GXb-gnosx%]?)?"
                r"\}",
                String.Interpol,
            ),
            # backslashes, quotes and formatting signs must be parsed one at a time
            (r'[^\\\'"%{\n]+', ttype),
            (r'[\'"\\]', ttype),
            # unhandled string formatting sign
            # newlines are an error (use "nl" state)
        ]

    def fstring_rules(ttype):
        return [
            # Assuming that a '}' is the closing brace after format specifier.
            # Sadly, this means that we won't detect syntax error. But it's
            # more important to parse correct syntax correctly, than to
            # highlight invalid syntax.
            (r"\}", String.Interpol),
            (r"\{", String.Interpol, "expr-inside-fstring"),
            # backslashes, quotes and formatting signs must be parsed one at a time
            (r'[^\\\'"{}\n]+', ttype),
            (r'[\'"\\]', ttype),
            # newlines are an error (use "nl" state)
        ]

    tokens = {
        "root": [
            (r"\n", Text),
            (
                r'^(\s*)([rRuUbB]{,2})("""(?:.|\n)*?""")',
                bygroups(Text, String.Affix, String.Doc),
            ),
            (
                r"^(\s*)([rRuUbB]{,2})('''(?:.|\n)*?''')",
                bygroups(Text, String.Affix, String.Doc),
            ),
            (r"\A#!.+$", Comment.Hashbang),
            (r"#.*$", Comment.Single),
            (r"\\\n", Text),
            (r"\\", Text),
            include("keywords"),
            (r"(def)((?:\s|\\\s)+)", bygroups(Keyword, Text), "funcname"),
            (r"(class)((?:\s|\\\s)+)", bygroups(Keyword, Text), "classname"),
            (r"(from)((?:\s|\\\s)+)", bygroups(Keyword.Namespace, Text), "fromimport"),
            (r"(import)((?:\s|\\\s)+)", bygroups(Keyword.Namespace, Text), "import"),
            include("expr"),
        ],
        "expr": [
            # non-raw f-strings
            (
                '(""")',
                bygroups(String.Double),
                combined("fstringescape", "tdqf"),
            ),
            (
                "(''')",
                bygroups(String.Single),
                combined("fstringescape", "tsqf"),
            ),
            (
                '(")',
                bygroups(String.Double),
                combined("fstringescape", "dqf"),
            ),
            (
                "(')",
                bygroups(String.Single),
                combined("fstringescape", "sqf"),
            ),
            (r"[^\S\n]+", Text),
            (r"!=|==|<<|>>|:=|[-~+/*%=<>&^|.]", Operator),
            (r"[]{}:(),;[]", Punctuation),
            (r"(in|is|and|or|not)\b", Operator.Word),
            include("builtins"),
            include("name"),
            include("numbers"),
        ],
        "expr-inside-fstring": [
            (r"[{([]", Punctuation, "expr-inside-fstring-inner"),
            # without format specifier
            (
                r"(=\s*)?"  # debug (https://bugs.python.org/issue36817)
                r"(\![sraf])?"  # conversion
                r"\}",
                String.Interpol,
                "#pop",
            ),
            # with format specifier
            # we'll catch the remaining '}' in the outer scope
            (
                r"(=\s*)?"  # debug (https://bugs.python.org/issue36817)
                r"(\![sraf])?"  # conversion
                r":",
                String.Interpol,
                "#pop",
            ),
            (r"\s+", Text),  # allow new lines
            include("expr"),
        ],
        "expr-inside-fstring-inner": [
            (r"[{([]", Punctuation, "expr-inside-fstring-inner"),
            (r"[])}]", Punctuation, "#pop"),
            (r"\s+", Text),  # allow new lines
            include("expr"),
        ],
        "keywords": [
            (
                words(tuple(KEYWORDS), suffix=r"\b"),
                Keyword,
            ),
        ],
        "builtins": [
            (
                words(
                    (
                        "print",
                        "Str",
                        "Int",
                        "Bool",
                        "Optional",
                        "List",
                        "true",
                        "false",
                        "null",
                    ),
                    prefix=r"(?<!\.)",
                    suffix=r"\b",
                ),
                Name.Builtin,
            ),
            (r"(?<!\.)(self)\b", Name.Builtin.Pseudo),
        ],
        "numbers": [
            (
                r"(\d(?:_?\d)*\.(?:\d(?:_?\d)*)?|(?:\d(?:_?\d)*)?\.\d(?:_?\d)*)"
                r"([eE][+-]?\d(?:_?\d)*)?",
                Number.Float,
            ),
            (r"\d(?:_?\d)*[eE][+-]?\d(?:_?\d)*j?", Number.Float),
            (r"0[oO](?:_?[0-7])+", Number.Oct),
            (r"0[bB](?:_?[01])+", Number.Bin),
            (r"0[xX](?:_?[a-fA-F0-9])+", Number.Hex),
            (r"\d(?:_?\d)*", Number.Integer),
        ],
        "name": [
            (id_regex, Name),
        ],
        "funcname": [
            (id_regex, Name.Function, "#pop"),
            default("#pop"),
        ],
        "classname": [
            (id_regex, Name.Class, "#pop"),
        ],
        "import": [
            (r"(\s+)(as)(\s+)", bygroups(Text, Keyword, Text)),
            (r"\.", Name.Namespace),
            (id_regex, Name.Namespace),
            (r"(\s*)(,)(\s*)", bygroups(Text, Operator, Text)),
            default("#pop"),  # all else: go back
        ],
        "fromimport": [
            (r"(\s+)(import)\b", bygroups(Text, Keyword.Namespace), "#pop"),
            (r"\.", Name.Namespace),
            # if None occurs here, it's "raise x from None", since None can
            # never be a module name
            (r"None\b", Name.Builtin.Pseudo, "#pop"),
            (id_regex, Name.Namespace),
            default("#pop"),
        ],
        "rfstringescape": [
            (r"\{\{", String.Escape),
            (r"\}\}", String.Escape),
        ],
        "fstringescape": [
            include("rfstringescape"),
            include("stringescape"),
        ],
        "stringescape": [
            (
                r'\\([\\abfnrtv"\']|\n|N\{.*?\}|u[a-fA-F0-9]{4}|'
                r"U[a-fA-F0-9]{8}|x[a-fA-F0-9]{2}|[0-7]{1,3})",
                String.Escape,
            )
        ],
        "fstrings-single": fstring_rules(String.Single),
        "fstrings-double": fstring_rules(String.Double),
        "strings-single": innerstring_rules(String.Single),
        "strings-double": innerstring_rules(String.Double),
        "dqf": [
            (r'"', String.Double, "#pop"),
            (r'\\\\|\\"|\\\n', String.Escape),  # included here for raw strings
            include("fstrings-double"),
        ],
        "sqf": [
            (r"'", String.Single, "#pop"),
            (r"\\\\|\\'|\\\n", String.Escape),  # included here for raw strings
            include("fstrings-single"),
        ],
        "dqs": [
            (r'"', String.Double, "#pop"),
            (r'\\\\|\\"|\\\n', String.Escape),  # included here for raw strings
            include("strings-double"),
        ],
        "sqs": [
            (r"'", String.Single, "#pop"),
            (r"\\\\|\\'|\\\n", String.Escape),  # included here for raw strings
            include("strings-single"),
        ],
        "tdqf": [
            (r'"""', String.Double, "#pop"),
            include("fstrings-double"),
            (r"\n", String.Double),
        ],
        "tsqf": [
            (r"'''", String.Single, "#pop"),
            include("fstrings-single"),
            (r"\n", String.Single),
        ],
        "tdqs": [
            (r'"""', String.Double, "#pop"),
            include("strings-double"),
            (r"\n", String.Double),
        ],
        "tsqs": [
            (r"'''", String.Single, "#pop"),
            include("strings-single"),
            (r"\n", String.Single),
        ],
    }
