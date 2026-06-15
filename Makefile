.PHONY: install dev test lint format clean run-demo

PYTHON = python
PIP = pip

install:
	$(PIP) install -r requirements.txt

dev:
	$(PIP) install -e ".[dev]"

test:
	$(PYTHON) -m pytest -q

test-cov:
	$(PYTHON) -m pytest -q --cov=memoryx --cov-report=term

lint:
	ruff check memoryx/ tests/

format:
	ruff format memoryx/ tests/

clean:
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('.pytest_cache')]"
	$(PYTHON) -c "import pathlib; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]"

run-demo:
	$(PYTHON) -c "from memoryx import MemoryBank; print('memoryx loaded')"