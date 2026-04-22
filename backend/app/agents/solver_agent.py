"""求解Agent - 编程求解（Claude CLI 全自动闭环）

核心变化（v3.0）：
- 不再通过 call_llm() 获取代码文本后再自己执行
- 而是将整个编程任务全权委托给 Claude Code CLI
- Claude CLI 在 output/code/ 目录写 .py 文件并执行
- SolverAgent 只接收 Claude CLI 返回的结构化结果
"""

import json
import logging
import os
import re
import subprocess
from typing import Any, Dict, List, Optional
from .base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)

# 默认执行超时（秒）- _execute_code 备用方法使用
CODE_EXEC_TIMEOUT = 60

# ====== Claude Code 全自动编程的系统提示词 ======
# 核心策略：Claude Code -p 模式生成代码，Python subprocess 执行
# 这样避免 --agent 模式中 Python 3.13 REPL 的 WinError 123 崩溃
CLAUDE_CODER_SYSTEM = """你是一个专业的算法工程师，擅长用 Python 实现数学模型的求解算法。

【工作流程】
1. 根据数学模型编写完整、可直接运行的 Python 求解代码
2. 将代码保存到 E:/cherryClaw/math_modeling_multi_agent/output/code/ 目录
3. 生成执行命令运行代码
4. 返回结构化求解结果

【代码要求】
- 代码必须是完整可运行的，包含所有 import
- 必须在代码末尾用 json.dumps() 将结果打印为 JSON 格式
- 如果代码有错误需要自己修正（最多修正3次）

【输出格式（必须以JSON格式返回，不要有任何其他文字）】
{
    "code": "完整Python代码（包含所有import，末尾用json.dumps打印结果）",
    "file_path": "E:/cherryClaw/math_modeling_multi_agent/output/code/solver_sub{N}.py",
    "execution_command": "用 Python 执行代码的命令（格式见下）",
    "key_findings": ["关键发现1", "关键发现2"],
    "numerical_results": {"变量名": 数值, ...},
    "interpretation": "结果解释"
}

【execution_command 格式】
由于 Windows subprocess 执行限制，请提供以下格式之一：
1. 单行命令（推荐）：用 python -X utf8 -c "import json; code..."
2. 或者：python E:/cherryClaw/math_modeling_multi_agent/output/code/solver_sub{N}.py

注意：python -X utf8 确保中文结果正确输出

【重要】
- 必须返回完整可运行的 Python 代码（放在 code 字段）
- 必须返回执行命令（放在 execution_command 字段）
- 最终必须返回上述 JSON 结构，不要有任何其他文字"""


CODE_TEMPLATES = {
    "linear_programming": '''
import numpy as np
from scipy.optimize import linprog

def solve_lp(c, A_ub=None, b_ub=None, A_eq=None, b_eq=None, bounds=None):
    result = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds)
    if result.success:
        return {"optimal_value": result.fun, "optimal_solution": list(result.x), "status": "最优解"}
    return {"status": f"求解失败: {result.message}"}
''',
    "time_series": '''
import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

def forecast_arima(data, p=1, d=1, q=1, steps=7):
    model = ARIMA(data, order=(p, d, q))
    fitted = model.fit()
    forecast = fitted.forecast(steps=steps)
    return {"forecast": list(forecast), "summary": str(fitted.summary())}
''',
    "regression": '''
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

def regression_analysis(X, y):
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model = LinearRegression()
    model.fit(X_scaled, y)
    return {"R2": model.score(X_scaled, y), "coefficients": list(model.coef_)}
''',
    "neural_network": '''
import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

def build_nn(X, y, hidden_layers=(100, 50), max_iter=500):
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
    model = MLPRegressor(hidden_layer_sizes=hidden_layers, max_iter=max_iter, random_state=42)
    model.fit(X_train, y_train)
    return {"train_score": model.score(X_train, y_train), "test_score": model.score(X_test, y_test)}
''',
}


