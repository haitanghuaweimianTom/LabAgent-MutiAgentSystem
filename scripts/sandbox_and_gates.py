"""
代码执行沙箱 + 阶段质量门禁 + 多模型辩论

参考竞品：
- MAARS: 3-stage pipeline, iterative self-improvement
- MSc: multi-model counsel debate, persona council, quality gates
- math_model: 8 agents, 9 quality gates, anti-pattern hard blocking
- MARS: schema-validated artifacts, HITL at every step
"""
import ast
import json
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ==================== 代码执行沙箱 ====================

class CodeSandbox:
    """
    代码执行沙箱 - 基于现有 conda 环境，自动安装缺失包
    
    特性：
    - 复用现有 conda 环境（不重新创建）
    - 自动检测缺失包并安装
    - AST 级代码审计（检测硬编码指标）
    - 超时保护
    - 输出捕获
    """

    def __init__(self, conda_env: Optional[str] = None, timeout: int = 120):
        """
        Args:
            conda_env: conda 环境名称，None 表示使用当前环境
            timeout: 执行超时（秒）
        """
        self.conda_env = conda_env
        self.timeout = timeout

    def ast_audit(self, code: str) -> Dict:
        """
        AST 级代码审计 - 检测伪代码和硬编码
        
        Returns:
            {
                "passed": bool,
                "issues": [{"severity": "HIGH|MEDIUM|LOW", "type": str, "message": str}]
            }
        """
        issues = []
        
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {
                "passed": False,
                "issues": [{"severity": "HIGH", "type": "SYNTAX_ERROR", "message": f"语法错误: {e}"}]
            }
        
        # 检测硬编码指标
        hardcoded_patterns = [
            (r'accuracy\s*=\s*0\.\d+', "硬编码 accuracy"),
            (r'loss\s*=\s*0\.\d+', "硬编码 loss"),
            (r'f1\s*=\s*0\.\d+', "硬编码 F1"),
            (r'precision\s*=\s*0\.\d+', "硬编码 precision"),
            (r'recall\s*=\s*0\.\d+', "硬编码 recall"),
        ]
        
        for node in ast.walk(tree):
            # 检测硬编码赋值
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_name = target.id.lower()
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)):
                            # 检查是否是常见指标名
                            if any(metric in var_name for metric in ['accuracy', 'loss', 'f1', 'precision', 'recall', 'score']):
                                issues.append({
                                    "severity": "HIGH",
                                    "type": "HARDCODED_METRIC",
                                    "message": f"检测到硬编码指标: {target.id} = {node.value.value}"
                                })
            
            # 检测 print 语句（需要有输出才能验证）
            # 这是允许的，只是标记
            
            # 检测 input() 调用（沙箱中不允许）
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'input':
                issues.append({
                    "severity": "HIGH",
                    "type": "INPUT_CALL",
                    "message": "检测到 input() 调用，沙箱中不允许"
                })
        
        return {
            "passed": not any(i["severity"] == "HIGH" for i in issues),
            "issues": issues
        }

    def detect_missing_packages(self, code: str) -> list:
        """检测代码中使用的包，返回缺失的包列表"""
        import importlib.util
        import re
        
        # 提取 import 语句（更健壮的解析）
        imported = set()
        
        # 匹配 import xxx 和 from xxx import yyy
        for match in re.finditer(r'^(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)', code, re.MULTILINE):
            pkg = match.group(1)
            # 跳过标准库
            if pkg in ['os', 'sys', 'json', 'math', 're', 'datetime', 'pathlib', 'typing', 'time']:
                continue
            imported.add(pkg)
        
        # 检查哪些包未安装
        missing = []
        for pkg in imported:
            spec = importlib.util.find_spec(pkg)
            if spec is None:
                missing.append(pkg)
        
        return missing

    def install_packages(self, packages: list) -> bool:
        """自动安装缺失的包"""
        if not packages:
            return True
        
        logger.info(f"安装缺失的包: {packages}")
        
        # 使用 pip 安装
        try:
            cmd = [sys.executable, "-m", "pip", "install", "-q"] + packages
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                logger.warning(f"pip 安装失败: {result.stderr}")
                return False
            
            logger.info(f"成功安装: {packages}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.warning(f"安装超时: {packages}")
            return False
        except Exception as e:
            logger.warning(f"安装异常: {e}")
            return False

    def execute(self, code: str, code_path: Optional[Path] = None) -> Dict:
        """
        执行代码（带沙箱保护）
        
        Returns:
            {
                "success": bool,
                "stdout": str,
                "stderr": str,
                "audit": {"passed": bool, "issues": list},
                "missing_packages": list,
                "installed_packages": list
            }
        """
        # 1. AST 审计
        audit = self.ast_audit(code)
        if not audit["passed"]:
            return {
                "success": False,
                "stdout": "",
                "stderr": "AST 审计失败",
                "audit": audit,
                "missing_packages": [],
                "installed_packages": []
            }
        
        # 2. 检测缺失包
        missing = self.detect_missing_packages(code)
        installed = []
        
        if missing:
            # 3. 自动安装
            if self.install_packages(missing):
                installed = missing
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"无法安装缺失包: {missing}",
                    "audit": audit,
                    "missing_packages": missing,
                    "installed_packages": []
                }
        
        # 4. 写入临时文件
        if code_path is None:
            code_path = Path(tempfile.mktemp(suffix=".py"))
            code_path.write_text(code, encoding="utf-8")
        
        # 5. 执行
        try:
            result = subprocess.run(
                [sys.executable, str(code_path)],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "audit": audit,
                "missing_packages": missing,
                "installed_packages": installed
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行超时 ({self.timeout}s)",
                "audit": audit,
                "missing_packages": missing,
                "installed_packages": installed
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "audit": audit,
                "missing_packages": missing,
                "installed_packages": installed
            }


