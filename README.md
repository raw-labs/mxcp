# RAW CLI (Local Dev)

## ✅ Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 🚀 Usage

```bash
raw list
raw run examples/hello.yml --param=value
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