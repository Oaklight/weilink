# Installation

## From PyPI

```bash
pip install weilink
```

## From Source

```bash
git clone https://github.com/Oaklight/weilink.git
cd weilink
pip install -e .
```

## Requirements

- Python >= 3.10
- No external dependencies (AES uses OpenSSL via ctypes if available; pure-Python fallback included)
