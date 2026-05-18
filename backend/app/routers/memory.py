"""记忆系统 RESTful API

提供：
- 查询历史经验教训（Lessons Learned）
- 查看任务记忆（Working + Episodic）
- 管理记忆（添加/删除/清空经验）
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.memory import get_memory_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/memory", tags=["记忆系统"])


# ===== Pydantic 请求模型 =====

class AddLessonRequest(BaseModel):
    category: str
    content: str
    problem_type: str = ""
    method: str = ""
    success: bool = True


class QueryLessonsRequest(BaseModel):
    problem_type: str = ""
    category: str = ""
    top_k: int = 10


class DeleteLessonRequest(BaseModel):
    lesson_id: str


# ===== API 端点 =====

@router.get("/lessons")
def list_lessons(problem_type: str = "", category: str = "", top_k: int = 20):
    """查询历史经验教训"""
    mm = get_memory_manager()
    lessons = mm.get_lessons().query(problem_type=problem_type, category=category, top_k=top_k)
    return {
        "lessons": lessons,
        "total": len(lessons),
        "all_count": len(mm.get_lessons().lessons),
    }


@router.get("/lessons/text")
def get_lessons_text(problem_type: str = "", top_k: int = 5):
    """获取格式化的经验上下文（用于注入 Agent prompt）"""
    mm = get_memory_manager()
    text = mm.get_lessons().get_context_text(problem_type=problem_type, top_k=top_k)
    return {"context": text}


@router.post("/lessons")
def add_lesson(req: AddLessonRequest):
    """手动添加经验教训"""
    mm = get_memory_manager()
    mm.get_lessons().add_lesson(
        category=req.category,
        content=req.content,
        problem_type=req.problem_type,
        method=req.method,
        success=req.success,
        source_task="manual",
    )
    mm.save_lessons()
    return {"status": "ok", "message": "经验已添加"}


@router.delete("/lessons")
def delete_lesson(req: DeleteLessonRequest):
    """删除指定经验教训"""
    mm = get_memory_manager()
    lessons = mm.get_lessons()
    original = len(lessons.lessons)
    lessons.lessons = [l for l in lessons.lessons if l["id"] != req.lesson_id]
    if len(lessons.lessons) == original:
        raise HTTPException(status_code=404, detail=f"经验 {req.lesson_id} 不存在")
    lessons.save()
    return {"status": "ok", "message": "经验已删除"}


@router.post("/lessons/clear")
def clear_lessons():
    """清空所有经验教训"""
    mm = get_memory_manager()
    count = len(mm.get_lessons().lessons)
    mm.get_lessons().lessons = []
    mm.save_lessons()
    return {"status": "ok", "message": f"已清空 {count} 条经验"}


@router.get("/task/{task_id}")
def get_task_memory(task_id: str):
    """获取指定任务的记忆（Working + Episodic）"""
    mm = get_memory_manager()

    # 尝试从磁盘加载
    if not mm.get_working(task_id):
        if not mm.load_task_memory(task_id):
            raise HTTPException(status_code=404, detail=f"任务 {task_id} 的记忆不存在")

    wm = mm.get_working(task_id)
    em = mm.get_episodic(task_id)

    return {
        "task_id": task_id,
        "working_memory": wm.to_dict() if wm else None,
        "episodic_memory": {
            "summary": em.summary if em else "",
            "entry_count": len(em.entries) if em else 0,
            "recent": em.get_recent(10) if em else [],
        },
    }


@router.get("/stats")
def get_memory_stats():
    """获取记忆系统统计信息"""
    mm = get_memory_manager()
    lessons = mm.get_lessons()

    # 按类别统计
    category_counts: Dict[str, int] = {}
    for l in lessons.lessons:
        cat = l.get("category", "unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # 按问题类型统计
    problem_type_counts: Dict[str, int] = {}
    for l in lessons.lessons:
        pt = l.get("problem_type", "unknown")
        if pt:
            problem_type_counts[pt] = problem_type_counts.get(pt, 0) + 1

    return {
        "total_lessons": len(lessons.lessons),
        "by_category": category_counts,
        "by_problem_type": problem_type_counts,
        "active_task_memories": len(mm._working),
    }
