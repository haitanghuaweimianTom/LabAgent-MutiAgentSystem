"""figure_audit 单元测试：去重 / 代码-caption 核对 / 引用完整性。"""
import tempfile
from pathlib import Path

from app.core.figure_audit import audit_figures


def _make_img(path: Path, content: bytes = b"fake_png_data_12345"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_duplicate_figure_detected_and_removed(tmp_path):
    charts = tmp_path / "charts"
    img1 = charts / "fig1.png"
    img2 = charts / "fig2.png"
    _make_img(img1, b"identical_content")
    _make_img(img2, b"identical_content")

    latex = r"""
\section{Results}
\begin{figure}[H]
\centering
\includegraphics[width=0.8\textwidth]{charts/fig1.png}
\caption{Figure one}\label{fig:one}
\end{figure}
Some text \ref{fig:one}.
\begin{figure}[H]
\centering
\includegraphics[width=0.8\textwidth]{charts/fig2.png}
\caption{Figure two}\label{fig:two}
\end{figure}
More text \ref{fig:two}.
"""
    issues, patched = audit_figures(latex, [], tmp_path)
    dup_issues = [i for i in issues if i["category"] == "duplicate_figure"]
    assert len(dup_issues) == 1
    assert r"\label{fig:two}" not in patched
    assert r"\label{fig:one}" in patched


def test_missing_ref_detected(tmp_path):
    charts = tmp_path / "charts"
    _make_img(charts / "fig1.png")

    latex = r"""
\begin{figure}[H]
\includegraphics{charts/fig1.png}
\caption{A figure}\label{fig:orphan}
\end{figure}
No reference here.
"""
    issues, _ = audit_figures(latex, [], tmp_path)
    ref_issues = [i for i in issues if i["category"] == "unreferenced_figure"]
    assert len(ref_issues) == 1
    assert "fig:orphan" in ref_issues[0]["message"]


def test_caption_code_mismatch_detected(tmp_path):
    charts = tmp_path / "charts"
    _make_img(charts / "fig1.png")
    code = charts / "fig1_code.py"
    code.write_text(
        "import matplotlib.pyplot as plt\n"
        "plt.title('房价预测趋势')\n"
        "plt.xlabel('年份')\n"
        "plt.ylabel('GDP增长率')\n"
        "plt.savefig('fig1.png')\n",
        encoding="utf-8",
    )

    latex = r"""
\begin{figure}[H]
\includegraphics{charts/fig1.png}
\caption{这个图展示的是股票收益率与通货膨胀的关系}\label{fig:mismatch}
\end{figure}
如图 \ref{fig:mismatch} 所示。
"""
    issues, _ = audit_figures(latex, [], tmp_path)
    mismatch = [i for i in issues if i["category"] == "caption_code_mismatch"]
    assert len(mismatch) == 1


def test_no_issues_when_consistent(tmp_path):
    charts = tmp_path / "charts"
    _make_img(charts / "fig1.png")
    code = charts / "fig1_code.py"
    code.write_text(
        "plt.title('房价预测趋势分析')\n"
        "plt.xlabel('年份')\n"
        "plt.ylabel('房价')\n",
        encoding="utf-8",
    )

    latex = r"""
\begin{figure}[H]
\includegraphics{charts/fig1.png}
\caption{房价预测趋势分析：年份与房价的关系}\label{fig:good}
\end{figure}
如图 \ref{fig:good} 所示，房价呈上升趋势。
"""
    issues, _ = audit_figures(latex, [], tmp_path)
    errors = [i for i in issues if i["severity"] == "error"]
    assert len(errors) == 0


def test_agent_code_field_used(tmp_path):
    charts = tmp_path / "charts"
    _make_img(charts / "fig1.png")

    figures = [{
        "figure_id": "fig1",
        "figure_path": str(charts / "fig1.png"),
        "code": "plt.title('收入分析')\nplt.xlabel('季度')\n",
        "success": True,
    }]

    latex = r"""
\begin{figure}[H]
\includegraphics{charts/fig1.png}
\caption{误差率与残差的关系}\label{fig:x}
\end{figure}
\ref{fig:x}
"""
    issues, _ = audit_figures(latex, figures, tmp_path)
    mismatch = [i for i in issues if i["category"] == "caption_code_mismatch"]
    assert len(mismatch) == 1


def test_duplicate_caption_detected(tmp_path):
    charts = tmp_path / "charts"
    _make_img(charts / "fig1.png", b"content_a")
    _make_img(charts / "fig2.png", b"content_b")

    latex = r"""
\begin{figure}[H]
\includegraphics{charts/fig1.png}
\caption{土地出让收入与地方财政收入比演变}\label{fig:a}
\end{figure}
如图 \ref{fig:a} 所示。
\begin{figure}[H]
\includegraphics{charts/fig2.png}
\caption{土地出让收入与地方财政收入比演变图}\label{fig:b}
\end{figure}
如图 \ref{fig:b} 所示。
"""
    issues, _ = audit_figures(latex, [], tmp_path)
    dup_cap = [i for i in issues if i["category"] == "duplicate_caption"]
    assert len(dup_cap) == 1
    assert dup_cap[0]["severity"] == "error"


def test_distinct_captions_no_duplicate(tmp_path):
    charts = tmp_path / "charts"
    _make_img(charts / "fig1.png", b"content_a")
    _make_img(charts / "fig2.png", b"content_b")

    latex = r"""
\begin{figure}[H]
\includegraphics{charts/fig1.png}
\caption{土地出让收入与地方财政收入比演变}\label{fig:a}
\end{figure}
如图 \ref{fig:a} 所示。
\begin{figure}[H]
\includegraphics{charts/fig2.png}
\caption{城投有息负债分省排名}\label{fig:b}
\end{figure}
如图 \ref{fig:b} 所示。
"""
    issues, _ = audit_figures(latex, [], tmp_path)
    dup_cap = [i for i in issues if i["category"] == "duplicate_caption"]
    assert len(dup_cap) == 0