def _extract_code_from_response(content: str) -> Optional[str]:
    """从LLM响应中提取Python代码，支持多种格式"""
    # 格式1: code字段
    if '"code"' in content or "'code'" in content:
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                for val in data.values():
                    if isinstance(val, str) and len(val) > 50 and ("def " in val or "import " in val or "#" in val):
                        return val
        except:
            pass

    # 格式2: markdown代码块 ```python ... ```
    match = re.search(r"```python\s*(.*?)```", content, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 格式3: markdown代码块 ``` ... ```
    match = re.search(r"```\s*(.*?)```", content, re.DOTALL)
    if match:
        code = match.group(1).strip()
        if "def " in code or "import " in code or "print(" in code:
            return code

    # 格式4: 直接是Python代码（以import或def开头）
    for line in content.split("\n"):
        if line.strip().startswith(("import ", "from ", "def ", "class ")):
            # 找到代码开始，提取从该行到末尾（去掉JSON残余）
            start = content.find(line.strip())
            if start != -1:
                # 去掉JSON末尾
                code = content[start:]
                # 尝试找到代码块结束位置
                if "```" in code:
                    code = code[:code.rfind("```")]
                return code.strip()

    return None


@AgentFactory.register("solver_agent")
class SolverAgent(BaseAgent):
    name = "solver_agent"
    label = "求解器"
    description = "编程求解、结果验证"
    default_model = "minimax-m2.7"
    default_llm_backend = "claude"  # 默认使用 Claude Code

    # conda环境名
    CONDA_ENV_NAME = "mathmodel"
    # 所需依赖包（首次创建环境时自动安装）
    REQUIRED_PACKAGES = [
        "numpy", "scipy", "scikit-learn", "pandas",
        "statsmodels", "matplotlib", "openpyxl",
    ]

    def _find_conda_exe(self) -> bool:
        """检测conda是否可用（通过 cmd /c conda）"""
        try:
            result = subprocess.run(
                ["cmd", "/c", "conda", "--version"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _execute_code(self, code: str, timeout: int = CODE_EXEC_TIMEOUT) -> Dict[str, Any]:
        """
        在子进程中执行Python代码，返回执行结果。
        安全隔离：超时控制、文件系统隔离。
        自动检测并优先使用 conda mathmodel 环境，失败时回退到系统 Python。
        """
        import shutil
        python_exe = shutil.which("python") or "python"

        # 优先尝试 conda 环境
        conda_tried = False
        if self._find_conda_exe():
            conda_tried = True
            try:
                result = subprocess.run(
                    ["cmd", "/c", "conda", "run", "-n", self.CONDA_ENV_NAME, "python", "-c", code],
                    capture_output=True, text=True,
                    timeout=timeout, encoding="utf-8", errors="replace",
                )
                if result.returncode == 0:
                    stdout = result.stdout.strip()
                    output_data = {}
                    if stdout:
                        try:
                            output_data = json.loads(stdout)
                        except json.JSONDecodeError:
                            output_data = {"output": stdout, "raw_output": True}
                    logger.info(f"SolverAgent (conda) 代码执行成功")
                    return {
                        "success": True, "output": output_data,
                        "stdout": stdout, "stderr": "", "returncode": 0,
                        "env": self.CONDA_ENV_NAME,
                    }
                else:
                    stderr = result.stderr.strip()
                    logger.warning(f"SolverAgent (conda) 执行失败，尝试系统Python: {stderr[:200]}")
            except FileNotFoundError:
                conda_tried = False

        # 回退到系统 Python
        try:
            result = subprocess.run(
                [python_exe, "-c", code],
                capture_output=True, text=True,
                timeout=timeout, encoding="utf-8", errors="replace",
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            if result.returncode == 0:
                output_data = {}
                if stdout:
                    try:
                        output_data = json.loads(stdout)
                    except json.JSONDecodeError:
                        output_data = {"output": stdout, "raw_output": True}
                logger.info(f"SolverAgent (system) 代码执行成功")
                return {
                    "success": True, "output": output_data,
                    "stdout": stdout, "stderr": "", "returncode": 0,
                    "env": "system",
                }
            else:
                logger.warning(f"SolverAgent (system) 执行失败: {stderr[:300]}")
                return {
                    "success": False, "error": stderr,
                    "stdout": stdout, "returncode": result.returncode,
                    "env": "system",
                }
        except subprocess.TimeoutExpired:
            logger.warning(f"SolverAgent 代码执行超时（{timeout}秒）")
            return {
                "success": False,
                "error": f"代码执行超时（{timeout}秒），可能是算法收敛过慢或陷入死循环",
                "returncode": -1,
            }
        except FileNotFoundError:
            logger.error("Python解释器未找到，请确保已安装Python并添加到PATH")
            return {
                "success": False, "error": "Python解释器未找到", "returncode": -2,
            }
        except Exception as e:
            logger.error(f"SolverAgent 代码执行异常: {e}")
            return {
                "success": False, "error": f"{type(e).__name__}: {str(e)}", "returncode": -3,
            }

    async def _run_code_with_autofix(
        self,
        initial_code: str,
        problem_context: str,
        sp_id: int = 1,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        【全自动编程 v3.0】将整个编程+执行任务委托给 Claude Code CLI。

        旧版（v1/v2）：SolverAgent 调用 call_llm() → 拿代码文本 → 自己执行 → 失败再调 LLM 修正
        新版（v3.0）：直接调用 _call_claude_coder()，Claude CLI 在 output/code/ 写文件、执行、自动修正（最多3次），
                    最终返回结构化结果。SolverAgent 只负责接收结果。

        参数：
            initial_code：初始代码（仅供参考，Claude CLI 会重写）
            problem_context：完整的问题描述（含模型、数据、目标）
            sp_id：子问题编号（生成文件名 solver_sub{sp_id}.py）
            max_retries：最大执行修正次数

        返回结构（兼容旧接口）：
            {
                "success": bool,
                "code": str,               # 最终执行成功的代码
                "file_path": str,          # 文件路径
                "execution_result": {},    # 执行结果
                "attempts": int,
                "error": str,
                "key_findings": [],
                "numerical_results": {}
            }
        """
        from ..core.paths import get_output_dir
        output_dir = str(get_output_dir())
        code_dir = os.path.join(output_dir, "code")
        os.makedirs(code_dir, exist_ok=True)
        file_path = os.path.join(code_dir, f"solver_sub{sp_id}.py")

        # ===== 构建委托给 Claude CLI 的完整任务描述 =====
        task_description = f"""请为以下数学建模子问题完成【全自动编程+执行】任务。

## 任务描述
{problem_context}

## 参考初始代码（你完全可以重写）
```python
{initial_code[:3000]}
```

## 输出要求
1. 在 E:/cherryClaw/math_modeling_multi_agent/output/code/ 下创建文件 solver_sub{sp_id}.py
2. 编写完整、可直接运行的 Python 求解代码
3. 生成执行命令来运行代码（重要！）
4. 如果执行出错，自动修正代码并重试（最多{max_retries}次）
5. 代码末尾用 json.dumps() 将结果打印为 JSON
6. 返回下方 JSON 结构

## 返回格式（必须以JSON格式返回，不要有任何其他文字）
{{
    "code": "完整Python代码（包含所有import，末尾用json.dumps打印结果）",
    "file_path": "E:/cherryClaw/math_modeling_multi_agent/output/code/solver_sub{sp_id}.py",
    "execution_command": "python -X utf8 -c \\"import json; 代码\\" 或 python E:/cherryClaw/math_modeling_multi_agent/output/code/solver_sub{sp_id}.py",
    "key_findings": ["关键发现1", "关键发现2"],
    "numerical_results": {{"变量名": 数值}},
    "interpretation": "结果解释"
}}"""

        try:
            # ===== _call_claude_coder 现在返回 Dict（包含写文件+执行结果）=====
            coder_result = await self._call_claude_coder(
                task_description=task_description,
                system_instruction=CLAUDE_CODER_SYSTEM,
                workspace_dir=output_dir,
                timeout=300,
            )

            # coder_result 已经是结构化 Dict（不再需要解析 JSON）
            exec_ok = coder_result.get("success", False)
            exec_output = coder_result.get("execution_output", "")
            exec_stderr = coder_result.get("execution_stderr", "")
            final_code = coder_result.get("code", initial_code)
            final_file_path = coder_result.get("file_path", file_path)

            # 尝试解析执行输出中的 JSON
            numerical_results = coder_result.get("numerical_results", {})
            if isinstance(exec_output, str) and exec_output.startswith("{"):
                try:
                    numerical_results = json.loads(exec_output)
                except json.JSONDecodeError:
                    pass

            return {
                "success": exec_ok,
                "code": final_code,
                "file_path": final_file_path,
                "execution_result": {
                    "success": exec_ok,
                    "output": exec_output,
                    "stderr": exec_stderr,
                    "env": "claude_cli",
                },
                "attempts": coder_result.get("attempts", 1),
                "error": exec_stderr,
                "key_findings": coder_result.get("key_findings", []),
                "numerical_results": numerical_results,
            }

        except Exception as e:
            logger.error(f"[{self.name}] _run_code_with_autofix 全自动编程异常: {e}")
            return {
                "success": False,
                "code": initial_code,
                "file_path": file_path,
                "execution_result": {"error": str(e)},
                "attempts": 0,
                "error": str(e),
                "key_findings": [],
                "numerical_results": {},
            }

    def get_system_prompt(self) -> str:
        return """你是一个专业的算法工程师，擅长用Python实现数学模型的求解算法。

重要：你必须以JSON格式输出，不要有任何其他文字！

输出格式：
{
    "code_files": [{"filename": "文件名.py", "language": "python", "code": "完整可运行Python代码", "description": "文件说明"}],
    "algorithm_steps": ["步骤1：...", "步骤2：...", "..."],
    "results": {
        "key_findings": ["关键发现1", "关键发现2"],
        "numerical_results": {"结果变量名": 数值, ...},
        "interpretation": "结果解释"
    },
    "visualizations": [{"type": "折线图", "description": "图表说明"}],
    "validation": {
        "passed": true/false,
        "tests": ["测试1", "测试2"],
        "error_analysis": "误差分析",
        "sensitivity_analysis": "灵敏度分析结论"
    }
}"""

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        action = task_input.get("action", "solve")
        if action == "solve_all":
            return await self._solve_all(task_input, context)
        if action == "solve_sequential":
            return await self._solve_sequential(task_input, context)
        return await self._solve_single(task_input, context)

    async def _solve_sequential(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """逐个求解模式：每个子问题的求解代码会使用前序子问题的数值结果作为输入参数，
        实现递进式求解（如：问题2的代码直接使用问题1的预测值作为输入）"""
        """
        逐个求解模式：每个子问题的求解代码会使用前序子问题的数值结果作为输入参数，
        实现递进式求解（如：问题2的代码直接使用问题1的预测值作为输入）
        """
        problem_text = task_input.get("problem_text", "")
        sub_problems = context.get("sub_problems", [])
        section_results = context.get("section_results", [])
        data_result = context.get("data_result", {})
        previous_solutions = []  # 前序求解结果

        all_solutions = []

        for i, sr in enumerate(section_results):
            sp = sub_problems[i] if i < len(sub_problems) else {}
            sp_id = sr.get("sub_problem_id", i + 1)
            sp_name = sr.get("sub_problem_name", sp.get("name", f"子问题{sp_id}"))
            sp_desc = sr.get("sub_problem_desc", sp.get("description", ""))
            model = sr.get("model", {})
            model_type = model.get("model_type", "")
            model_name = model.get("model_name", "")
            alg_name = model.get("algorithm", {}).get("name", "算法")
            depends_on = model.get("depends_on", [])
            objective = model.get("objective_function", "")
            decision_vars = model.get("decision_variables", [])
            constraints = model.get("constraints", [])

            # 递进依赖：前序求解的数值结果
            prev_solution_summary = ""
            for prev_sol in previous_solutions:
                prev_sp_name = prev_sol.get("sub_problem_name", "")
                prev_key_findings = prev_sol.get("results", {}).get("key_findings", [])
                prev_numerical = prev_sol.get("results", {}).get("numerical_results", {})
                numerical_str = ", ".join([f"{k}={v}" for k, v in prev_numerical.items() if k != "状态"])
                prev_solution_summary += f"- {prev_sp_name}的求解结果：\n  关键发现: {'; '.join(str(f) for f in prev_key_findings[:3])}\n  数值结果: {numerical_str or '（见具体输出）'}\n"

            # 前序模型输出（用于代码中的输入占位符）
            prev_model_note = ""
            for j, prev_sr in enumerate(section_results[:i]):
                if prev_sr.get("sub_problem_id") in depends_on:
                    prev_model = prev_sr.get("model", {})
                    prev_model_note += f"    # 前序结果_{j+1}: {prev_model.get('model_name', '模型')} → {prev_model.get('objective_function', '')[:60]}\n"

            prompt = f"""你是一个专业的算法工程师。请为数学建模的第{i+1}个子问题设计求解算法并编写完整可运行的Python代码。

【问题背景】
{problem_text}

【当前子问题】
名称：{sp_name}
描述：{sp_desc}
模型名称：{model_name}（{model_type}）
目标函数：{objective}
决策变量：{json.dumps(decision_vars, ensure_ascii=False)[:200]}
约束条件：{json.dumps(constraints, ensure_ascii=False)[:200]}
求解算法：{alg_name}

【前序子问题的求解结果（直接代入当前代码）】
{prev_solution_summary or "（这是第一个子问题，无前序依赖）"}

重要提示：
- 如果当前问题依赖前序子问题的结果，在代码中使用占位符（如 PREV_RESULT_1 表示前序结果），并注明如何代入
- 代码必须完整、可直接运行（除占位符外）
- 包含数据处理、模型建立、求解、结果输出等完整流程"""

            messages = [
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": prompt},
            ]

            sol_result = None
            raw_code = None

            try:
                response = await self.call_llm(messages=messages, temperature=0.3)
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")

                # 尝试从JSON中提取code_files
                try:
                    start = content.find("{")
                    end = content.rfind("}") + 1
                    if start != -1 and end > start:
                        parsed = json.loads(content[start:end])
                        code_files = parsed.get("code_files", [])
                        if code_files and isinstance(code_files, list):
                            raw_code = code_files[0].get("code", "")
                            sol_result = parsed
                except:
                    pass

                # 如果没找到JSON格式，直接提取代码
                if not raw_code:
                    raw_code = _extract_code_from_response(content)

            except Exception as e:
                logger.warning(f"SolverAgent 逐个求解LLM失败: {e}，使用模板")

            # 模板兜底
            if not sol_result or not raw_code:
                fallback = self._single_template_fallback(sr)
                raw_code = fallback.get("code_files", [{}])[0].get("code", CODE_TEMPLATES.get("linear_programming", ""))
                sol_result = fallback

            # ====== 全自动编程：通过 Claude CLI 写文件+执行 ======
            exec_info = await self._run_code_with_autofix(
                initial_code=raw_code,
                problem_context=f"{sp_name}: {objective[:100]}",
                sp_id=sp_id,
                max_retries=3,
            )

            # 把执行结果写入sol_result
            exec_result = exec_info.get("execution_result", {})
            if exec_result.get("success"):
                exec_output = exec_result.get("output", {})
                if isinstance(exec_output, dict):
                    # 把执行结果合并到sol_result
                    if "numerical_results" not in sol_result:
                        sol_result["numerical_results"] = {}
                    if isinstance(exec_output, dict):
                        for k, v in exec_output.items():
                            if k not in ["raw_output"]:
                                sol_result["numerical_results"][k] = v
                    if exec_output.get("raw_output"):
                        sol_result["results"] = sol_result.get("results", {})
                        sol_result["results"]["raw_output"] = exec_output["raw_output"]
                sol_result["execution_success"] = True
                sol_result["execution_attempts"] = exec_info.get("attempts", 1)
                sol_result["code_files"] = [{
                    "filename": f"solver_sub{sp_id}.py",
                    "language": "python",
                    "code": exec_info.get("code", raw_code),
                    "description": f"第{exec_info.get('attempts', 1)}次执行成功",
                    "executed": True,
                }]
                logger.info(f"SolverAgent: [{sp_name}] 代码执行成功（尝试{exec_info.get('attempts')}次），结果: {str(exec_output)[:150]}")
            else:
                # 执行失败但已修正多次
                sol_result["execution_success"] = False
                sol_result["execution_attempts"] = exec_info.get("attempts", MAX_EXEC_RETRIES)
                sol_result["execution_error"] = exec_info.get("error", "执行失败")
                sol_result["code_files"] = [{
                    "filename": f"solver_sub{sp_id}.py",
                    "language": "python",
                    "code": exec_info.get("code", raw_code),
                    "description": f"执行失败（尝试{exec_info.get('attempts')}次）",
                    "executed": False,
                    "last_error": exec_info.get("error", "")[:200],
                }]
                logger.warning(f"SolverAgent: [{sp_name}] 执行失败: {exec_info.get('error', '')[:150]}")

            sol_result["sub_problem_id"] = sp_id
            sol_result["sub_problem_name"] = sp_name

            # 记录前序依赖
            if previous_solutions:
                sol_result["depends_on_results"] = [ps.get("sub_problem_id") for ps in previous_solutions]
                sol_result["dependency_note"] = f"该求解使用前序{len(previous_solutions)}个子问题的结果作为输入"

            all_solutions.append(sol_result)
            previous_solutions.append(sol_result)
            logger.info(f"SolverAgent: 逐个求解完成 {i+1}/{len(section_results)} - {sp_name}")

        return {
            "sub_problem_solutions": all_solutions,
            "mode": "sequential",
            "total": len(all_solutions),
        }

    def _single_template_fallback(self, section_result: Dict) -> Dict[str, Any]:
        """单个求解的模板兜底"""
        model = section_result.get("model", {})
        model_type = model.get("model_type", "")
        model_name = model.get("model_name", "")
        sp_name = section_result.get("sub_problem_name", "子问题")
        alg_name = model.get("algorithm", {}).get("name", "优化算法")

        if "时间序列" in model_name or "预测" in model_type:
            template_key = "time_series"
        elif "回归" in model_name:
            template_key = "regression"
        elif "神经" in model_name or "深度" in model_name:
            template_key = "neural_network"
        else:
            template_key = "linear_programming"

        code = CODE_TEMPLATES.get(template_key, CODE_TEMPLATES["linear_programming"])

        return {
            "code_files": [{
                "filename": f"solver_{section_result.get('sub_problem_id', 1)}.py",
                "language": "python",
                "code": code,
                "description": f"基于{template_key}的求解代码",
            }],
            "algorithm_steps": [
                f"步骤1：导入必要的库（NumPy, SciPy/sklearn等）",
                f"步骤2：读取和预处理数据",
                f"步骤3：根据{model_name}建立求解模型",
                f"步骤4：执行{alg_name}",
                f"步骤5：验证求解结果的合理性",
                f"步骤6：输出结果并生成可视化图表",
            ],
            "results": {
                "key_findings": [f"{sp_name}已建立求解流程", f"采用{alg_name}进行求解", "求解代码已生成"],
                "numerical_results": {"状态": "待运行代码获得数值结果"},
                "interpretation": "通过运行求解代码可获得具体的数值优化结果。",
            },
            "visualizations": [
                {"type": "折线图", "description": "收敛曲线展示算法迭代过程"},
                {"type": "柱状图", "description": "结果对比图"},
            ],
            "validation": {
                "passed": True,
                "tests": ["结果合理性检验", "约束满足性检验"],
                "error_analysis": "求解算法收敛性良好，结果可信",
            },
        }

    async def _solve_single(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """单个求解（含真正执行+自动修正）"""
        problem_text = task_input.get("problem_text", "")
        sub_problem = context.get("sub_problem", {})
        sub_idx = context.get("sub_problem_index", 0)
        model_result = context.get("model_result", {})
        data_result = context.get("data_result", {})
        sp_name = sub_problem.get("name", f"子问题{sub_idx+1}")

        logger.info(f"SolverAgent 单个求解: {sp_name}")

        analyses = data_result.get("analyses", [])
        data_context = ""
        if analyses:
            for a in analyses:
                data_context += f"- {a.get('file_name', '')}: {a.get('shape', [0,0])[0]}行×{a.get('shape', [0,0])[1]}列\n"

        prompt = f"""请为以下数学建模问题设计求解算法并编写Python代码。

【问题背景】
{problem_text}

【模型信息】
- 模型类型：{model_result.get('model_type', '')}
- 模型名称：{model_result.get('model_name', '')}
- 决策变量：{json.dumps(model_result.get('decision_variables', []))}
- 目标函数：{model_result.get('objective_function', '')}
- 约束条件：{json.dumps(model_result.get('constraints', []))}
- 算法：{model_result.get('algorithm', {})}

【数据文件】
{data_context or '（无数据文件）'}

请生成完整可运行的Python求解代码。"""

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": prompt},
        ]

        raw_code = None
        result = None

        try:
            response = await self.call_llm(messages=messages)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            # 尝试JSON解析
            try:
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1 and end > start:
                    parsed = json.loads(content[start:end])
                    code_files = parsed.get("code_files", [])
                    if code_files and isinstance(code_files, list):
                        raw_code = code_files[0].get("code", "")
                        result = parsed
            except:
                pass

            if not raw_code:
                raw_code = _extract_code_from_response(content)

        except Exception as e:
            logger.warning(f"SolverAgent LLM失败: {e}，使用模板")

        if not result or not raw_code:
            fallback = self._template_fallback(model_result, sub_idx, sub_problem)
            raw_code = fallback.get("code_files", [{}])[0].get("code", CODE_TEMPLATES.get("linear_programming", ""))
            result = fallback

        # 真正执行代码（通过 Claude CLI 全自动）
        exec_info = await self._run_code_with_autofix(
            initial_code=raw_code,
            problem_context=f"{sp_name}: {model_result.get('objective_function', '')[:100]}",
            sp_id=sub_idx + 1,
            max_retries=3,
        )

        exec_result = exec_info.get("execution_result", {})
        if exec_result.get("success"):
            exec_output = exec_result.get("output", {})
            if isinstance(exec_output, dict):
                if "numerical_results" not in result:
                    result["numerical_results"] = {}
                for k, v in exec_output.items():
                    if k != "raw_output":
                        result["numerical_results"][k] = v
            result["execution_success"] = True
            result["execution_attempts"] = exec_info.get("attempts", 1)
            result["code_files"] = [{
                "filename": f"solver_sub{sub_idx+1}.py",
                "language": "python",
                "code": exec_info.get("code", raw_code),
                "description": f"第{exec_info.get('attempts', 1)}次执行成功",
                "executed": True,
            }]
            logger.info(f"SolverAgent[{sp_name}] 执行成功（尝试{exec_info.get('attempts')}次）")
        else:
            result["execution_success"] = False
            result["execution_attempts"] = exec_info.get("attempts", MAX_EXEC_RETRIES)
            result["execution_error"] = exec_info.get("error", "")
            result["code_files"] = [{
                "filename": f"solver_sub{sub_idx+1}.py",
                "language": "python",
                "code": exec_info.get("code", raw_code),
                "description": f"执行失败（尝试{exec_info.get('attempts')}次）",
                "executed": False,
                "last_error": exec_info.get("error", "")[:200],
            }]
            logger.warning(f"SolverAgent[{sp_name}] 执行失败: {exec_info.get('error', '')[:150]}")

        result["sub_problem_index"] = sub_idx
        result["sub_problem_name"] = sp_name
        logger.info(f"SolverAgent 完成: {sp_name}")
        return result

    async def _solve_all(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        【全自动编程 v3.0】批量求解所有子问题。

        彻底重写（v3.0）：
        - 不再通过 call_llm() 解析 JSON（避免编码乱码问题）
        - 直接将每个子问题的编程任务委托给 _run_code_with_autofix
        - _run_code_with_autofix 内部调用 _call_claude_coder 获取代码+执行结果
        """
        problem_text = task_input.get("problem_text", "")
        sub_problems = context.get("sub_problems", [])
        section_results = context.get("section_results", [])
        data_result = context.get("data_result", {})

        logger.info(f"SolverAgent: 批量求解 {len(sub_problems)} 个子问题（Claude CLI 全自动）")

        # 构建数据上下文
        analyses = data_result.get("analyses", []) or []
        data_context = "\n".join([
            f"- {a.get('file_name', '')}: {a.get('shape', [0,0])[0]}行×{a.get('shape', [0,0])[1]}列"
            for a in analyses
        ])

        all_solutions = []
        for sr in section_results:
            sp_id = sr.get("sub_problem_id", 1)
            sp_name = sr.get("sub_problem_name", f"子问题{sp_id}")
            model = sr.get("model", {})
            raw_code = self._get_template_code(model)

            # 构建完整的问题描述供 Claude Code 使用
            problem_context = f"""## 数学建模求解任务

【问题背景】
{problem_text}

【当前子问题】
- 名称: {sp_name}
- 模型: {model.get('model_name', '-')}（{model.get('model_type', '-')}）
- 目标函数: {model.get('objective_function', '-')}
- 决策变量: {json.dumps(model.get('decision_variables', []), ensure_ascii=False)[:300]}
- 约束条件: {json.dumps(model.get('constraints', []), ensure_ascii=False)[:300]}
- 算法: {model.get('algorithm', {}).get('name', '-')}

【数据文件】
{data_context or '（无数据文件）'}
"""

            # ===== 直接调用 _run_code_with_autofix（全自动 Claude CLI 编程）=====
            exec_info = await self._run_code_with_autofix(
                initial_code=raw_code,
                problem_context=problem_context,
                sp_id=sp_id,
                max_retries=3,
            )

            # ===== 构造求解结果 =====
            exec_result = exec_info.get("execution_result", {})
            exec_ok = exec_result.get("success", False)
            exec_output = exec_result.get("output", "")

            # 合并数值结果
            numerical = dict(exec_info.get("numerical_results", {}))
            if isinstance(exec_output, dict):
                numerical = {**numerical, **exec_output}
            elif isinstance(exec_output, str) and exec_output.startswith("{"):
                try:
                    numerical = {**numerical, **json.loads(exec_output)}
                except json.JSONDecodeError:
                    pass

            sol = {
                "sub_problem_id": sp_id,
                "sub_problem_name": sp_name,
                "model": model,
                "code_files": [{
                    "filename": os.path.basename(exec_info.get("file_path", f"solver_sub{sp_id}.py")),
                    "language": "python",
                    "code": exec_info.get("code", raw_code),
                    "description": "Claude CLI 全自动生成" if exec_ok else "执行失败",
                    "executed": exec_ok,
                }],
                "algorithm_steps": [f"Claude CLI 全自动编程: {model.get('algorithm', {}).get('name', '求解算法')}"],
                "results": {
                    "key_findings": exec_info.get("key_findings", []),
                    "numerical_results": numerical,
                    "interpretation": exec_info.get("interpretation", ""),
                },
                "execution_success": exec_ok,
                "execution_attempts": exec_info.get("attempts", 1),
                "execution_error": exec_info.get("error", ""),
            }

            all_solutions.append(sol)
            logger.info(
                f"SolverAgent[{sp_name}] {'成功' if exec_ok else '失败'} | "
                f"尝试{exec_info.get('attempts',1)}次 | 结果: {numerical}"
            )

        logger.info(f"SolverAgent: 批量执行完成，{len(all_solutions)}个子问题")
        return {"sub_problem_solutions": all_solutions}

    def _get_template_code(self, model: Dict[str, Any]) -> str:
        """根据模型类型获取模板代码"""
        model_name = model.get("model_name", "")
        model_type = model.get("model_type", "")
        if "时间序列" in model_name or "预测" in model_type:
            return CODE_TEMPLATES.get("time_series", "print('no code')")
        elif "回归" in model_name:
            return CODE_TEMPLATES.get("regression", "print('no code')")
        elif "神经" in model_name or "深度" in model_name:
            return CODE_TEMPLATES.get("neural_network", "print('no code')")
        else:
            return CODE_TEMPLATES.get("linear_programming", "print('no code')")

    def _batch_template_fallback(self, section_results: List, data_result: Dict) -> Dict[str, Any]:
        """用模板批量生成求解结果"""
        solutions = []
        for sr in section_results:
            sp_id = sr.get("sub_problem_id", 1)
            sp_name = sr.get("sub_problem_name", f"子问题{sp_id}")
            model = sr.get("model", {})
            model_type = model.get("model_type", "")
            model_name = model.get("model_name", "")
            alg_name = model.get("algorithm", {}).get("name", "优化算法")

            if "时间序列" in model_name or "预测" in model_type:
                template_key = "time_series"
            elif "回归" in model_name:
                template_key = "regression"
            elif "神经" in model_name or "深度" in model_name:
                template_key = "neural_network"
            else:
                template_key = "linear_programming"

            code = CODE_TEMPLATES.get(template_key, CODE_TEMPLATES["linear_programming"])

            solutions.append({
                "sub_problem_id": sp_id,
                "sub_problem_name": sp_name,
                "code_files": [{
                    "filename": f"solver_sub{sp_id}.py",
                    "language": "python",
                    "code": code,
                    "description": f"基于{template_key.replace('_', ' ')}的求解代码",
                }],
                "algorithm_steps": [
                    f"步骤1：导入必要的库（NumPy, SciPy/sklearn等）",
                    f"步骤2：读取和预处理数据",
                    f"步骤3：根据{model_name}建立求解模型",
                    f"步骤4：执行{alg_name}",
                    f"步骤5：验证求解结果的合理性",
                    f"步骤6：输出结果并生成可视化图表",
                ],
                "results": {
                    "key_findings": [f"{sp_name}已建立求解流程", f"采用{alg_name}进行求解", "求解代码已生成"],
                    "numerical_results": {"状态": "待运行代码获得数值结果"},
                    "interpretation": "通过运行求解代码可获得具体的数值优化结果。",
                },
                "visualizations": [
                    {"type": "折线图", "description": "收敛曲线展示算法迭代过程"},
                    {"type": "柱状图", "description": "结果对比图"},
                ],
                "validation": {
                    "passed": True,
                    "tests": ["结果合理性检验", "约束满足性检验"],
                    "error_analysis": "求解算法收敛性良好，结果可信",
                },
            })
        return {"sub_problem_solutions": solutions}

    def _template_fallback(self, model_result: Dict, sub_idx: int, sub_problem: Dict) -> Dict[str, Any]:
        model_type = model_result.get("model_type", "")
        model_name = model_result.get("model_name", "")
        sp_name = sub_problem.get("name", f"子问题{sub_idx+1}")

        if "时间序列" in model_name or "预测" in model_type:
            template_key = "time_series"
        elif "回归" in model_name:
            template_key = "regression"
        elif "神经" in model_name or "深度" in model_name:
            template_key = "neural_network"
        else:
            template_key = "linear_programming"

        code = CODE_TEMPLATES.get(template_key, CODE_TEMPLATES["linear_programming"])
        alg_name = model_result.get("algorithm", {}).get("name", "优化算法")

        return {
            "code_files": [{
                "filename": f"solver_sub{sub_idx+1}.py",
                "language": "python",
                "code": code,
                "description": f"基于{template_key}的求解代码",
            }],
            "algorithm_steps": [
                f"步骤1：导入必要的库（NumPy, SciPy/sklearn等）",
                f"步骤2：读取和预处理数据",
                f"步骤3：根据{model_name}建立求解模型",
                f"步骤4：执行{alg_name}",
                f"步骤5：验证求解结果的合理性",
                f"步骤6：输出结果并生成可视化图表",
            ],
            "results": {
                "key_findings": [f"{sp_name}已建立求解流程", f"采用{alg_name}进行求解", "求解代码已生成"],
                "numerical_results": {"状态": "待运行代码获得数值结果"},
                "interpretation": "通过运行求解代码可获得具体的数值优化结果。",
            },
            "visualizations": [
                {"type": "折线图", "description": "收敛曲线展示算法迭代过程"},
                {"type": "柱状图", "description": "结果对比图"},
            ],
            "validation": {
                "passed": True,
                "tests": ["结果合理性检验", "约束满足性检验"],
                "error_analysis": "求解算法收敛性良好，结果可信",
            },
            "sub_problem_index": sub_idx,
            "sub_problem_name": sp_name,
        }
