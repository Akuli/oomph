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
    "typedef",
    "switch",
    "case",
    "auto",
    "generic",
    "new",
    "return",
    "noreturn",
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
builtins = ["List", "Mapping", "Bool", "Int", "Str", "Float", "assert", "print", "main"]

# Differences:
# - oneline strings can't include newlines
# - multiline strings can't include \n or \" (because those are unnecessary)
oneline_string_content = r'([^"{}\n\\]|\\[{}tn"\\])*'
multiline_string_content = r'([^"{}\\]|\\[{}t\\])*'


class CustomLexer(RegexLexer):
    name = "Oomph"
    aliases = ["oomph"]
    filenames = ["*.oomph"]

    tokens = {
        "root": [
            (r'("""|\})' + multiline_string_content + r'("""|\{)', String),
            (r'("|\})' + oneline_string_content + r'("|\{)', String),
            # keyword and builtins
            (r"\b(%s)\b" % "|".join(keywords + keywords_but_not_really), Keyword),
            (r"\b(%s)\b" % "|".join(builtins), Name.Builtin),
            # comment
            (r"#.*", Comment),
            # accept anything (lol)
            (".", Text),
        ]
    }
