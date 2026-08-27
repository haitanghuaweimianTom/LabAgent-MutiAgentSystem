"""
输出保障机制：
1. 排版格式正确（LaTeX 转义 + 数学模式 + CJK + 参考文献格式）
2. 参考文献无幻觉（多层验证 + 标题匹配 + 去重）
3. Idea 不重复（历史记录 + 相似度检测）
"""
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ==================== 1. 排版格式保障 ====================


class LaTeXFormatter:
    """
    LaTeX 排版格式保障
    
    确保：
    - 数学模式正确包裹
    - CJK 字符正确转义
    - 特殊字符正确处理
    - 参考文献格式正确
    """

    # LaTeX 特殊字符（需要转义）
    SPECIAL_CHARS = {
        '&': r'\&',
        '%': r'\%',
        '#': r'\#',
        '_': r'\_',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
        '\\': r'\textbackslash{}',
    }

    # 不应转义的字符（在数学模式中）
    MATH_MODE_CHARS = {'$', '_', '^', '\\'}

    @classmethod
    def escape_text(cls, text: str) -> str:
        """转义 LaTeX 文本（保留数学模式）"""
        if not text:
            return ""

        # 1. 保护数学模式：$...$ 和 \(...\) 和 \[...\]
        math_patterns = []

        def save_math(m):
            math_patterns.append(m.group(0))
            # 使用不包含特殊字符的占位符
            return f"MATHPLACEHOLDER{len(math_patterns) - 1}ENDMATH"

        text = re.sub(r'\$[^$]+\$', save_math, text)
        text = re.sub(r'\\[(\[][^\\]*\\[)\]]', save_math, text)

        # 2. 转义特殊字符（注意顺序：先转义反斜杠）
        text = text.replace('\\', r'\textbackslash{}')
        for char, replacement in cls.SPECIAL_CHARS.items():
            if char != '\\':  # 反斜杠已处理
                text = text.replace(char, replacement)

        # 3. 恢复数学模式
        for i, m in enumerate(math_patterns):
            text = text.replace(f"MATHPLACEHOLDER{i}ENDMATH", m)

        return text

    @classmethod
    def ensure_math_mode(cls, text: str) -> str:
        """确保常见数学表达式在数学模式中"""
        # O(n) → $O(n)$
        text = re.sub(r'(?<!\$)O\(([^)]{1,20})\)(?!\$)', r'$O(\1)$', text)
        # α, β, γ 等希腊字母
        greek_letters = ['α', 'β', 'γ', 'δ', 'ε', 'θ', 'λ', 'μ', 'π', 'σ', 'φ', 'ω']
        for letter in greek_letters:
            text = text.replace(letter, f'${letter}$')

        return text

    @classmethod
    def validate_latex(cls, tex_content: str) -> Dict:
        """
        验证 LaTeX 内容格式
        
        Returns:
            {
                "valid": bool,
                "errors": list,
                "warnings": list
            }
        """
        errors = []
        warnings = []

        # 检查基本结构
        if r'\begin{document}' not in tex_content:
            errors.append("缺少 \\begin{document}")
        if r'\end{document}' not in tex_content:
            errors.append("缺少 \\end{document}")

        # 检查未闭合的数学模式
        dollar_count = tex_content.count('$') - tex_content.count('\\$')
        if dollar_count % 2 != 0:
            errors.append("未闭合的数学模式（$ 数量为奇数）")

        # 检查未闭合的环境
        begins = len(re.findall(r'\\begin\{[^}]+\}', tex_content))
        ends = len(re.findall(r'\\end\{[^}]+\}', tex_content))
        if begins != ends:
            errors.append(f"未闭合的环境：\\begin 数量 {begins} ≠ \\end 数量 {ends}")

        # 检查 CJK 字符（如果没有 xeCJK 包）
        cjk_chars = re.findall(r'[\u4e00-\u9fff]', tex_content)
        if cjk_chars and r'\usepackage{xeCJK}' not in tex_content:
            warnings.append("包含 CJK 字符但未加载 xeCJK 包")

        # 检查参考文献格式
        if r'\bibitem' in tex_content:
            bibitems = re.findall(r'\\bibitem\{([^}]+)\}', tex_content)
            if not bibitems:
                warnings.append("\\bibitem 为空")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    @classmethod
    def format_bibliography(cls, references: List[Dict]) -> str:
        """生成格式正确的参考文献"""
        lines = [r"\begin{thebibliography}{99}"]

        for i, ref in enumerate(references, 1):
            arxiv_id = ref.get("arxiv_id", "")
            title = cls.escape_text(ref.get("title", arxiv_id))
            authors = ref.get("authors", [])
            year = ref.get("year", "2024")

            # 格式：\bibitem{key} Authors. Title. arXiv:ID, Year.
            author_str = ", ".join(authors[:3]) if authors else "Unknown"
            if len(authors) > 3:
                author_str += " et al."

            bib_entry = (
                f"\\bibitem{{{arxiv_id}}} "
                f"{cls.escape_text(author_str)}. "
                f"\\textit{{{title}}}. "
                f"arXiv:{arxiv_id}, {year}."
            )
            lines.append(bib_entry)

        lines.append(r"\end{thebibliography}")
        return "\n".join(lines)