# ==================== 阶段质量门禁 ====================

class QualityGate:
    """
    阶段间质量门禁 - 确保每个阶段输出满足最低标准
    
    参考 MSc + math_model 的门禁设计
    """

    # 门禁规则
    GATES = {
        "research": {
            "min_references": 3,
            "min_content_length": 200,
            "require_real_arxiv": True
        },
        "modeling": {
            "min_sub_problems": 1,
            "require_formulas": True,
            "min_notation": 3
        },
        "code": {
            "require_syntax_valid": True,
            "min_lines": 10,
            "require_print": True  # 必须有 print 输出
        },
        "writing": {
            "min_sections": 3,
            "min_abstract_length": 100,
            "min_references": 5
        },
        "review": {
            "min_score": 2.0,
            "require_issues": True
        }
    }

    @classmethod
    def validate(cls, stage: str, data: Dict) -> Dict:
        """
        验证阶段输出
        
        Returns:
            {
                "passed": bool,
                "gate": str,
                "checks": [{"check": str, "passed": bool, "message": str}],
                "severity": "PASS|WARN|FAIL"
            }
        """
        gate = cls.GATES.get(stage, {})
        checks = []
        
        if stage == "research":
            # 检查引用数量
            refs = data.get("references", [])
            checks.append({
                "check": "min_references",
                "passed": len(refs) >= gate.get("min_references", 3),
                "message": f"引用数: {len(refs)}/{gate.get('min_references', 3)}"
            })
            
            # 检查内容长度
            content = data.get("content", "")
            checks.append({
                "check": "min_content_length",
                "passed": len(content) >= gate.get("min_content_length", 200),
                "message": f"内容长度: {len(content)}/{gate.get('min_content_length', 200)}"
            })
            
            # 检查是否有真实 arxiv ID
            if gate.get("require_real_arxiv"):
                real_count = sum(1 for r in refs if r.get("arxiv_id", "").startswith("2"))
                checks.append({
                    "check": "require_real_arxiv",
                    "passed": real_count >= gate.get("min_references", 3),
                    "message": f"真实 arxiv ID 数: {real_count}"
                })
        
        elif stage == "modeling":
            # 检查子问题数量
            sub_problems = data.get("sub_problems", [])
            checks.append({
                "check": "min_sub_problems",
                "passed": len(sub_problems) >= gate.get("min_sub_problems", 1),
                "message": f"子问题数: {len(sub_problems)}/{gate.get('min_sub_problems', 1)}"
            })
            
            # 检查是否有公式
            notation = data.get("notation", {})
            checks.append({
                "check": "min_notation",
                "passed": len(notation) >= gate.get("min_notation", 3),
                "message": f"符号表条目: {len(notation)}/{gate.get('min_notation', 3)}"
            })
        
        elif stage == "code":
            # 检查代码语法
            code = data.get("code", "")
            try:
                ast.parse(code)
                syntax_valid = True
            except SyntaxError:
                syntax_valid = False
            
            checks.append({
                "check": "require_syntax_valid",
                "passed": syntax_valid,
                "message": "语法检查" if syntax_valid else "语法错误"
            })
            
            # 检查行数
            line_count = len(code.split('\n'))
            checks.append({
                "check": "min_lines",
                "passed": line_count >= gate.get("min_lines", 10),
                "message": f"代码行数: {line_count}/{gate.get('min_lines', 10)}"
            })
            
            # 检查是否有 print
            checks.append({
                "check": "require_print",
                "passed": "print(" in code,
                "message": "包含 print 语句" if "print(" in code else "缺少 print 语句"
            })
        
        elif stage == "writing":
            # 检查章节数
            sections = data.get("sections", [])
            checks.append({
                "check": "min_sections",
                "passed": len(sections) >= gate.get("min_sections", 3),
                "message": f"章节数: {len(sections)}/{gate.get('min_sections', 3)}"
            })
            
            # 检查摘要长度
            abstract = data.get("abstract", "")
            checks.append({
                "check": "min_abstract_length",
                "passed": len(abstract) >= gate.get("min_abstract_length", 100),
                "message": f"摘要长度: {len(abstract)}/{gate.get('min_abstract_length', 100)}"
            })
            
            # 检查引用数
            refs = data.get("references", [])
            checks.append({
                "check": "min_references",
                "passed": len(refs) >= gate.get("min_references", 5),
                "message": f"引用数: {len(refs)}/{gate.get('min_references', 5)}"
            })
        
        elif stage == "review":
            # 检查评分
            overall_score = data.get("overall_score", 0)
            checks.append({
                "check": "min_score",
                "passed": overall_score >= gate.get("min_score", 2.0),
                "message": f"总体评分: {overall_score}/{gate.get('min_score', 2.0)}"
            })
            
            # 检查是否有问题列表
            major_issues = data.get("major_issues", [])
            checks.append({
                "check": "require_issues",
                "passed": len(major_issues) > 0 or overall_score >= 4.0,
                "message": f"主要问题数: {len(major_issues)}"
            })
        
        # 计算结果
        all_passed = all(c["passed"] for c in checks)
        has_high_severity = any(not c["passed"] for c in checks)
        
        if all_passed:
            severity = "PASS"
        elif has_high_severity:
            severity = "FAIL"
        else:
            severity = "WARN"
        
        return {
            "passed": all_passed,
            "gate": stage,
            "checks": checks,
            "severity": severity
        }


