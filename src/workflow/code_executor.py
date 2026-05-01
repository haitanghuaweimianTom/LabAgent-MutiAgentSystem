"""
CodeExecutor - Claude CLI 代码执行引擎
========================================

明确使用 Claude Code CLI 进行代码生成，
使用 subprocess 沙箱执行代码，
支持调试闭环（出错→修复→重试）。

借鉴 LLM-MM-Agent 的 coding_actor + coding_debugger 设计。
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable


class CodeExecutor:
    """
    代码执行器

    职责：
    1. 使用 Claude CLI 生成代码
    2. 在隔离的 subprocess 中执行代码
    3. 捕获 stdout/stderr，自动修复错误
    4. 提取代码结构供下游任务引用
    """

    def __init__(
        self,
        call_llm: Optional[Callable[[str, Optional[str]], str]] = None,
        output_dir: str = "work",
    ):
        self.call_llm = call_llm
        self.output_dir = Path(output_dir)
        self.exec_dir = self.output_dir / "execution"
        self.exec_dir.mkdir(parents=True, exist_ok=True)
        self._claude_path = self._find_claude_code()

    def _find_claude_code(self) -> Optional[str]:
        """查找 Claude Code CLI"""
        found = shutil.which("claude-code") or shutil.which("claude")
        return found

    def generate_code_with_claude_cli(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: str = "sonnet",
        timeout: int = 180,
    ) -> str:
        """
        使用 Claude Code CLI 生成代码

        这是代码生成的首选方式，因为：
        1. Claude CLI 针对代码任务优化
        2. 支持更长的上下文和更复杂的代码
        3. 用户明确要求代码任务交给 Claude CLI
        """
        if not self._claude_path:
            raise RuntimeError(
                "Claude Code CLI 未找到。请安装 Claude Code: npm install -g @anthropic-ai/claude-code"
            )

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        cmd = [
            self._claude_path,
            "-p",
            "--model", model,
            "--output-format", "json",
            full_prompt,
        ]

        print(f"    [CodeExecutor] 调用 Claude CLI 生成代码...")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate(timeout=timeout)

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Claude CLI 代码生成失败: {error_msg[:500]}")

        stdout_text = stdout.decode("utf-8", errors="replace").strip()

        try:
            data = json.loads(stdout_text)
            result = data.get("result", "")
            if isinstance(result, str):
                return result.strip()
            return str(result)
        except json.JSONDecodeError:
            return stdout_text.strip()

    def extract_code(self, raw_output: str, save_path: Path) -> str:
        """从 LLM 输出中提取纯净 Python 代码"""
        text = raw_output.strip()

        # 去除 markdown 代码块
        if text.startswith("```"):
            lines = text.split("\n")
            start = 0
            while start < len(lines) and not lines[start].strip().startswith("```"):
                start += 1
            start += 1
            end = len(lines) - 1
            while end > start and not lines[end].strip().startswith("```"):
                end -= 1
            text = "\n".join(lines[start:end]).strip()

        # 找到第一个 import
        lines = text.split("\n")
        first_import = 0
        for i, line in enumerate(lines):
            if line.strip().startswith(("import ", "from ")):
                first_import = i
                break

        code = "\n".join(lines[first_import:]).strip()

        if not code.startswith(("import ", "from ")):
            # 尝试更激进的提取
            import re
            py_match = re.search(r'(import [\w]+|from [\w.]+ import)', text)
            if py_match:
                code = text[py_match.start():].strip()
            else:
                raise ValueError("无法从输出中提取有效Python代码")

        # 后处理：确保代码使用 OUTPUT_DIR 环境变量写入结果
        code = self._ensure_output_dir_usage(code)

        # 保存
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(code, encoding="utf-8")
        return code

    def _ensure_output_dir_usage(self, code: str) -> str:
        """
        确保代码使用 OUTPUT_DIR 环境变量作为输出路径，
        防止硬编码相对路径导致结果写入错误位置。
        """
        import re

        # 如果代码已经使用了 OUTPUT_DIR，则不需要修改
        if "OUTPUT_DIR" in code:
            return code

        # 检测常见的硬编码输出目录模式
        patterns = [
            r'out_dir\s*=\s*["\']work[^"\']*["\']',
            r'out_dir\s*=\s*["\']execution["\']',
            r'output_dir\s*=\s*["\']work[^"\']*["\']',
            r'output_dir\s*=\s*["\']execution["\']',
            r'os\.makedirs\(["\']work[^"\']*["\']',
            r'os\.makedirs\(["\']execution["\']',
        ]

        modified = code
        for pattern in patterns:
            modified = re.sub(pattern, lambda m: m.group(0).replace(m.group(0).split("=")[-1].strip().strip('"').strip("'"), "os.environ.get('OUTPUT_DIR', '.') + '/execution'"), modified)

        # 更通用的替换：如果代码中直接写了 open("work_... 或 open("execution/...
        # 替换为使用 os.path.join(os.environ.get('OUTPUT_DIR', '.'), 'execution', ...)
        if "OUTPUT_DIR" not in modified:
            # 在代码开头插入 OUTPUT_DIR 的使用
            lines = modified.split("\n")
            import_idx = 0
            for i, line in enumerate(lines):
                if line.strip().startswith(("import ", "from ")):
                    import_idx = i + 1

            output_dir_line = "_OUTPUT_DIR = os.environ.get('OUTPUT_DIR', '.')"
            if output_dir_line not in modified:
                lines.insert(import_idx, output_dir_line)
                modified = "\n".join(lines)

        return modified

    def execute_code(
        self,
        code_file: Path,
        data_files: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """
        在隔离的 subprocess 中执行代码

        Args:
            code_file: 代码文件路径
            data_files: 数据文件路径映射
            env_vars: 额外环境变量
            timeout: 执行超时时间

        Returns:
            Dict: {"success": bool, "output": str, "error": str, "returncode": int}
        """
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(code_file.parent.resolve())

            if data_files:
                env["DATA_FILES"] = json.dumps(data_files, ensure_ascii=False)

            if env_vars:
                env.update(env_vars)

            work_dir = self.output_dir.resolve()

            # 将输出目录通过环境变量传递，便于代码使用绝对路径
            env["OUTPUT_DIR"] = str(self.output_dir.resolve())

            proc = subprocess.run(
                [sys.executable, str(code_file.resolve())],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(work_dir),
            )

            return {
                "success": proc.returncode == 0,
                "output": proc.stdout,
                "error": proc.stderr,
                "returncode": proc.returncode,
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"代码执行超时（{timeout}秒）", "output": "", "returncode": -1}
        except Exception as e:
            return {"success": False, "error": str(e), "output": "", "returncode": -1}

    def fix_code(
        self,
        code_file: Path,
        error_msg: str,
        stdout: str = "",
        max_retries: int = 3,
    ) -> bool:
        """
        调用 LLM 修复代码错误

        Args:
            code_file: 代码文件路径
            error_msg: 错误信息
            stdout: 标准输出
            max_retries: 最大修复尝试次数

        Returns:
            bool: 是否修复成功
        """
        if not self.call_llm:
            print("    [CodeExecutor] 无 LLM 回调，无法自动修复")
            return False

        original_code = code_file.read_text(encoding="utf-8")

        for attempt in range(max_retries):
            fix_prompt = f"""以下Python代码执行时出错，请修复后输出完整代码。

