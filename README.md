Commands:

```
python3 -m venv env
. env/bin/activate
pip install more_itertools black isort mypy pyflakes
make
./test
./lint
```

Test script passes its argument to compiler, try e.g. `./test --valgrind`

Type `python3 -m compiler foo.code` to compile and run `foo.code`.


## The language

- Refcounted types are named `LikeThis`, non-refcounted pass-by-value types `like_this`