# ==================== 2. 参考文献无幻觉 ====================


class ReferenceVerifier:
    """
    参考文献多层验证
    
    确保：
    - 所有引用都是真实的 arxiv 论文
    - 引用标题与实际论文匹配
    - 引用在论文中被正确引用
    - 无重复引用
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Args:
            cache_dir: 缓存目录，用于存储已验证的引用信息
        """
        self.cache_dir = cache_dir or Path.home() / ".cache" / "paper_generator" / "references"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.verified_cache: Dict[str, Dict] = {}
        self._load_cache()

    def _load_cache(self):
        """加载缓存"""
        cache_file = self.cache_dir / "verified.json"
        if cache_file.exists():
            try:
                self.verified_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                self.verified_cache = {}

    def _save_cache(self):
        """保存缓存"""
        cache_file = self.cache_dir / "verified.json"
        cache_file.write_text(json.dumps(self.verified_cache, indent=2, ensure_ascii=False), encoding="utf-8")

    def verify_arxiv(self, arxiv_id: str) -> Dict:
        """
        验证 arxiv ID 是否真实
        
        Returns:
            {
                "arxiv_id": str,
                "is_real": bool,
                "title": Optional[str],
                "authors": List[str],
                "verified_at": str,
                "source": str
            }
        """
        # 检查缓存
        if arxiv_id in self.verified_cache:
            cached = self.verified_cache[arxiv_id]
            cached["source"] = "cache"
            return cached

        # 从 arxiv API 验证
        import httpx

        url = f"https://arxiv.org/abs/{arxiv_id}"
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(url, follow_redirects=True)

            if resp.status_code != 200:
                return {
                    "arxiv_id": arxiv_id,
                    "is_real": False,
                    "title": None,
                    "authors": [],
                    "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "source": "arxiv_api",
                }

            # 解析 HTML
            html = resp.text
            title_m = re.search(r'<meta\s+name="citation_title"\s+content="([^"]+)"', html)
            authors_m = re.findall(r'<meta\s+name="citation_author"\s+content="([^"]+)"', html)

            result = {
                "arxiv_id": arxiv_id,
                "is_real": True,
                "title": title_m.group(1) if title_m else None,
                "authors": authors_m,
                "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "arxiv_api",
            }

            # 缓存结果
            self.verified_cache[arxiv_id] = result
            self._save_cache()

            return result

        except Exception as e:
            logger.warning(f"验证 arxiv ID {arxiv_id} 失败: {e}")
            return {
                "arxiv_id": arxiv_id,
                "is_real": False,
                "title": None,
                "authors": [],
                "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "error",
            }

    def verify_title_match(self, arxiv_id: str, claimed_title: str) -> Dict:
        """
        验证引用标题是否与实际论文匹配
        
        Returns:
            {
                "arxiv_id": str,
                "title_match": bool,
                "claimed_title": str,
                "actual_title": Optional[str],
                "similarity": float
            }
        """
        # 获取实际标题
        verification = self.verify_arxiv(arxiv_id)
        actual_title = verification.get("title")

        if not actual_title:
            return {
                "arxiv_id": arxiv_id,
                "title_match": False,
                "claimed_title": claimed_title,
                "actual_title": None,
                "similarity": 0.0,
            }

        # 计算相似度（简单的 Jaccard 相似度）
        claimed_words = set(claimed_title.lower().split())
        actual_words = set(actual_title.lower().split())

        if not claimed_words or not actual_words:
            similarity = 0.0
        else:
            intersection = claimed_words & actual_words
            union = claimed_words | actual_words
            similarity = len(intersection) / len(union)

        return {
            "arxiv_id": arxiv_id,
            "title_match": similarity > 0.5,  # 阈值 50%
            "claimed_title": claimed_title,
            "actual_title": actual_title,
            "similarity": similarity,
        }

    def check_citation_in_text(self, text: str, arxiv_id: str) -> bool:
        """检查文本中是否引用了指定的 arxiv ID"""
        patterns = [
            rf"\b{re.escape(arxiv_id)}\b",
            rf"arxiv\.org/(?:abs|pdf)/{re.escape(arxiv_id)}",
            rf"arXiv:{re.escape(arxiv_id)}",
        ]
        for p in patterns:
            if re.search(p, text, re.IGNORECASE):
                return True
        return False

    def verify_all_references(
        self,
        text: str,
        references: List[Dict],
        real_pool: List[str],
    ) -> Dict:
        """
        全面验证所有引用
        
        Returns:
            {
                "total": int,
                "verified": int,
                "fake": int,
                "uncited": int,
                "details": list
            }
        """
        real_set = set(real_pool)
        verified = []
        fake = []
        uncited = []
        details = []

        for ref in references:
            arxiv_id = ref.get("arxiv_id", "")
            claimed_title = ref.get("title", "")

            # 1. 验证是否真实
            if arxiv_id in real_set:
                # 在模板池中，直接通过
                is_real = True
                source = "template_pool"
            else:
                # 需要 API 验证
                verification = self.verify_arxiv(arxiv_id)
                is_real = verification["is_real"]
                source = "arxiv_api"

            # 2. 验证标题匹配
            if is_real and claimed_title:
                title_check = self.verify_title_match(arxiv_id, claimed_title)
                if not title_check["title_match"]:
                    details.append({
                        "arxiv_id": arxiv_id,
                        "issue": "title_mismatch",
                        "claimed": claimed_title,
                        "actual": title_check["actual_title"],
                        "similarity": title_check["similarity"],
                    })

            # 3. 检查是否被引用
            if not self.check_citation_in_text(text, arxiv_id):
                uncited.append(arxiv_id)
                details.append({
                    "arxiv_id": arxiv_id,
                    "issue": "uncited",
                })

            if is_real:
                verified.append(arxiv_id)
            else:
                fake.append(arxiv_id)
                details.append({
                    "arxiv_id": arxiv_id,
                    "issue": "fake_reference",
                })

        return {
            "total": len(references),
            "verified": len(verified),
            "fake": len(fake),
            "uncited": len(uncited),
            "details": details,
        }

    def deduplicate_references(self, references: List[Dict]) -> List[Dict]:
        """去重引用（基于 arxiv_id）"""
        seen = set()
        unique = []
        for ref in references:
            arxiv_id = ref.get("arxiv_id", "")
            if arxiv_id not in seen:
                seen.add(arxiv_id)
                unique.append(ref)
        return unique


