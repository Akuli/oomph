# Oomph lexer for Pygments, see README for usage
#
# To try this thing for developing:
#   python3 -m pygments -x -l oomph_pygments_lexer.py tests/hello.oomph

from pygments.lexer import RegexLexer
from pygments.token import Comment, Keyword, Name, String, Text


# Keep up to date with oomph compiler tokenizers
keywords = [
    "let",
    "import",
    "as",
    "export",
    "func",
    "meth",
    "class",
    "union",
    "switch",
    "case",
    "auto",
    "generic",
    "new",
    "return",
    "pass",
    "mod",
    "and",
    "or",
    "not",
    "in",
    "if",
    "elif",
    "else",
    "while",
    "for",
    "foreach",
    "of",
    "continue",
    "break",
]

keywords_but_not_really = ["true", "false", "null"]
builtins = ["Bool", "Int", "List", "Optional", "Str", "assert", "print", "main"]

oneline_string_content = r'([^"{}\\]|\\[{}tn"\\])*'
multiline_string_content = oneline_string_content.replace('n"', '')  # no \n or \"


class CustomLexer(RegexLexer):
    name = "Oomph"
    aliases = ["oomph"]
    filenames = ["*.oomph"]

    tokens = {
        "root": [
            (r'("|\})' + oneline_string_content + r'("|\{)', String),
            (r'("""|\})' + multiline_string_content + r'("""|\{)', String),
            # keyword and builtins
            (r"\b(%s)\b" % "|".join(keywords + keywords_but_not_really), Keyword),
            (r"\b(%s)\b" % "|".join(builtins), Name.Builtin),
            # comment
            (r"#.*", Comment),
            # accept anything (lol)
            (".", Text),
        ]
    }
