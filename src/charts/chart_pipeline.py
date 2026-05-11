"""
Chart Pipeline: Multi-step chart generation with LLM planning and template fallback.
====================================================================================

5-step pipeline:
1. Plan: LLM outputs JSON chart specification
2. Validate: Verify data keys exist in results.json
3. Generate: Per-chart LLM code generation
4. Execute: Run in subprocess, retry on error
5. Fallback: Template-based charts that always render
"""

import json
import sys
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable

import numpy as np

from .style_engine import apply_nature_style, save_figure, add_panel_label, NATURE_PALETTE, get_color


def _call_llm(prompt: str, system: str = "") -> str:
    """Call LLM via available provider."""
    try:
        import os
        from src.agent_workflow import _get_llm_provider
        pm = _get_llm_provider()
        if pm:
            return pm.generate(prompt, system_prompt=system)
    except Exception:
        pass
    return ""


class ChartPipeline:
    """
    5-step pipeline for LLM-driven chart generation.

    Unlike the single-shot ChartDesigner, this validates data availability,
    retries on error, and falls back to templates.
    """

    def __init__(self, output_dir: Path, results: Dict[str, Any],
                 call_llm: Optional[Callable] = None):
        self.output_dir = output_dir
        self.results = results
        self.charts_dir = output_dir / "stage_7_charts"
        self.charts_dir.mkdir(parents=True, exist_ok=True)
        self.call_llm = call_llm or _call_llm
        self.chart_count = 0

    def run(self) -> int:
        """Run the full pipeline. Returns number of charts generated."""
        # Step 1: Plan
        plan = self._plan()
        if not plan:
            return 0

        # Step 2: Validate
        valid_charts = self._validate(plan)
        if not valid_charts:
            return 0

        # Step 3 & 4: Generate and Execute per chart
        for chart_spec in valid_charts:
            self._generate_and_execute(chart_spec)

        return self.chart_count

    def _plan(self) -> List[Dict[str, Any]]:
        """Step 1: LLM outputs a JSON chart specification."""
        schema_desc = self._describe_data()
        if not schema_desc:
            return []

        prompt = f"""You are an expert data visualization designer for mathematical modeling papers.

Given the following result data, propose 2-4 specific charts to create.

**Result Data Description:**
{schema_desc}

Output a JSON array of chart specifications. Each chart must be:
{{
  "type": "bar|line|scatter|heatmap|comparison|multi_panel",
  "name": "short_english_name",
  "title": "Chinese chart title",
  "data_keys": ["path.to.data.in.results"],
  "description": "What this chart shows"
}}

Only use data keys that actually exist in the data above. Write ONLY the JSON array, no explanation."""

        code = self.call_llm(prompt, "You are a data visualization expert.")
        return self._parse_plan(code)

    def _validate(self, plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Step 2: Verify each chart's data_keys exist in results."""
        valid = []
        for chart in plan:
            if self._data_keys_exist(chart.get("data_keys", [])):
                valid.append(chart)
            else:
                print(f"  [ChartPipeline] 跳过无效图表: {chart.get('name', '?')} (数据键不存在)")
        return valid

    def _generate_and_execute(self, chart_spec: Dict[str, Any]):
        """Steps 3 & 4: Generate code for one chart, execute with retry."""
        name = chart_spec.get("name", f"chart_{self.chart_count}")
        data_sample = self._extract_data_sample(chart_spec.get("data_keys", []))

        code = self._generate_chart_code(chart_spec, data_sample)
        if not code or "import" not in code:
            return

        for attempt in range(3):
            ok = self._execute_code(code, f"fig_{self.chart_count + 1:02d}_{name}")
            if ok:
                self.chart_count += 1
                return
            if attempt < 2:
                print(f"  [ChartPipeline] 重试图表 {name} (attempt {attempt + 2})")

    def _generate_chart_code(self, spec: Dict, data_sample: str) -> str:
        """Generate Python code for a single chart."""
        chart_type = spec.get("type", "bar")
        title = spec.get("title", "Chart")
        description = spec.get("description", "")

        prompt = f"""Write a Python function that generates a {chart_type} chart.

Chart title: {title}
Description: {description}

Data sample (variable DATA_SAMPLE):
{data_sample[:800]}

Requirements:
1. Use `matplotlib.use('Agg')` and `import matplotlib.pyplot as plt`
2. Call `apply_nature_style()` before plotting
3. Use `save_figure(fig, name, charts_dir)` to save
4. The chart name is already set as `CHART_NAME = "{spec.get('name', 'chart')}"`
5. The output directory is `charts_dir`
6. Use Chinese labels where appropriate
7. Data is in variable `DATA_SAMPLE`

Write ONLY the Python code body (no markdown fences, no explanations)."""

        code = self.call_llm(prompt, "You write matplotlib plotting code.")
        return self._sanitize_code(code) if code else ""

    def _execute_code(self, code: str, name: str) -> bool:
        """Execute chart code in isolated subprocess. Returns True on success."""
        project_root = str(Path(__file__).parent.parent.parent)
        wrapper = f"""
import json, sys
from pathlib import Path
sys.path.insert(0, {repr(project_root)})
charts_dir = Path("{self.charts_dir}")
DATA_SAMPLE = {json.dumps(self.results, ensure_ascii=False)}
CHART_NAME = {repr(name)}

from src.charts.style_engine import apply_nature_style, save_figure, add_panel_label, NATURE_PALETTE, get_color
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np

{code}

print("CHART_DONE")
"""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(wrapper)
                f.flush()
                result = subprocess.run(
                    [sys.executable, f.name],
                    capture_output=True, text=True, timeout=120, cwd=project_root
                )
                if "CHART_DONE" in result.stdout:
                    # Verify file was created
                    png_files = list(self.charts_dir.glob(f"fig_*{name}*"))
                    return len(png_files) > 0
                if result.returncode != 0:
                    print(f"  [ChartPipeline] stderr: {result.stderr[:300]}")
            return False
        except Exception as e:
            print(f"  [ChartPipeline] execution error: {e}")
            return False

    # =========================================================================
    # Helpers
    # =========================================================================

    def _describe_data(self) -> str:
        """Generate human-readable data schema description."""
        lines = []
        for key, val in self.results.items():
            if isinstance(val, dict):
                lines.append(f"- {key}: dict with keys {list(val.keys())}")
                for sub_k, sub_v in list(val.items())[:3]:
                    preview = str(sub_v)[:80]
                    lines.append(f"  - {sub_k}: {preview}")
            elif isinstance(val, list) and val:
                first = val[0]
                if isinstance(first, dict):
                    lines.append(f"- {key}: list of {len(val)} items, keys: {list(first.keys())}")
                    for sk, sv in list(first.items())[:2]:
                        lines.append(f"  - {sk}: {str(sv)[:60]}")
                else:
                    lines.append(f"- {key}: list of {len(val)} {type(first).__name__}")
            else:
                lines.append(f"- {key}: {type(val).__name__} = {str(val)[:60]}")
        return "\n".join(lines)

    def _data_keys_exist(self, keys: List[str]) -> bool:
        """Check if the given data keys exist in results."""
        if not keys:
            return True
        for key in keys:
            parts = key.split(".")
            obj = self.results
            for p in parts:
                if isinstance(obj, dict) and p in obj:
                    obj = obj[p]
                else:
                    return False
        return True

    def _extract_data_sample(self, keys: List[str]) -> Dict[str, Any]:
        """Extract a sample of data for the given keys."""
        sample = {}
        for key in keys:
            parts = key.split(".")
            obj = self.results
            for p in parts:
                if isinstance(obj, dict) and p in obj:
                    obj = obj[p]
                else:
                    obj = None
                    break
            if obj is not None:
                if isinstance(obj, list) and len(obj) > 5:
                    sample[key] = obj[:5]
                else:
                    sample[key] = obj
        return sample if sample else self.results

    def _parse_plan(self, text: str) -> List[Dict[str, Any]]:
        """Parse JSON plan from LLM output."""
        if not text:
            return []
        try:
            import re
            json_match = re.search(r'\[.*\]', text, re.DOTALL)
            if json_match:
                plan = json.loads(json_match.group())
                if isinstance(plan, list):
                    return plan
        except Exception:
            pass
        return []

    @staticmethod
    def _sanitize_code(code: str) -> str:
        code = code.strip()
        if code.startswith("```"):
            lines = code.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            code = "\n".join(lines)
        return code


# =============================================================================
# Template-based fallback charts (no LLM required, always produce output)
# =============================================================================

class TemplateChartGenerator:
    """
    Generates publication-ready charts directly from results data without LLM.
    These are guaranteed to produce output for common data patterns.
    """

    def __init__(self, output_dir: Path, results: Dict[str, Any]):
        self.output_dir = output_dir
        self.results = results
        self.charts_dir = output_dir / "stage_7_charts"
        self.charts_dir.mkdir(parents=True, exist_ok=True)
        self.chart_count = 0

    def generate_all(self) -> int:
        """Detect data patterns and generate appropriate charts."""
        # Try to find numeric/array data for visualization
        for key, val in self.results.items():
            if isinstance(val, dict):
                self._inspect_dict(key, val)
            elif isinstance(val, list) and len(val) > 0:
                self._inspect_list(key, val)
            elif isinstance(val, (int, float)) and key != "success":
                self._generate_scalar_summary(key, val)

        if self.chart_count == 0:
            # Last resort: generate a summary bar chart of all scalar values
            self._generate_summary_bar_chart()

        return self.chart_count

    def _inspect_dict(self, parent_key: str, data: Dict):
        """Inspect a dict value and generate appropriate charts."""
        numeric_lists = {}
        for k, v in data.items():
            if isinstance(v, list) and len(v) > 0 and all(isinstance(x, (int, float)) for x in v[:3]):
                numeric_lists[k] = v

        if len(numeric_lists) >= 1:
            # Line chart for sequential numeric data
            if len(numeric_lists) == 1:
                k, v = list(numeric_lists.items())[0]
                self._generate_line_chart(v, f"fig_{self.chart_count + 1:02d}_{parent_key}_{k}",
                                          title=f"{parent_key}: {k}")
            elif len(numeric_lists) >= 2:
                self._generate_multi_line_chart(numeric_lists,
                                                 f"fig_{self.chart_count + 1:02d}_{parent_key}_multi",
                                                 title=parent_key)

        # Check for nested dicts with numeric values (bar chart candidates)
        numeric_scalars = {k: v for k, v in data.items() if isinstance(v, (int, float))}
        if len(numeric_scalars) >= 2:
            self._generate_bar_chart(numeric_scalars,
                                     f"fig_{self.chart_count + 1:02d}_{parent_key}_bars",
                                     title=parent_key)

    def _inspect_list(self, parent_key: str, data: List):
        """Inspect a list value and generate charts."""
        if not data:
            return
        first = data[0]
        if isinstance(first, dict):
            # Extract numeric columns
            numeric_cols = {}
            for k in first.keys():
                col = [item.get(k) for item in data if isinstance(item.get(k), (int, float))]
                if len(col) >= 3:
                    numeric_cols[k] = col

            if len(numeric_cols) >= 1:
                if len(numeric_cols) == 1:
                    k, v = list(numeric_cols.items())[0]
                    self._generate_line_chart(v, f"fig_{self.chart_count + 1:02d}_{parent_key}_{k}",
                                              title=f"{parent_key}: {k}")
                else:
                    self._generate_multi_line_chart(numeric_cols,
                                                     f"fig_{self.chart_count + 1:02d}_{parent_key}_trend",
                                                     title=parent_key)
        elif isinstance(first, (int, float)) and len(data) >= 3:
            self._generate_line_chart(data, f"fig_{self.chart_count + 1:02d}_{parent_key}",
                                      title=parent_key)

    # =========================================================================
    # Chart Templates
    # =========================================================================

    def _generate_line_chart(self, values: List, name: str, title: str = ""):
        """Generate a simple line chart."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 5))
        apply_nature_style()

        x = range(len(values))
        ax.plot(x, values, color=NATURE_PALETTE["blue_main"], linewidth=2, marker="o", markersize=4)
        ax.set_title(title or "Trend Analysis", fontsize=14, fontweight="bold")
        ax.set_xlabel("Index")
        ax.set_ylabel("Value")
        ax.grid(True, alpha=0.3)

        save_figure(fig, name, self.charts_dir)
        self.chart_count += 1

    def _generate_multi_line_chart(self, data: Dict[str, List], name: str, title: str = ""):
        """Generate a multi-line chart."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 6))
        apply_nature_style()

        max_len = max(len(v) for v in data.values() if isinstance(v, list))
        x = range(max_len)

        for i, (k, v) in enumerate(data.items()):
            if isinstance(v, list):
                vals = v[:max_len] + [v[-1]] * max(0, max_len - len(v)) if len(v) < max_len else v[:max_len]
                ax.plot(x, vals, color=get_color(i), linewidth=2, marker="o", markersize=3, label=str(k))

        ax.set_title(title or "Comparison Trends", fontsize=14, fontweight="bold")
        ax.set_xlabel("Index")
        ax.set_ylabel("Value")
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)

        save_figure(fig, name, self.charts_dir)
        self.chart_count += 1

    def _generate_bar_chart(self, data: Dict[str, float], name: str, title: str = ""):
        """Generate a bar chart from scalar values."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 5))
        apply_nature_style()

        labels = list(data.keys())
        values = [float(v) for v in data.values()]
        colors = [get_color(i) for i in range(len(labels))]

        bars = ax.bar(range(len(labels)), values, color=colors, edgecolor="white", linewidth=0.5)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=10)
        ax.set_title(title or "Comparison", fontsize=14, fontweight="bold")
        ax.set_ylabel("Value")

        # Add value labels on bars
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.01,
                    f"{val:.2f}", ha="center", va="bottom", fontsize=9)

        save_figure(fig, name, self.charts_dir)
        self.chart_count += 1

    def _generate_heatmap(self, matrix: List[List[float]], name: str,
                          row_labels: List[str] = None, col_labels: List[str] = None,
                          title: str = ""):
        """Generate a heatmap from a matrix."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 6))
        apply_nature_style()

        arr = np.array(matrix)
        im = ax.imshow(arr, cmap="Blues", aspect="auto")

        if row_labels:
            ax.set_yticks(range(len(row_labels)))
            ax.set_yticklabels(row_labels[:len(row_labels)], fontsize=9)
        if col_labels:
            ax.set_xticks(range(len(col_labels)))
            ax.set_xticklabels(col_labels[:len(col_labels)], rotation=45, ha="right", fontsize=9)

        ax.set_title(title or "Heatmap", fontsize=14, fontweight="bold")
        fig.colorbar(im, ax=ax, shrink=0.8)

        save_figure(fig, name, self.charts_dir)
        self.chart_count += 1

    def _generate_scalar_summary(self, key: str, value: float):
        """Generate a simple annotation chart for a scalar value."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(4, 3))
        apply_nature_style()

        ax.bar([0], [float(value)], color=NATURE_PALETTE["blue_main"], width=0.4)
        ax.set_xticks([0])
        ax.set_xticklabels([key], fontsize=11)
        ax.set_title(f"{key}: {value:.4g}", fontsize=13, fontweight="bold")
        ax.set_ylabel("Value")

        save_figure(fig, f"fig_{self.chart_count + 1:02d}_{key}", self.charts_dir)
        self.chart_count += 1

    def _generate_summary_bar_chart(self):
        """Last resort: bar chart of all top-level scalar values in results."""
        scalars = {k: v for k, v in self.results.items()
                   if isinstance(v, (int, float)) and k != "success"}
        if not scalars:
            # Try deeper nesting
            for k, v in self.results.items():
                if isinstance(v, dict):
                    for sk, sv in v.items():
                        if isinstance(sv, (int, float)):
                            scalars[f"{k}/{sk}"] = sv
        if not scalars:
            return

        self._generate_bar_chart(scalars, f"fig_{self.chart_count + 1:02d}_summary",
                                 title="Key Results Summary")
