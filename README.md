# Eye Tracking Course Report

[![Render Quarto Report to PDF](https://github.com/jnagasawa/ET-report/actions/workflows/render-pdf.yml/badge.svg)](https://github.com/jnagasawa/ET-report/actions/workflows/render-pdf.yml)

A Quarto book reporting the results of an eye-tracking study investigating spatial scanning biases in speakers of right-to-left and left-to-right languages.

## Structure

```
.
├── report/             # Quarto book source
│   ├── _quarto.yml     # book configuration (chapter order, output formats)
│   ├── index.qmd       # cover / preface
│   ├── chapters/       # chapter .qmd files
│   └── references.bib  # bibliography
├── data/
│   ├── raw/            # raw eye-tracking data (.tsv, .csv, log files) per subject
│   └── preprocessed/   # cleaned / processed data
├── scripts/            # analysis and plotting notebooks
├── src/                # reusable functions and modules
├── plots/              # exported figures (reproducible from scripts/)
├── experiment/         # OpenSesame experiment files
├── presentation/       # presentation slides
└── _research/          # work-in-progress notes and drafts
```

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

## Rendering the report

```bash
quarto render report            # builds all formats (html + pdf)
quarto render report --to pdf   # pdf only
quarto preview report           # live preview while editing
```

Output goes to `report/_book/` (git-ignored).

You can also use the [Quarto VS Code extension](https://marketplace.visualstudio.com/items?itemName=quarto.quarto) and click "Render Project" from the editor.

## Adding a chapter

1. Add a new `.qmd` file under `report/chapters/`.
2. Add its path to the `chapters:` list in `report/_quarto.yml`.

## CI

`.github/workflows/render-pdf.yml` renders the PDF on every push/PR to `main`/`develop` and uploads it as a build artifact (download from the run's "Artifacts" section on the Actions tab). On pushes to `main`, it also commits the rendered file back to the repo as `report.pdf`.

**Important:** after pushing to `main`, the bot's commit lands a few seconds later. Run `git pull` before making further commits, otherwise your local `main` will be behind and a later push may be rejected.
