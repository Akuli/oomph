Commands:

```
python3 -m venv env
. env/bin/activate
pip install more_itertools black isort mypy pyflakes
make
./test
black compiler
isort compiler
mypy --strict compiler
pyflakes compiler
```

Test script passes its argument to compiler, try e.g. `./test --valgrind`

Type `python3 -m compiler foo.code` to compile and run `foo.code`.
