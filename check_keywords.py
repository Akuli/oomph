# Builtins, keywords etc are mentioned in many places that can't just import
# them from one central place. This test ensures that they stay in sync.
import subprocess
import json
import sys

import oomph_pygments_lexer
import pyoomph.ir
import pyoomph.tokenizer
import pyoomph.types

pygments_names = (
    oomph_pygments_lexer.keywords
    + oomph_pygments_lexer.builtins
    + oomph_pygments_lexer.keywords_but_not_really
)
pyoomph_names = (
    pyoomph.tokenizer.TOKEN_REGEX.split(r"\b")[1].strip("() ").replace("|", " ").split()
    + [k for k in pyoomph.ir.visible_builtins.keys() if not k.startswith("__")]
    + list(pyoomph.types.builtin_types.keys())
    + list(pyoomph.types.builtin_generic_types.keys())
)
self_hosted_names = subprocess.run(
    [sys.executable, "-m", "pyoomph", "print_names.oomph"],
    capture_output=True,
    encoding="ascii",
    check=True,
).stdout.split()

vscode_names = []
for item in json.load(open("./oomph-vscode/syntaxes/oomph.tmLanguage.json"))[
    "repository"
]["keywords"]["patterns"]:
    pattern = item["match"]
    pattern = pattern[pattern.index("(") + 1 : pattern.rindex(")")]
    vscode_names.extend(pattern.split("|"))


# null is type and variable, it appears twice in compiler lists
pyoomph_names.remove("null")
self_hosted_names.remove("null")

# main is not really a built-in function, but it has special meaning
pygments_names.remove("main")

print("pyoomph:       ", sorted(pyoomph_names))
print("self-hosted:   ", sorted(self_hosted_names))
print("pygments lexer:", sorted(pygments_names))
print("oomph-vscode:  ", sorted(vscode_names))

assert (
    sorted(pyoomph_names)
    == sorted(self_hosted_names)
    == sorted(pygments_names)
    == sorted(vscode_names)
)
