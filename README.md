# RAW CLI (Local Dev)

## ✅ Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 🚀 Usage

```bash
cd examples/earthquakes
mxcp list
mxcp validate
mxcp test
mxcp run --param min_magnitude=5 tool query_recent_earthquakes           
mxcp serve
```

## 🧪 Tests

```bash
pytest tests/
```

## 🛠 VS Code

- Open this folder in VSCode
- Ensure interpreter is set to `.venv`
