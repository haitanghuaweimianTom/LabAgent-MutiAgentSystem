"""Tests for CodeSandbox, QualityGate, MultiModelDebate, FigureGenerator, AntiPatternDetector, CodeAutoFixer."""
import ast
import tempfile
from pathlib import Path
from scripts.sandbox_and_gates import CodeSandbox, QualityGate, MultiModelDebate, FigureGenerator, AntiPatternDetector, CodeAutoFixer


class TestCodeSandbox:
    def test_ast_audit_valid_code(self):
        sandbox = CodeSandbox()
        code = """
import numpy as np
from scipy.optimize import minimize

def objective(x):
    return x[0]**2 + x[1]**2

result = minimize(objective, [1.0, 1.0])
print(result.fun)
"""
        audit = sandbox.ast_audit(code)
        assert audit["passed"] is True
        assert len(audit["issues"]) == 0

    def test_ast_audit_hardcoded_metric(self):
        sandbox = CodeSandbox()
        code = "accuracy = 0.95"
        audit = sandbox.ast_audit(code)
        assert audit["passed"] is False
        assert any(i["type"] == "HARDCODED_METRIC" for i in audit["issues"])

    def test_ast_audit_syntax_error(self):
        sandbox = CodeSandbox()
        code = "def foo(:"  # 语法错误
        audit = sandbox.ast_audit(code)
        assert audit["passed"] is False
        assert any(i["type"] == "SYNTAX_ERROR" for i in audit["issues"])

    def test_ast_audit_input_call(self):
        sandbox = CodeSandbox()
        code = "x = input('Enter: ')"
        audit = sandbox.ast_audit(code)
        assert audit["passed"] is False
        assert any(i["type"] == "INPUT_CALL" for i in audit["issues"])

    def test_detect_missing_packages(self):
        sandbox = CodeSandbox()
        code = "import numpy as np\nimport nonexistent_fake_package_xyz"
        missing = sandbox.detect_missing_packages(code)
        assert "nonexistent_fake_package_xyz" in missing
        assert "numpy" not in missing  # numpy is installed

    def test_execute_valid_code(self):
        sandbox = CodeSandbox(timeout=10)
        code = "print(2 + 2)"
        result = sandbox.execute(code)
        assert result["success"] is True
        assert "4" in result["stdout"]

    def test_execute_syntax_error(self):
        sandbox = CodeSandbox(timeout=10)
        code = "def foo(:"
        result = sandbox.execute(code)
        assert result["success"] is False
        assert result["audit"]["passed"] is False

    def test_execute_timeout(self):
        sandbox = CodeSandbox(timeout=1)
        code = "import time; time.sleep(5)"
        result = sandbox.execute(code)
        assert result["success"] is False
        assert "超时" in result["stderr"] or "Timeout" in result["stderr"] or "timed out" in result["stderr"].lower()


class TestQualityGate:
    def test_research_gate_pass(self):
        gate = QualityGate.validate("research", {
            "references": [{"arxiv_id": "2401.00001"}, {"arxiv_id": "2401.00002"}, {"arxiv_id": "2401.00003"}],
            "content": "This is a research content with enough length " * 10
        })
        assert gate["passed"] is True
        assert gate["severity"] == "PASS"

    def test_research_gate_fail(self):
        gate = QualityGate.validate("research", {
            "references": [],
            "content": "Short"
        })
        assert gate["passed"] is False
        assert gate["severity"] == "FAIL"

    def test_code_gate_pass(self):
        gate = QualityGate.validate("code", {
            "code": """import numpy as np
import scipy.optimize

def objective(x):
    return x[0]**2 + x[1]**2

x0 = [1.0, 1.0]
result = scipy.optimize.minimize(objective, x0)
print(f"Optimal value: {result.fun}")
print(f"Optimal point: {result.x}")
""",
            "execution": {"success": True}
        })
        assert gate["passed"] is True

    def test_code_gate_fail_syntax(self):
        gate = QualityGate.validate("code", {
            "code": "def foo(:",
            "execution": {"success": False}
        })
        assert gate["passed"] is False

    def test_writing_gate_pass(self):
        gate = QualityGate.validate("writing", {
            "sections": [{"heading": "1"}, {"heading": "2"}, {"heading": "3"}],
            "abstract": "This is a long abstract " * 10,
            "references": [{"id": "1"}, {"id": "2"}, {"id": "3"}, {"id": "4"}, {"id": "5"}, {"id": "6"}]
        })
        assert gate["passed"] is True

    def test_review_gate_pass(self):
        gate = QualityGate.validate("review", {
            "overall_score": 4.0,
            "major_issues": ["Issue 1"]
        })
        assert gate["passed"] is True

    def test_review_gate_fail_low_score(self):
        gate = QualityGate.validate("review", {
            "overall_score": 1.5,
            "major_issues": ["Issue 1"]
        })
        assert gate["passed"] is False