# ==================== 3. Idea 不重复 ====================


class IdeaDeduplicator:
    """
    Idea 去重保障
    
    确保：
    - 新 idea 不与历史记录重复
    - 相似度检测防止微小变异的重复
    """

    def __init__(self, history_dir: Optional[Path] = None):
        """
        Args:
            history_dir: 历史记录目录
        """
        self.history_dir = history_dir or Path.home() / ".cache" / "paper_generator" / "ideas"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.history_dir / "history.json"
        self.history: List[Dict] = self._load_history()

    def _load_history(self) -> List[Dict]:
        """加载历史记录"""
        if self.history_file.exists():
            try:
                return json.loads(self.history_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save_history(self):
        """保存历史记录"""
        self.history_file.write_text(
            json.dumps(self.history, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _compute_fingerprint(self, text: str) -> str:
        """计算文本指纹"""
        # 清理文本：小写、去标点、去多余空格
        cleaned = re.sub(r'[^\w\s]', '', text.lower())
        cleaned = ' '.join(cleaned.split())
        return hashlib.md5(cleaned.encode()).hexdigest()

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（Jaccard）"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)

    def check_duplicate(self, idea: str, threshold: float = 0.7) -> Dict:
        """
        检查 idea 是否重复
        
        Args:
            idea: 新的 idea 描述
            threshold: 相似度阈值（超过则认为重复）
        
        Returns:
            {
                "is_duplicate": bool,
                "similar_ideas": list,
                "max_similarity": float
            }
        """
        fingerprint = self._compute_fingerprint(idea)
        similar_ideas = []
        max_similarity = 0.0

        for record in self.history:
            # 检查指纹完全匹配
            if record.get("fingerprint") == fingerprint:
                return {
                    "is_duplicate": True,
                    "similar_ideas": [record],
                    "max_similarity": 1.0,
                }

            # 检查相似度
            similarity = self._compute_similarity(idea, record.get("idea", ""))
            if similarity > max_similarity:
                max_similarity = similarity

            if similarity >= threshold:
                similar_ideas.append({
                    "idea": record.get("idea", ""),
                    "project": record.get("project_name", ""),
                    "created_at": record.get("created_at", ""),
                    "similarity": similarity,
                })

        return {
            "is_duplicate": len(similar_ideas) > 0,
            "similar_ideas": similar_ideas,
            "max_similarity": max_similarity,
        }

    def record_idea(self, idea: str, project_name: str, metadata: Optional[Dict] = None):
        """记录 idea 到历史"""
        record = {
            "idea": idea,
            "fingerprint": self._compute_fingerprint(idea),
            "project_name": project_name,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "metadata": metadata or {},
        }
        self.history.append(record)
        self._save_history()
        logger.info(f"记录 idea: {project_name} - {idea[:50]}...")

    def get_all_ideas(self) -> List[Dict]:
        """获取所有历史 idea"""
        return self.history


# ==================== 统一接口 ====================


class OutputGuarantee:
    """
    统一输出保障接口
    
    整合排版、引用验证、idea 去重三大功能
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.formatter = LaTeXFormatter()
        self.verifier = ReferenceVerifier(cache_dir)
        self.deduplicator = IdeaDeduplicator(cache_dir / "ideas" if cache_dir else None)

    def guarantee_output(
        self,
        tex_content: str,
        paper_md: str,
        references: List[Dict],
        real_pool: List[str],
        idea: str,
        project_name: str,
    ) -> Dict:
        """
        全面保障输出质量
        
        Returns:
            {
                "format_valid": bool,
                "format_errors": list,
                "reference_valid": bool,
                "reference_result": dict,
                "idea_unique": bool,
                "idea_check": dict,
                "overall_pass": bool
            }
        """
        # 1. 排版格式验证
        format_check = self.formatter.validate_latex(tex_content)

        # 2. 参考文献验证
        ref_result = self.verifier.verify_all_references(
            paper_md, references, real_pool
        )
        ref_valid = ref_result["fake"] == 0

        # 3. Idea 去重检查
        idea_check = self.deduplicator.check_duplicate(idea)
        idea_unique = not idea_check["is_duplicate"]

        # 4. 如果通过，记录 idea
        if idea_unique:
            self.deduplicator.record_idea(idea, project_name)

        overall_pass = format_check["valid"] and ref_valid and idea_unique

        return {
            "format_valid": format_check["valid"],
            "format_errors": format_check["errors"],
            "format_warnings": format_check["warnings"],
            "reference_valid": ref_valid,
            "reference_result": ref_result,
            "idea_unique": idea_unique,
            "idea_check": idea_check,
            "overall_pass": overall_pass,
        }


# ==================== 导出 ====================

__all__ = [
    "LaTeXFormatter",
    "ReferenceVerifier",
    "IdeaDeduplicator",
    "OutputGuarantee",
]
