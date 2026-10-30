# Dependencies and installation

## Runtime

- Python: 3.11 or newer (`pyproject.toml`); verified with Python 3.12.13 on Windows 11.
- Required package: NumPy 1.24 or newer; verified with NumPy 2.3.5.
- Packaging/build: pip and setuptools 68 or newer.

Python standard-library modules provide HTTP servers/clients, JSON-RPC handling, threading, hashing, CLI parsing, CSV/JSON storage, and tests. There is no runtime dependency on Flask, FastAPI, requests, scikit-learn, SciPy, PyTorch, or TensorFlow.

## Capability matrix

| Capability | Required dependencies |
|---|---|
| Core Sentinel | Python + NumPy |
| HTTP MCP gateway | Python standard library + core Sentinel |
| Mock MCP server | Python standard library |
| Complete test suite | Project + NumPy; `unittest` is standard library |
| Classical research experiments | NumPy |
| LSTM/Transformer comparisons | NumPy; these are constrained NumPy implementations |
| SVG/table generation | Python standard library + NumPy |

Everything needed for the local demo is required, not optional. No optional external package is currently necessary. PyTorch/TensorFlow would only be relevant to a future, separate end-to-end sequence study.

## Fresh PowerShell installation

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

If internet access is intentionally unavailable but compatible NumPy and setuptools are already visible to the environment, create the environment with inherited packages and disable isolated build dependency downloads:

```powershell
py -3.12 -m venv --system-site-packages .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --no-deps --no-build-isolation -e .
```

The offline command was required in the verified restricted environment because ordinary build isolation attempted to download `setuptools>=68`. This is an environment/network limitation, not a Sentinel import failure.

## Verification

```powershell
python --version
python -m pip --version
python -c "import numpy, sentinel; print(numpy.__version__)"
python -m unittest discover -s tests -v
python -m compileall -q sentinel tests
python -m sentinel.final_verification
```