# ==================== 多模型辩论 ====================

class MultiModelDebate:
    """
    多模型辩论系统 - 参考 MSc counsel + 改进
    
    改进点：
    1. 角色定义更清晰（实用性、严谨性、叙事性）
    2. 辩论轮数可配置
    3. 自动降级（单模型 → 模拟辩论）
    4. 结构化冲突解决
    """

    def __init__(self, call_fn, models: Optional[list] = None, rounds: int = 2):
        """
        Args:
            call_fn: 异步函数，签名 (system, user, max_tokens) -> dict
            models: 候选模型列表，None 表示使用单模型模拟
            rounds: 辩论轮数
        """
        self.call_fn = call_fn
        self.models = models or ["MiniMax-M3"]
        self.rounds = rounds

    async def persona_debate(self, topic: str, context: str) -> Dict:
        """
        角色辩论 - 3 个角色从不同角度评估方案
        
        Returns:
            {
                "synthesis": str,
                "personas": [
                    {"name": str, "feedback": str, "score": float}
                ],
                "rounds": int
            }
        """
        personas = [
            {
                "name": "Practical",
                "system": "你是一位注重实用性的研究员。你关注方案的可行性、实现成本和实际应用价值。"
            },
            {
                "name": "Rigor",
                "system": "你是一位严谨的理论家。你关注方案的数学严谨性、逻辑一致性和理论基础。"
            },
            {
                "name": "Narrative",
                "system": "你是一位叙事架构师。你关注方案的故事性、论文的逻辑流和读者体验。"
            }
        ]
        
        all_feedback = []
        
        for round_num in range(self.rounds):
            round_feedback = []
            
            for persona in personas:
                system = (
                    f"{persona['system']}\n\n"
                    f"这是第 {round_num + 1}/{self.rounds} 轮辩论。\n"
                    f"请对以下方案给出你的评估和建议。"
                )
                
                user = f"【方案主题】\n{topic}\n\n【上下文】\n{context[:3000]}"
                
                try:
                    resp = await self.call_fn(system, user, max_tokens=4000)
                    feedback = resp.get("content", "")
                except Exception as e:
                    feedback = f"评估失败: {e}"
                
                round_feedback.append({
                    "name": persona["name"],
                    "feedback": feedback,
                    "round": round_num + 1
                })
            
            all_feedback.extend(round_feedback)
        
        # 综合所有反馈
        synthesis = self._synthesize_feedback(all_feedback, topic)
        
        return {
            "synthesis": synthesis,
            "personas": all_feedback,
            "rounds": self.rounds
        }

    def _synthesize_feedback(self, feedbacks: list, topic: str) -> str:
        """综合所有角色反馈，生成最终建议"""
        if not feedbacks:
            return "无反馈"
        
        # 简单综合：按角色分组，提取关键点
        by_persona = {}
        for fb in feedbacks:
            name = fb["name"]
            if name not in by_persona:
                by_persona[name] = []
            by_persona[name].append(fb["feedback"])
        
        lines = [f"## 综合评估 — {topic}\n"]
        
        for persona_name, feedbacks_list in by_persona.items():
            lines.append(f"### {persona_name} 角色反馈")
            # 取最后一轮的反馈（最成熟）
            lines.append(feedbacks_list[-1][:500])
            lines.append("")
        
        return "\n".join(lines)