class TestFigureGenerator:
    def test_generate_from_stdout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout = "accuracy: 0.95\nloss: 0.05\nf1: 0.88"
            figures = FigureGenerator._generate_from_stdout(stdout, Path(tmpdir))
            assert len(figures) > 0
            assert Path(figures[0]).exists()

    def test_generate_from_empty_stdout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            figures = FigureGenerator._generate_from_stdout("", Path(tmpdir))
            assert len(figures) == 0


class TestMultiModelDebate:
    def test_persona_debate(self):
        import asyncio
        
        async def mock_call(system, user, max_tokens):
            return {"content": "Mock feedback from model"}
        
        async def run_debate():
            debate = MultiModelDebate(mock_call, rounds=1)
            result = await debate.persona_debate("Test topic", "Test context")
            return result
        
        result = asyncio.run(run_debate())
        
        assert "synthesis" in result
        assert "personas" in result
        assert result["rounds"] == 1
        assert len(result["personas"]) == 3  # 3 personas


class TestAntiPatternDetector:
    def test_writing_hardcoded_metric(self):
        text = "The model achieves accuracy = 0.95 on the test set."
        result = AntiPatternDetector.detect_all(text, is_code=False)
        assert result["passed"] is True  # MEDIUM severity doesn't block
        assert result["medium_count"] > 0

    def test_writing_absolute_claim(self):
        text = "我们的方法在所有数据集上都达到了100%的准确率。"
        result = AntiPatternDetector.detect_all(text, is_code=False)
        assert result["medium_count"] > 0

    def test_code_hardcoded_metric(self):
        code = "accuracy = 0.95"
        result = AntiPatternDetector.detect_all(code, is_code=True)
        assert result["passed"] is False  # HIGH severity blocks
        assert result["high_count"] > 0

    def test_code_assert_metric(self):
        code = "assert accuracy > 0.9"
        result = AntiPatternDetector.detect_all(code, is_code=True)
        assert result["passed"] is False

    def test_clean_writing(self):
        text = "Our method achieves 95% accuracy on the test set."
        result = AntiPatternDetector.detect_all(text, is_code=False)
        assert result["passed"] is True
        assert result["medium_count"] == 0

    def test_clean_code(self):
        code = "result = model.predict(X_test)\naccuracy = np.mean(result == y_test)"
        result = AntiPatternDetector.detect_all(code, is_code=True)
        assert result["passed"] is True


class TestCodeAutoFixer:
    def test_execute_with_fix_success(self):
        import asyncio
        
        async def mock_call(system, user, max_tokens):
            return {"content": "```python\nprint(2 + 2)\n```"}
        
        async def run_fixer():
            sandbox = CodeSandbox(timeout=10)
            fixer = CodeAutoFixer(mock_call, sandbox, max_retries=2)
            result = await fixer.execute_with_fix("print(2 + 2)", "test problem")
            return result
        
        result = asyncio.run(run_fixer())
        
        assert result["success"] is True
        assert result["attempts"] == 1
        assert "4" in result["execution"]["stdout"]

    def test_execute_with_fix_retry(self):
        import asyncio
        
        call_count = 0
        
        async def mock_call(system, user, max_tokens):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 第一次返回错误代码
                return {"content": "```python\nprint(1/0)\n```"}
            else:
                # 第二次返回修复后的代码
                return {"content": "```python\nprint(42)\n```"}
        
        async def run_fixer():
            sandbox = CodeSandbox(timeout=10)
            fixer = CodeAutoFixer(mock_call, sandbox, max_retries=2)
            # 先执行一个会失败的代码
            result = await fixer.execute_with_fix("print(1/0)", "test problem")
            return result
        
        result = asyncio.run(run_fixer())
        
        # 应该会重试并最终成功
        assert result["attempts"] >= 2
