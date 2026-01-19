"""
Jaw Dropper Dashboard (safe version)

Purpose: give Opus a live, read-only pulse on Python files without executing them.
Pulls brain_path from brain_config.json via workshop.config; no hardcoded paths or exec().
"""
from __future__ import annotations

import ast
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import dash
import pandas as pd
import plotly.express as px
from dash import dcc, html
from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from workshop.config import load_config
except Exception:  # fallback if workshop is missing
    def load_config() -> Dict:
        return {
            "brain_path": REPO_ROOT,
            "server_port": 8000,
            "_warning": "workshop.config not available; using repo root",
        }


SKIP_DIRS = {".git", "__pycache__", ".venv", "Logs", "Tests"}


def analyze_file(path: Path) -> Dict:
    """Static analysis: parse for syntax, docstring presence, and metadata."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        return {
            "path": str(path),
            "status": "read_error",
            "error": str(exc),
            "lines": 0,
            "size": path.stat().st_size if path.exists() else 0,
            "docstring": False,
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat()
            if path.exists()
            else "",
        }

    lines = text.count("\n") + 1
    size = path.stat().st_size
    modified = datetime.fromtimestamp(path.stat().st_mtime).isoformat()

    try:
        tree = ast.parse(text)
        ast.get_source_segment(text, tree)  # no-op to touch tree for coverage
        docstring_present = bool(ast.get_docstring(tree))
        status = "ok"
        error = ""
    except SyntaxError as exc:
        status = "syntax_error"
        docstring_present = False
        error = f"{exc.msg} (line {exc.lineno})"
    except Exception as exc:  # noqa: BLE001
        status = "parse_error"
        docstring_present = False
        error = str(exc)

    return {
        "path": str(path),
        "status": status,
        "error": error,
        "lines": lines,
        "size": size,
        "docstring": docstring_present,
        "modified": modified,
    }


def scan_repo(root: Path) -> pd.DataFrame:
    records: List[Dict] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # prune noise
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            file_path = Path(dirpath) / name
            records.append(analyze_file(file_path))
    return pd.DataFrame(records)


def build_app(root: Path) -> dash.Dash:
    app = dash.Dash(__name__)
    app.title = "Jaw Dropper Dashboard"

    app.layout = html.Div(
        [
            html.H1("Jaw Dropper Dashboard"),
            html.P(f"Brain path: {root}"),
            dcc.Interval(id="interval", interval=3_000, n_intervals=0),
            html.Div(
                [
                    html.Div(id="metric-total", className="metric"),
                    html.Div(id="metric-errors", className="metric"),
                    html.Div(id="metric-docs", className="metric"),
                ],
                style={"display": "flex", "gap": "24px"},
            ),
            dcc.Graph(id="quality-graph"),
            html.Div(id="error-list"),
        ],
        style={"fontFamily": "Arial, sans-serif", "padding": "24px"},
    )

    @app.callback(
        [
            Output("metric-total", "children"),
            Output("metric-errors", "children"),
            Output("metric-docs", "children"),
            Output("quality-graph", "figure"),
            Output("error-list", "children"),
        ],
        Input("interval", "n_intervals"),
    )
    def update_dashboard(n: int):
        if n is None:
            raise PreventUpdate

        df = scan_repo(root)
        if df.empty:
            return (
                "Total files: 0",
                "Errors: 0",
                "Docstrings: 0%",
                px.scatter(title="No data"),
                html.Div("No Python files found."),
            )

        total = len(df)
        errors = len(df[df["status"] != "ok"])
        doc_rate = round((df["docstring"].mean() or 0) * 100, 1)

        fig = px.histogram(
            df,
            x="status",
            title="File status distribution",
            category_orders={"status": ["ok", "syntax_error", "parse_error", "read_error"]},
        )

        top_errors = df[df["status"] != "ok"][["path", "status", "error"]].head(10)
        error_items = []
        for _, row in top_errors.iterrows():
            error_items.append(
                html.Div(
                    [
                        html.Strong(row["status"]),
                        html.Span(f" - {row['path']}"),
                        html.Div(row["error"], style={"color": "crimson"}),
                    ],
                    style={"marginBottom": "12px"},
                )
            )

        return (
            f"Total files: {total}",
            f"Errors: {errors}",
            f"Docstrings: {doc_rate}%",
            fig,
            error_items or html.Div("No errors detected."),
        )

    return app


def main() -> None:
    cfg = load_config()
    root = Path(cfg.get("brain_path", REPO_ROOT))
    app = build_app(root)
    app.run_server(debug=True, host="127.0.0.1", port=8050)


if __name__ == "__main__":
    main()
