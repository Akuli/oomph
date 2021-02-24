python3 -m venv env
. env/bin/activate
pip install more_itertools mypy isort
python3 -m compiler > out.c && make out && ./out
isort compiler
mypy --strict compiler
