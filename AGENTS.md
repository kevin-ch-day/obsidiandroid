# AGENTS Instructions

These instructions apply to the entire repository.

## Code Style
- Follow [PEP 8](https://peps.python.org/pep-0008/) conventions.
- Use descriptive variable names and type hints where practical.
- Include docstrings for public modules, classes, and functions using Google-style format.

## Testing
- Install dependencies with `pip install -r requirements.txt`.
- Run all tests before committing using **one** of:
  - `pytest -q`
  - `./run_tests.sh`
  - `make test`
- Ensure tests pass and add new tests for new features or bug fixes.

## Miscellaneous
- Use `python clean_bytecode_cache.py` to remove `__pycache__` and log artifacts before committing.
- Optionally run `python run_ml_static_scan.py` to check for accidental `.predict()` misuse.
- Update relevant documentation (e.g., README.md) when making user-facing changes.
