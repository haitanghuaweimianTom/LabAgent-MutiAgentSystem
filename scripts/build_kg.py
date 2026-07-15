"""KG Builder — 批量构建知识图谱

扫描 outputs 目录下的解析后论文 .md 文件，
通过 EntityExtractor 抽取实体，批量导入 Neo4j。
"""

import argparse
import json
import logging
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.services.kg_extractor import EntityExtractor
from app.core.neo4j_store import Neo4jStore

logger = logging.getLogger(__name__)


def scan_papers(input_dir: str = "outputs") -> List[Dict]:
    """扫描目录下的解析后论文 .md 文件。

    扫描路径:
    - {input_dir}/*/reading/*.md
    - {input_dir}/_global/global_references/*.md

    Returns:
        List[Dict]: 每个 dict 包含 file_path, project, content
    """
    papers = []
    base = Path(input_dir)

    if not base.exists():
        logger.warning(f"输入目录不存在: {input_dir}")
        return papers

    # 扫描各项目的 reading 目录
    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        reading_dir = project_dir / "reading"
        if reading_dir.exists():
            for md_file in reading_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8")
                    papers.append({
                        "file_path": str(md_file),
                        "project": project_dir.name,
                        "content": content,
                    })
                except Exception as e:
                    logger.warning(f"读取失败 {md_file}: {e}")

    # 扫描 _global/global_references
    global_refs = base / "_global" / "global_references"
    if global_refs.exists():
        for md_file in global_refs.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                papers.append({
                    "file_path": str(md_file),
                    "project": "_global",
                    "content": content,
                })
            except Exception as e:
                logger.warning(f"读取失败 {md_file}: {e}")

    logger.info(f"扫描到 {len(papers)} 篇论文")
    return papers


def import_to_neo4j(
    store: Neo4jStore,
    extraction_results: List[Dict],
    papers: List[Dict],
) -> Dict:
    """将抽取结果导入 Neo4j。

    Returns:
        Dict: 导入统计信息
    """
    stats = {"papers": 0, "nodes": 0, "relationships": 0, "errors": 0}

    for i, result in enumerate(extraction_results):
        paper_meta = papers[i] if i < len(papers) else {}
        project = paper_meta.get("project", "unknown")
        file_path = paper_meta.get("file_path", "unknown")

        # 创建 Paper 元数据节点
        paper_id = f"paper_{project}_{Path(file_path).stem}"
        try:
            store.upsert_node("Paper", {
                "id": paper_id,
                "title": Path(file_path).stem,
                "project": project,
                "source_file": file_path,
            })
            stats["papers"] += 1
        except Exception as e:
            logger.error(f"创建 Paper 节点失败 {file_path}: {e}")
            stats["errors"] += 1
            continue

        # 导入抽取的节点
        node_id_map = {}
        for node in result.get("nodes", []):
            try:
                label = node["label"]
                props = node["properties"]
                # 使用 paper 级唯一 ID
                original_id = props.get("id", "")
                unique_id = f"{paper_id}_{label}_{original_id}"
                props["id"] = unique_id
                store.upsert_node(label, props)
                node_id_map[original_id] = unique_id
                stats["nodes"] += 1
            except Exception as e:
                logger.warning(f"导入节点失败: {e}")
                stats["errors"] += 1

        # 导入抽取的关系
        for rel in result.get("relationships", []):
            try:
                from_id = node_id_map.get(rel["from_id"], rel["from_id"])
                to_id = node_id_map.get(rel["to_id"], rel["to_id"])
                store.create_relationship(
                    from_label=rel["from_label"],
                    from_id=from_id,
                    to_label=rel["to_label"],
                    to_id=to_id,
                    rel_type=rel["type"],
                )
                stats["relationships"] += 1
            except Exception as e:
                logger.warning(f"导入关系失败: {e}")
                stats["errors"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="批量构建知识图谱")
    parser.add_argument("--input-dir", default="outputs", help="论文输出目录 (默认: outputs)")
    parser.add_argument("--dry-run", action="store_true", help="仅扫描和抽取，不导入 Neo4j")
    parser.add_argument("--neo4j-uri", default=None, help="Neo4j 连接 URI (覆盖环境变量)")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细日志")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # 扫描论文
    papers = scan_papers(args.input_dir)
    if not papers:
        logger.info("未找到任何论文文件，退出。")
        return

    logger.info(f"发现 {len(papers)} 篇论文:")
    for p in papers:
        logger.info(f"  - [{p['project']}] {p['file_path']}")

    # 抽取实体
    extractor = EntityExtractor()
    contents = [p["content"] for p in papers]
    results = extractor.batch_extract(contents)

    total_nodes = sum(len(r.get("nodes", [])) for r in results)
    total_rels = sum(len(r.get("relationships", [])) for r in results)
    logger.info(f"抽取完成: {total_nodes} 个节点, {total_rels} 个关系")

    if args.dry_run:
        logger.info("Dry-run 模式，跳过 Neo4j 导入。")
        # 输出摘要
        for i, r in enumerate(results):
            paper = papers[i]
            logger.info(f"  [{paper['project']}] {paper['file_path']}: "
                        f"{len(r.get('nodes', []))} nodes, {len(r.get('relationships', []))} rels")
        return

    # 导入 Neo4j
    store_kwargs = {}
    if args.neo4j_uri:
        store_kwargs["uri"] = args.neo4j_uri

    store = Neo4jStore(**store_kwargs)
    if not store.connect():
        logger.error("Neo4j 连接失败，退出。")
        sys.exit(1)

    try:
        stats = import_to_neo4j(store, results, papers)
        logger.info(f"导入完成: {stats['papers']} 篇论文, "
                    f"{stats['nodes']} 个节点, {stats['relationships']} 个关系, "
                    f"{stats['errors']} 个错误")

        # 输出图谱统计
        graph_stats = store.get_stats()
        logger.info(f"图谱统计: {graph_stats}")
    finally:
        store.disconnect()


if __name__ == "__main__":
    main()
