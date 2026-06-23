# Eye Tracking Course Report

[![Render Quarto Report to PDF](https://github.com/jnagasawa/ET-report/actions/workflows/render-pdf.yml/badge.svg)](https://github.com/jnagasawa/ET-report/actions/workflows/render-pdf.yml)

A Quarto book reporting the results of an eye-tracking study (data analysis, figures, and discussion).

## Structure

- `index.qmd`, `chapters/` — book chapters (source for the report)
- `data/` — raw eye-tracking data (`.tsv`, `.csv`, log files) per subject
- `notebook/` — exploratory Jupyter notebooks
- `src/` — supporting scripts
- `img/` — images used in the report
- `_quarto.yml` — book configuration (chapter order, output formats)

## Setup

This project uses [uv](https://docs.astral.sh/uv/) to manage the Python environment.

```bash
uv sync
```

This installs Python (matplotlib, pandas, seaborn, etc.) into `.venv`, matching `uv.lock`.

You also need [Quarto](https://quarto.org/docs/get-started/) installed to render the report. For PDF output, Quarto needs a TeX distribution — either install one yourself or run:

```bash
quarto install tinytex
```

(Not needed if you already render PDFs through another tool, e.g. the VS Code Quarto extension with its own TeX setup.)

## Rendering the report

```bash
quarto render            # builds all formats configured in _quarto.yml (html + pdf)
quarto render --to pdf   # pdf only
quarto preview           # live preview while editing
```

Output goes to `_book/` (git-ignored).

You can also use the [Quarto VS Code extension](https://marketplace.visualstudio.com/items?itemName=quarto.quarto) and click "Render" from the editor.

## Adding a chapter

1. Add a new `.qmd` file under `chapters/`.
2. Add its path to the `chapters:` list in `_quarto.yml`.

## CI

`.github/workflows/render-pdf.yml` renders the PDF on every push/PR to `main`/`develop` and uploads it as a build artifact (download from the run's "Artifacts" section on the Actions tab). On pushes to `main`, it also commits the rendered file back to the repo as `report.pdf`.
