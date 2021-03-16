# Oomph lexer for Pygments, see README for usage
#
# To try this thing for developing:
#   python3 -m pygments -x -l oomph_pygments_lexer.py tests/hello.oomph
import re

from pygments.lexer import Lexer
from pygments.token import Comment, Keyword, Name, Number, Operator, String, Text

from pyoomph.tokenizer import TOKEN_REGEX


class CustomLexer(Lexer):
    name = "Oomph"
    aliases = ["oomph"]
    filenames = ["*.oomph"]
    mimetypes = []

    def get_tokens_unprocessed(self, text):
        prev_end = 0
        for match in re.finditer(TOKEN_REGEX, text, flags=re.VERBOSE):
            tokentype = match.lastgroup
            assert tokentype is not None
            value = match.group()
            index = match.start()

#            if tokentype in {"indent", "error", "ignore"}:
#                continue

            for line in text[prev_end:index].splitlines(keepends=True):
                if "#" in line:
                    before, after = line.split("#", maxsplit=1)
                    if before:
                        yield (prev_end, Text, before)
                    yield (prev_end + len(before), Comment, "#" + after)
                else:
                    yield (prev_end, Text, line)
            prev_end = index + len(value)

            if tokentype == "keyword":
                yield (index, Keyword, value)
            elif tokentype in {"oneline_string", "multiline_string"}:
                # TODO: string formatting
                yield (index, String, value)
            elif tokentype in {"int", "float"}:
                yield (index, Number, value)
            elif tokentype == "identifier" or tokentype.startswith("assert_"):
                if "::" in value:
                    before, after = value.split("::")
                    yield (index, Name.Namespace, before)
                    yield (index + len(before), Operator, "::")
                    yield (index + len(before) + 2, Name, after)
                elif value in {
                    "Bool",
                    "Int",
                    "List",
                    "Optional",
                    "Str",
                    "assert",
                    "print",
                }:
                    yield (index, Name.Builtin, value)
                elif value in {
                    "false",
                    "null",
                    "true",
                }:
                    yield (index, Keyword, value)
                else:
                    yield (index, Name, value)
            elif tokentype == "op":
                yield (index, Operator, value)
            else:
                raise NotImplementedError(tokentype)
