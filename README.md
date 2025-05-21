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
raw list
raw validate
raw test
raw run --param min_magnitude=5 tool query_recent_earthquakes           
raw serve
```

## 🧪 Tests

```bash
pytest tests/
```

## 🛠 VS Code

- Open this folder in VSCode
- Ensure interpreter is set to `.venv`
- You can debug CLI commands via `.vscode/launch.json`