错误信息：
{error_msg[:2000]}

标准输出：
{stdout[:1000]}

原始代码：
{original_code}

要求：
1. 直接输出修复后的纯Python代码，不要有任何说明文字
2. 代码开头必须是import语句
3. 确保代码能正确处理数据文件路径
4. 保留原有的核心逻辑和算法"""

            try:
                fixed = self.call_llm(fix_prompt, "你是Python调试专家。")
                self.extract_code(fixed, code_file)
                print(f"    [CodeExecutor] 代码修复尝试 {attempt + 1}/{max_retries}")

                # 验证修复后的代码
                result = self.execute_code(code_file)
                if result["success"]:
                    print(f"    [CodeExecutor] 修复成功")
                    return True
                else:
                    error_msg = result["error"]
                    original_code = code_file.read_text(encoding="utf-8")

            except Exception as e:
                print(f"    [CodeExecutor] 修复失败: {e}")

        return False

    def run_with_auto_fix(
        self,
        code_file: Path,
        data_files: Optional[Dict[str, str]] = None,
        results_json_path: Optional[Path] = None,
        max_fix_attempts: int = 3,
    ) -> Dict[str, Any]:
        """
        执行代码，出错时自动修复

        Args:
            code_file: 代码文件路径
            data_files: 数据文件映射
            results_json_path: 期望的结果JSON路径
            max_fix_attempts: 最大修复次数

        Returns:
            Dict: 最终结果字典（优先读取 results_json）
        """
        execution_result = {}

        for attempt in range(max_fix_attempts + 1):
            print(f"    [CodeExecutor] 执行代码 (尝试 {attempt + 1}/{max_fix_attempts + 1})...")
            exec_output = self.execute_code(code_file, data_files)

            if exec_output["success"]:
                # 检查结果JSON - 尝试多个可能的路径
                found_result = False
                possible_paths = []
                if results_json_path:
                    possible_paths.append(results_json_path)
                    # 添加可能的fallback路径（处理硬编码双重路径问题）
                    possible_paths.append(self.output_dir / self.output_dir.name / "execution" / "results.json")
                    possible_paths.append(self.output_dir / "results.json")
                    possible_paths.append(Path("results.json"))

                for path in possible_paths:
                    if path.exists():
                        try:
                            with open(path, "r", encoding="utf-8") as f:
                                execution_result = json.load(f)
                            print(f"    [CodeExecutor] 成功读取结果文件: {path}")
                            found_result = True
                            break
                        except Exception as e:
                            print(f"    [CodeExecutor] 结果JSON解析失败 ({path}): {e}")

                if found_result:
                    break

                if exec_output["output"]:
                    execution_result = {"stdout": exec_output["output"]}
                    break

            error_msg = exec_output.get("error", "")
            print(f"    [CodeExecutor] 执行失败: {error_msg[:200]}")

            if attempt < max_fix_attempts:
                success = self.fix_code(code_file, error_msg, exec_output.get("output", ""))
                if not success:
                    print(f"    [CodeExecutor] 自动修复未成功，继续尝试...")
            else:
                print(f"    [CodeExecutor] 达到最大修复次数")
                execution_result = {"error": error_msg, "stdout": exec_output.get("output", "")}

        return execution_result

    def generate_and_run(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        data_files: Optional[Dict[str, str]] = None,
        filename: str = "solve.py",
        use_claude_cli: bool = True,
    ) -> Dict[str, Any]:
        """
        一站式代码生成与执行

        Args:
            prompt: 代码生成提示词
            system_prompt: 系统提示词
            data_files: 数据文件映射
            filename: 保存的代码文件名
            use_claude_cli: 是否使用 Claude CLI（默认True）

        Returns:
            Dict: {"code": str, "execution_result": dict, "success": bool}
        """
        code_file = self.exec_dir / filename
        results_json = self.exec_dir / "results.json"

        # 1. 生成代码
        print(f"    [CodeExecutor] 生成代码...")
        raw_code = ""
        if use_claude_cli and self._claude_path:
            try:
                raw_code = self.generate_code_with_claude_cli(prompt, system_prompt)
                print(f"    [CodeExecutor] Claude CLI 代码生成成功")
            except subprocess.TimeoutExpired:
                print(f"    [CodeExecutor] Claude CLI 超时({180}s)，回退到 API...")
                if self.call_llm:
                    raw_code = self.call_llm(prompt, system_prompt)
                else:
                    raise RuntimeError("Claude CLI 超时且无可用的 API 回退")
            except Exception as e:
                print(f"    [CodeExecutor] Claude CLI 失败: {e}，回退到 API")
                if self.call_llm:
                    raw_code = self.call_llm(prompt, system_prompt)
                else:
                    raise
        elif self.call_llm:
            raw_code = self.call_llm(prompt, system_prompt)
        else:
            raise RuntimeError("无可用的代码生成方式")

        # 2. 提取并保存代码
        try:
            code = self.extract_code(raw_code, code_file)
            print(f"    [CodeExecutor] 代码已保存: {code_file}")
        except Exception as e:
            print(f"    [CodeExecutor] 代码提取失败: {e}")
            # 保存原始输出供调试
            code_file.write_text(raw_code, encoding="utf-8")
            code = raw_code

        # 3. 执行代码（带自动修复）
        execution_result = self.run_with_auto_fix(
            code_file=code_file,
            data_files=data_files,
            results_json_path=results_json,
        )

        # 4. 提取代码结构
        code_structure = self._extract_code_structure(code)

        return {
            "code": code,
            "code_file": str(code_file),
            "execution_result": execution_result,
            "success": "error" not in execution_result or not execution_result.get("error"),
            "code_structure": code_structure,
        }

    def _extract_code_structure(self, code: str) -> Dict[str, Any]:
        """提取代码结构（类、函数、输出文件）"""
        structure = {
            "classes": [],
            "functions": [],
            "imports": [],
            "file_outputs": [],
        }

        lines = code.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("class "):
                name = stripped.split("(")[0].replace("class ", "").strip(":")
                structure["classes"].append(name)
            elif stripped.startswith("def "):
                name = stripped.split("(")[0].replace("def ", "").strip(":")
                structure["functions"].append(name)
            elif stripped.startswith(("import ", "from ")):
                structure["imports"].append(stripped)

        # 检测文件输出
        if "results.json" in code:
            structure["file_outputs"].append("results.json")
        if ".png" in code or ".jpg" in code:
            structure["file_outputs"].append("chart images")
        if ".csv" in code:
            structure["file_outputs"].append("output.csv")
        if ".xlsx" in code:
            structure["file_outputs"].append("output.xlsx")

        return structure


import shutil
