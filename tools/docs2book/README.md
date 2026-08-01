# docs2book

`docs2book` is a standalone, reusable CLI tool that transforms a folder of Markdown documentation into a beautifully formatted, printable PDF book with cover page, table of contents, unified heading hierarchy, code highlighting, and footnote links.

## Requirements & Installation (Debian / Ubuntu aarch64)

### 1. System Dependencies & Binaries
Install system font and graphics libraries:
```bash
sudo apt update && sudo apt install -y pandoc python3 python3-pip python3-venv \
  libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev \
  shared-mime-info fonts-liberation poppler-utils
```

Install **Typst** (static binary for Linux `aarch64`):
```bash
mkdir -p ~/.local/bin
curl -L -o /tmp/typst.tar.xz https://github.com/typst/typst/releases/download/v0.15.1/typst-aarch64-unknown-linux-musl.tar.xz
tar -xf /tmp/typst.tar.xz -C /tmp
cp /tmp/typst-aarch64-unknown-linux-musl/typst ~/.local/bin/
chmod +x ~/.local/bin/typst
```

Install **Pandoc** (static binary for Linux `arm64` if not available in apt):
```bash
curl -L -o /tmp/pandoc.tar.gz https://github.com/jgm/pandoc/releases/download/3.10.1/pandoc-3.10.1-linux-arm64.tar.gz
tar -xf /tmp/pandoc.tar.gz -C /tmp
cp /tmp/pandoc-3.10.1/bin/pandoc ~/.local/bin/
chmod +x ~/.local/bin/pandoc
```

Ensure `~/.local/bin` is in your `PATH`.

### 2. Python Virtual Environment
Set up the Python venv and install dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick Start Example

Run `docs2book` using default `--engine auto`:
```bash
python3 build_book.py --docs /path/to/any/docs --out ./Book.pdf --title "My Documentation Book" --author "Author Name" --lang en
```

## Command Line Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `--docs` | **Yes** | - | Path to the directory containing `.md` files. |
| `--out` | **Yes** | - | Output path for the generated PDF book. |
| `--title` | No | `"Documentation"` | Title displayed on the book cover and metadata. |
| `--author` | No | `"docs2book"` | Author displayed on the book cover and metadata. |
| `--lang` | No | `"en"` | Language code (`en`, `uk`). Configures hyphenation and TOC title. |
| `--engine` | No | `"auto"` | Execution engine: `auto`, `typst`, or `weasyprint`. |

## Engine Selection

- **`auto` (Default)**: Primary engine is **Typst** (`pandoc` -> `.typ` -> `typst compile`). If `pandoc`/`typst` are not installed or if Typst compilation fails, `docs2book` automatically falls back to **WeasyPrint** (`markdown2` + Pygments + Jinja2 + WeasyPrint).
- **`typst`**: Forces the Pandoc + Typst pipeline.
- **`weasyprint`**: Forces the Python + WeasyPrint HTML/CSS rendering pipeline.

## Known Limitations & Notes

- **Ukrainian (`--lang uk`)**: Supported in configuration (hyphenation, `"Зміст"` TOC header, `"Вступ"` default root index title), but tested primarily with English (`en`) documentation content when sample Ukrainian fixture docs are unavailable.
