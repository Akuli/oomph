# Builtins, keywords etc are mentioned in many places that can't just import
# them from one central place. This test ensures that they stay in sync.
import subprocess
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

pyoomph_names.remove("null")  # type and keyword, appears twice
self_hosted_names.remove("null")  # type and keyword, appears twice
pygments_names.remove("main")  # not really builtin, but still special

print("pyoomph:       ", sorted(pyoomph_names))
print("self-hosted:   ", sorted(self_hosted_names))
print("pygments lexer:", sorted(pygments_names))

assert sorted(pyoomph_names) == sorted(self_hosted_names) == sorted(pygments_names)
