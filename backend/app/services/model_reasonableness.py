"""模型合理性 LLM 判定器（设计 R3）。

学术标准（grill 查证）：校准≠验证；模型必须做历史回测/样本外验证；
参数应与已有研究对比；敏感性/稳健性；结论要自洽（coherent story）。

本判定器读四个输入：论文建模章节、模型代码、模型输出 CSV、观测真实值。
- REASONABLE: 判定通过
- ON_CONCERN: 判定存疑 → 仅 warning，打标，不拦 passed（防误杀合法预测）

llm_call 可注入（测试用 fake）；为 None 或调用异常时优雅降级为 REASONABLE，
绝不因判定器自身故障误杀论文。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReasonablenessVerdict:
    status: str            # REASONABLE | ON_CONCERN
    reasons: List[str] = field(default_factory=list)
    warning: bool = False  # True=仅标记，不拦 passed

    def to_dict(self) -> dict:
        return {"status": self.status, "reasons": self.reasons, "warning": self.warning}


class ModelReasonableness:
    """基于 LLM 的模型构建合理性判定。"""

    _SYSTEM_PROMPT = (
        "你是经济/金融建模评审专家。基于以下四项材料判定模型构建是否合理：\n"
        "① 论文建模章节 ② 模型代码 ③ 模型输出CSV ④ 观测真实值。\n"
        "评审依据学术标准：校准≠验证（匹配基年数据只算校准）；模型应做历史回测/"
        "样本外验证；参数应与已有研究对比；敏感性/稳健性；结论须自洽。\n"
        "只输出 JSON：{\"verdict\": \"REASONABLE\" 或 \"ON_CONCERN\", \"reasons\": [\"...\"]}\n"
        "注意：这是预警而非否决，模型预测类结论即使与观测略有偏差也不应直接否定。"
    )

    def __init__(self, llm_call: Optional[Callable[[List[dict]], Any]] = None):
        self.llm_call = llm_call

    async def judge(
        self,
        paper_modeling_section: str,
        model_code: str,
        model_output_csv: str,
        observed_values: dict,
    ) -> ReasonablenessVerdict:
        """综合四输入判定。llm_call 为 None 或异常 → 降级 REASONABLE。"""
        if self.llm_call is None:
            return ReasonablenessVerdict("REASONABLE", [], warning=False)

        user_prompt = (
            "① 论文建模章节：\n" + (paper_modeling_section or "(空)")[:3000]
            + "\n\n② 模型代码（前2000字符）：\n" + (model_code or "(空)")[:2000]
            + "\n\n③ 模型输出CSV（前2000字符）：\n" + (model_output_csv or "(空)")[:2000]
            + "\n\n④ 观测真实值：\n" + json.dumps(observed_values, ensure_ascii=False, default=str)[:2000]
            + "\n\n请给出模型合理性判定 JSON。"
        )
        try:
            resp = await self.llm_call(
                [
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ]
            )
            content = ""
            if isinstance(resp, dict):
                content = resp.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
            else:
                content = str(resp)
            payload = json.loads(content)
            status = str(payload.get("verdict", "REASONABLE")).upper()
            reasons = payload.get("reasons") or []
            if status == "ON_CONCERN":
                return ReasonablenessVerdict("ON_CONCERN", list(reasons), warning=True)
            return ReasonablenessVerdict("REASONABLE", list(reasons), warning=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"ModelReasonableness degraded to REASONABLE: {exc}")
            return ReasonablenessVerdict("REASONABLE", [], warning=False)