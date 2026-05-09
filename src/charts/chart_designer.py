"""
LLM-driven chart designer.
Generates plotting code dynamically based on result data schema.
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any

from .style_engine import apply_nature_style, save_figure, NATURE_PALETTE


def _call_llm(prompt: str, system: str = "") -> str:
    """Call LLM via available provider."""
    try:
        import os
        # Use the same provider initialization as agent_workflow
        from src.agent_workflow import _get_llm_provider
        pm = _get_llm_provider()
        if pm:
            return pm.generate(prompt, system_prompt=system)
    except Exception:
        pass
    return ""


class ChartDesigner:
    """Designs and executes charts based on result data."""

    def __init__(self, output_dir: Path, results: Dict[str, Any]):
        self.output_dir = output_dir
        self.results = results
        self.charts_dir = output_dir / "stage_7_charts"
        self.charts_dir.mkdir(parents=True, exist_ok=True)

    def design_and_draw(self) -> int:
        """Generate chart code via LLM and execute it. Returns chart count."""
        schema_desc = self._describe_schema()
        if not schema_desc:
            return 0

        prompt = f"""You are an expert data visualization designer for mathematical modeling papers.

Given the following result data schema and sample values, write a Python script that generates 2-4 publication-ready matplotlib figures using the provided API.

**Result Data Description:**
{schema_desc}

**Available API (already imported):**
- `apply_nature_style(font_size=14, lw=2)` - sets Nature-style font/spine defaults
- `save_figure(fig, name, out_dir, dpi=300)` - saves both .png and .svg
- `add_panel_label(ax, label, fs=12)` - adds panel label like 'a', 'b'
- `NATURE_PALETTE` - dict of colors: blue_main="#0F4D92", green_3="#8BCF8B", red_strong="#B64342", teal="#42949E", violet="#9A4D8E", neutral_light="#CFCECE"
- `get_color(i)` - cycles through a strong color list

**Requirements:**
1. Use `matplotlib.use('Agg')` and `import matplotlib.pyplot as plt`
2. Each figure should be saved with `save_figure(fig, "fig_01_xxx", charts_dir)` etc.
3. Use Chinese labels where appropriate (set font to support CJK)
4. Create meaningful visualizations: time-series, bar charts, heatmaps, scatter plots, etc.
5. Only write the plotting code, no data loading (data is in variable `RESULTS`)
6. The output directory is in variable `charts_dir`

Write ONLY the Python code body (no markdown fences, no explanations).
"""

        code = _call_llm(prompt, "You are a matplotlib expert generating charts for academic papers.")
        if not code or "import" not in code:
            return 0

        code = self._sanitize_code(code)
        return self._execute_code(code)

    def _describe_schema(self) -> str:
        """Generate a human-readable schema description from results."""
        lines = []
        for key, val in self.results.items():
            if isinstance(val, dict):
                lines.append(f"- {key}: dict with keys {list(val.keys())}")
                for sub_k, sub_v in list(val.items())[:3]:
                    preview = str(sub_v)[:80]
                    lines.append(f"  - {sub_k}: {preview}")
            elif isinstance(val, list) and val:
                lines.append(f"- {key}: list of {len(val)} items, first item keys: {list(val[0].keys()) if isinstance(val[0], dict) else type(val[0]).__name__}")
            else:
                lines.append(f"- {key}: {type(val).__name__} = {str(val)[:60]}")
        return "\n".join(lines)

    def _sanitize_code(self, code: str) -> str:
        """Remove markdown fences and fix common issues."""
        code = code.strip()
        if code.startswith("```"):
            lines = code.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            code = "\n".join(lines)
        return code

    def _execute_code(self, code: str) -> int:
        """Execute generated plotting code in isolated process."""
        project_root = str(Path(__file__).parent.parent.parent)
        wrapper = f"""
import json, sys
from pathlib import Path
sys.path.insert(0, {repr(project_root)})
charts_dir = Path("{self.charts_dir}")
RESULTS = {json.dumps(self.results, ensure_ascii=False)}

from src.charts.style_engine import apply_nature_style, save_figure, add_panel_label, NATURE_PALETTE, get_color
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np

{code}

print("CHARTS_DONE")
"""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(wrapper)
                f.flush()
                result = subprocess.run(
                    [sys.executable, f.name],
                    capture_output=True, text=True, timeout=120, cwd=project_root
                )
                if "CHARTS_DONE" in result.stdout:
                    return result.stdout.count("CHARTS_DONE") + result.stdout.count("save_figure")
                if result.returncode != 0:
                    print(f"  [ChartDesigner] stderr: {result.stderr[:300]}")
            return 0
        except Exception as e:
            print(f"  [ChartDesigner] execution error: {e}")
            return 0