# ==================== 图表生成 ====================

class FigureGenerator:
    """
    图表生成器 - 自动从代码输出生成 Nature-style 图表
    
    参考 Nature 配色方案
    """

    # Nature 风格配色
    NATURE_COLORS = [
        '#E64B35',  # 红
        '#4DBBD5',  # 青
        '#00A087',  # 绿
        '#3C5488',  # 蓝
        '#F39B7F',  # 橙
        '#8491B4',  # 灰蓝
        '#91D1C2',  # 浅绿
        '#DC0000',  # 深红
    ]

    @classmethod
    def generate_from_code_output(cls, code: str, stdout: str, output_dir: Path) -> list:
        """
        从代码输出自动生成图表
        
        Returns:
            生成的图表文件路径列表
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        figures = []
        
        try:
            import matplotlib
            matplotlib.use('Agg')  # 非交互后端
            import matplotlib.pyplot as plt
            import numpy as np
        except ImportError:
            logger.warning("matplotlib 未安装，跳过图表生成")
            return []
        
        # 设置 Nature 风格
        plt.rcParams.update({
            'font.size': 10,
            'axes.titlesize': 12,
            'axes.labelsize': 10,
            'xtick.labelsize': 8,
            'ytick.labelsize': 8,
            'legend.fontsize': 8,
            'figure.dpi': 300,
            'savefig.dpi': 300,
            'savefig.bbox': 'tight',
            'axes.spines.top': False,
            'axes.spines.right': False,
        })
        
        # 尝试从代码中提取绘图数据
        try:
            # 执行代码并捕获图形
            exec_globals = {}
            exec(code, exec_globals)
            
            # 查找 matplotlib 图形
            fig_nums = plt.get_fignums()
            for i, fig_num in enumerate(fig_nums):
                fig = plt.figure(fig_num)
                fig_path = output_dir / f"figure_{i+1}.png"
                fig.savefig(str(fig_path), dpi=300, bbox_inches='tight')
                figures.append(str(fig_path))
                plt.close(fig)
            
            if figures:
                logger.info(f"生成了 {len(figures)} 个图表")
                return figures
                
        except Exception as e:
            logger.warning(f"从代码生成图表失败: {e}")
        
        # 如果无法从代码生成，尝试解析 stdout 生成简单图表
        if not figures:
            figures = cls._generate_from_stdout(stdout, output_dir)
        
        return figures

    @classmethod
    def _generate_from_stdout(cls, stdout: str, output_dir: Path) -> list:
        """从 stdout 解析数据并生成简单图表"""
        figures = []
        
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import numpy as np
        except ImportError:
            return []
        
        # 尝试解析 stdout 中的数值数据
        lines = stdout.strip().split('\n')
        data_points = []
        
        for line in lines:
            # 尝试解析 "key: value" 或 "key = value" 格式
            import re
            match = re.search(r'(\w+[\s_]*\w*)\s*[:=]\s*([\d.]+)', line)
            if match:
                data_points.append({
                    "label": match.group(1).strip(),
                    "value": float(match.group(2))
                })
        
        if not data_points:
            return []
        
        # 生成柱状图
        fig, ax = plt.subplots(figsize=(8, 5))
        
        labels = [d["label"][:20] for d in data_points[:8]]  # 最多 8 个
        values = [d["value"] for d in data_points[:8]]
        
        bars = ax.bar(range(len(labels)), values, color=cls.NATURE_COLORS[:len(labels)])
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha='right')
        ax.set_ylabel('Value')
        ax.set_title('Code Output Analysis')
        
        fig_path = output_dir / "figure_1.png"
        fig.savefig(str(fig_path), dpi=300, bbox_inches='tight')
        figures.append(str(fig_path))
        plt.close(fig)
        
        return figures


# ==================== 反模式检测 ====================

class AntiPatternDetector:
    """
    反模式检测器 - 参考 math_model 的反模式硬阻断
    
    检测：
    - 写作中的硬编码指标
    - 代码中的硬编码指标
    - 虚假引用
    - 过度承诺
    """

    # 写作反模式
    WRITING_PATTERNS = [
        (r'(?:accuracy|precision|recall|f1|auc|rmse|mse)\s*(?:=|：|达到|为)\s*0\.\d{2,}', "硬编码指标值"),
        (r'(?:提升|提高|增加|降低|减少)\s*\d{2,}\s*%', "无来源的百分比声明"),
        (r'(?:显著|明显|大幅)\s*(?:优于|高于|低于)', "无统计显著性的比较"),
        (r'(?:state.of.the.art|SOTA|最优|最佳)', "未经证实的最优声明"),
        (r'(?:100%|完全|全部|所有)', "绝对化声明"),
    ]

    # 代码反模式
    CODE_PATTERNS = [
        (r'(?:accuracy|precision|recall|f1|auc|rmse|mse)\s*=\s*0\.\d{2,}', "硬编码指标赋值"),
        (r'assert\s+(?:accuracy|precision|recall|f1)\s*[><=]+\s*0\.\d', "断言硬编码指标"),
        (r'print\s*\(\s*["\'].*?(?:accuracy|precision|recall|f1).*?["\']', "打印硬编码指标"),
    ]

    @classmethod
    def detect_writing_patterns(cls, text: str) -> list:
        """检测写作中的反模式"""
        issues = []
        for pattern, desc in cls.WRITING_PATTERNS:
            import re
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                issues.append({
                    "type": "WRITING_ANTI_PATTERN",
                    "severity": "MEDIUM",
                    "message": f"{desc}: {match.group()[:50]}",
                    "position": match.start()
                })
        return issues

    @classmethod
    def detect_code_patterns(cls, code: str) -> list:
        """检测代码中的反模式"""
        issues = []
        for pattern, desc in cls.CODE_PATTERNS:
            import re
            matches = re.finditer(pattern, code, re.IGNORECASE)
            for match in matches:
                issues.append({
                    "type": "CODE_ANTI_PATTERN",
                    "severity": "HIGH",
                    "message": f"{desc}: {match.group()[:50]}",
                    "position": match.start()
                })
        return issues

    @classmethod
    def detect_all(cls, text: str, is_code: bool = False) -> dict:
        """检测所有反模式"""
        if is_code:
            issues = cls.detect_code_patterns(text)
        else:
            issues = cls.detect_writing_patterns(text)
        
        return {
            "passed": not any(i["severity"] == "HIGH" for i in issues),
            "issues": issues,
            "high_count": sum(1 for i in issues if i["severity"] == "HIGH"),
            "medium_count": sum(1 for i in issues if i["severity"] == "MEDIUM")
        }


# ==================== 代码自动修复 ====================

class CodeAutoFixer:
    """
    代码自动修复 - 执行失败后让 LLM 修复
    
    流程：
    1. 执行代码
    2. 如果失败，提取错误信息
    3. 让 LLM 修复代码
    4. 重新执行
    5. 最多重试 max_retries 次
    """

    def __init__(self, call_fn, sandbox: CodeSandbox, max_retries: int = 2):
        """
        Args:
            call_fn: 异步函数，签名 (system, user, max_tokens) -> dict
            sandbox: CodeSandbox 实例
            max_retries: 最大重试次数
        """
        self.call_fn = call_fn
        self.sandbox = sandbox
        self.max_retries = max_retries

    async def execute_with_fix(self, code: str, problem: str) -> Dict:
        """
        执行代码，失败时自动修复
        
        Returns:
            {
                "success": bool,
                "code": str,
                "attempts": int,
                "errors": list,
                "execution": dict
            }
        """
        attempts = 0
        errors = []
        current_code = code
        
        while attempts <= self.max_retries:
            # 执行
            result = self.sandbox.execute(current_code)
            
            if result["success"]:
                return {
                    "success": True,
                    "code": current_code,
                    "attempts": attempts + 1,
                    "errors": errors,
                    "execution": result
                }
            
            # 记录错误
            error_msg = result["stderr"]
            errors.append({
                "attempt": attempts + 1,
                "error": error_msg
            })
            
            # 如果还有重试机会，让 LLM 修复
            if attempts < self.max_retries:
                current_code = await self._fix_code(current_code, error_msg, problem)
            
            attempts += 1
        
        return {
            "success": False,
            "code": current_code,
            "attempts": attempts,
            "errors": errors,
            "execution": result
        }

    async def _fix_code(self, code: str, error: str, problem: str) -> str:
        """让 LLM 修复代码"""
        system = (
            "你是一位 Python 调试专家。给定代码和错误信息，"
            "请修复代码使其能正确运行。只输出修复后的完整代码。"
        )
        
        user = f"""【原始问题】
{problem[:1000]}

【当前代码】
```python
{code}
```

【错误信息】
{error}

请返回修复后的完整 Python 代码（用 ```python 块包裹）："""
        
        try:
            resp = await self.call_fn(system, user, max_tokens=32000)
            content = resp.get("content", "")
            
            # 提取代码
            import re
            code_match = re.search(r"```python\s*\n(.*?)```", content, re.DOTALL)
            if code_match:
                return code_match.group(1).strip()
            
            # 如果没有代码块，尝试提取 import 开始的代码
            lines = content.split("\n")
            start = -1
            for i, line in enumerate(lines):
                if line.strip().startswith(("import ", "from ")):
                    start = i
                    break
            if start >= 0:
                return "\n".join(lines[start:])
            
            return code  # 修复失败，返回原代码
            
        except Exception as e:
            return code  # 修复失败，返回原代码


# ==================== 导出 ====================

__all__ = [
    "CodeSandbox",
    "QualityGate", 
    "MultiModelDebate",
    "FigureGenerator",
    "AntiPatternDetector",
    "CodeAutoFixer"
]
