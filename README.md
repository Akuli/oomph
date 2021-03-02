# oomph
This is yet another attempt at making a usable programming language.

Commands:

```
python3 -m venv env
. env/bin/activate
pip install more_itertools black isort mypy pyflakes
make
./test
./lint
```

Test script passes its argument to oomph, try e.g. `./test --valgrind`

Type `python3 -m oomph foo.oomph` to compile and run `foo.oomph`.


## The language

- Compiles to C, aims to be high-level but faster than Python
- See example files in `tests` to get started
- Refcounted types are named `LikeThis`, non-refcounted pass-by-value types `like_this`
