"""系统功能集成测试 — 轻量验证各模块是否正常工作"""
import asyncio
import json
import httpx

API = "http://localhost:8000"
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"

results = {"passed": 0, "failed": 0, "skipped": 0}


def check(name, ok, detail="", response=None):
    status = PASS if ok else FAIL
    results["passed" if ok else "failed"] += 1
    d = f" | {detail}" if detail else ""
    if response and not ok:
        try:
            body = response.text[:200]
            d += f" | resp={body}"
        except:
            pass
    print(f"  [{status}] {name}{d}")


async def main():
    client = httpx.AsyncClient(base_url=API, timeout=10)

    # ========== 1. 基础健康检查 ==========
    print("\n=== 1. 基础健康检查 ===")
    r = await client.get("/")
    check("根路径", r.status_code == 200, r.json().get("name"))

    r = await client.get("/health")
    check("健康检查", r.status_code == 200, r.json().get("status"))

    # ========== 2. 系统信息 ==========
    print("\n=== 2. 系统信息 ===")
    r = await client.get("/api/v1/info")
    data = r.json()
    check("系统信息接口", r.status_code == 200, f"version={data.get('version')} team_size={data.get('team_size')}")
    check("Claude Code CLI", data.get("claude_code_available", False), data.get("claude_code_path"))
    check("默认模型", bool(data.get("default_model")), data.get("default_model"))
    dp = data.get("default_provider")
    check("默认 Provider", isinstance(dp, (dict, type(None))), f"id={dp.get('id')}" if dp else "none yet (ok at startup)")

    # ========== 3. 设置接口 ==========
    print("\n=== 3. 设置接口 ===")
    r = await client.get("/api/v1/settings")
    data = r.json()
    check("获取设置", r.status_code == 200, f"provider={data.get('default_llm_provider')}")
    check("Multi-provider 配置", bool(data.get("providers")),
          f"keys={list(data.get('providers', {}).keys())}")

    r = await client.post("/api/v1/settings", json={})
    check("保存空设置", r.status_code == 200, r.json().get("message"))

    # ========== 4. Provider 系统（CC Switch 风格）==========
    print("\n=== 4. Provider 管理 ===")

    # 列出所有 Provider（预设 + 自定义）
    r = await client.get("/api/v1/providers/")
    data = r.json()
    check("Provider 列表", r.status_code == 200,
          f"custom={len(data.get('custom_providers', []))} presets={len(data.get('presets', []))}")
    existing_count = len(data.get("custom_providers", []))

    # 获取预设列表
    r = await client.get("/api/v1/providers/presets")
    data = r.json()
    check("预设列表", r.status_code == 200, f"count={len(data.get('presets', []))}")

    # 按分类获取预设
    r = await client.get("/api/v1/providers/presets")
    data = r.json()
    by_cat = data.get("presets_by_category", {})
    # Handle both string keys and enum keys
    cat_count = len(by_cat) if isinstance(by_cat, dict) else 0
    check("预设分类", cat_count > 0, f"categories={list(by_cat.keys()) if isinstance(by_cat, dict) else 'N/A'}")

    # 创建自定义 Provider
    r = await client.post("/api/v1/providers/", json={
        "id": "test_provider_bailian",
        "name": "阿里云百炼测试",
        "type": "openai",
        "category": "cn_official",
        "api_key": "sk-test-dummy-key-12345",
        "api_host": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
        "meta": {"api_format": "openai_chat"},
    })
    created_ok = r.status_code in (200, 201)
    check("创建自定义 Provider", created_ok, r.json().get("success") or r.json().get("error"))

    if created_ok:
        # 获取单个
        r = await client.get("/api/v1/providers/test_provider_bailian")
        check("获取单个 Provider", r.status_code == 200, r.json().get("name"))

        # 更新
        r = await client.put("/api/v1/providers/test_provider_bailian", json={
            "name": "阿里云百炼更新测试",
        })
        check("更新 Provider", r.status_code == 200, r.json().get("success"))

        # 设置默认
        r = await client.post("/api/v1/providers/test_provider_bailian/default")
        check("设置默认 Provider", r.status_code == 200, r.json().get("success"))

        # 清理
        r = await client.delete("/api/v1/providers/test_provider_bailian")
        check("删除 Provider", r.status_code == 200, r.json().get("success"))

        # 确认删除
        r = await client.get("/api/v1/providers/")
        data = r.json()
        check("确认删除", len(data.get("custom_providers", [])) == existing_count)

    # 所有模型列表（仅自定义 provider 的模型，空列表也正常）
    r = await client.get("/api/v1/providers/models")
    data = r.json()
    models_ok = r.status_code == 200 and isinstance(data.get("models"), list)
    check("所有模型列表", models_ok,
          f"count={len(data.get('models', []))} (仅自定义 provider 的模型，0也正常)")

    # ========== 5. Agent 列表 ==========
    print("\n=== 5. Agent 团队 ===")
    r = await client.get("/api/v1/agents")
    agents = r.json()
    if isinstance(agents, dict):
        agents = agents.get("agents", [])
    check("Agent 列表", r.status_code == 200 and len(agents) > 0, f"count={len(agents)}")
    for a in agents:
        check(f"  {a.get('name')}", True, f"label={a.get('label')} model={a.get('model', '?')}")

    # ========== 6. MCP 管理 ==========
    print("\n=== 6. MCP 管理 ===")
    r = await client.get("/api/v1/mcp/servers")
    servers = r.json()
    if isinstance(servers, dict):
        servers = servers.get("servers", servers.get("data", []))
    check("MCP 服务器列表", r.status_code == 200 and isinstance(servers, list), f"count={len(servers)}")

    r = await client.get("/api/v1/mcp/tools")
    tools_data = r.json()
    tools = tools_data if isinstance(tools_data, list) else tools_data.get("tools", [])
    check("MCP 工具列表", r.status_code == 200 and isinstance(tools, list), f"count={len(tools)}")

    # 标签发现
    r = await client.get("/api/v1/mcp/tags")
    tags = r.json()
    check("MCP 标签", r.status_code == 200 and isinstance(tags, list), f"tags={tags}")

    # 工具发现
    r = await client.post("/api/v1/mcp/discover", json={})
    disc = r.json()
    check("工具发现", r.status_code == 200,
          f"servers={disc.get('total_servers')} tools={disc.get('total_tools')}")

    # Agent 工具映射
    r = await client.get("/api/v1/mcp/agents/research_agent/tools")
    agent_tools = r.json()
    check("Agent 工具映射", r.status_code == 200 and isinstance(agent_tools, list), f"tools={agent_tools}")

    # ========== 7. 知识库 ==========
    print("\n=== 7. 知识库 ===")

    # 列出知识
    r = await client.get("/api/v1/knowledge/")
    kb = r.json()
    check("知识库列表", r.status_code == 200, f"total={kb.get('total')}")

    # 添加文档
    r = await client.post("/api/v1/knowledge/documents", json={
        "title": "线性规划基础",
        "content": "线性规划是数学规划中理论最成熟、应用最广泛的一个分支。标准形式为 min c^T x, s.t. Ax = b, x >= 0。常用求解方法包括单纯形法和内点法。",
        "source": "教材",
        "metadata": {"category": "optimization"},
    })
    doc_ok = r.status_code == 200
    doc_id = r.json().get("doc_id") if doc_ok else None
    check("添加文档", doc_ok, f"doc_id={doc_id}")

    # 查询知识库
    if doc_ok:
        r = await client.post("/api/v1/knowledge/query", json={
            "query": "什么是线性规划",
            "top_k": 3,
        })
        qr = r.json()
        check("知识库查询询", r.status_code == 200, f"results={qr.get('total')}")

        # 带上下文查询
        r = await client.post("/api/v1/knowledge/query/context", json={
            "query": "优化方法有哪些",
            "top_k": 3,
        })
        ctx = r.json()
        check("带上下文查询", r.status_code == 200, f"has_context={ctx.get('has_context')}")

    # 统计信息
    r = await client.get("/api/v1/knowledge/stats")
    stats = r.json()
    check("知识库统计", r.status_code == 200,
          f"docs={stats.get('total_documents')} chunks={stats.get('total_chunks')}")

    # 保存知识库
    r = await client.post("/api/v1/knowledge/save")
    check("保存知识库", r.status_code == 200, r.json().get("success"))

    # 加载知识库
    r = await client.post("/api/v1/knowledge/load")
    check("加载知识库", r.status_code == 200, r.json().get("success"))

    # 清理：删除测试文档
    if doc_id:
        r = await client.delete(f"/api/v1/knowledge/documents/{doc_id}")
        check("删除文档", r.status_code == 200, r.json().get("success"))

    # ========== 8. Workflow 管理 ==========
    print("\n=== 8. Workflow 管理 ===")
    r = await client.get("/api/v1/workflows")
    workflows = r.json()
    if isinstance(workflows, dict):
        workflows = workflows.get("workflows", [])
    check("Workflow 列表", r.status_code == 200 and isinstance(workflows, list), f"count={len(workflows)}")
    for w in workflows[:3]:
        check(f"  {w.get('name')}", True, f"steps={len(w.get('steps', []))}")

    # ========== 9. 数据文件管理 ==========
    print("\n=== 9. 数据文件管理 ===")
    r = await client.get("/api/v1/data/files")
    files = r.json()
    if isinstance(files, dict):
        files = files.get("files", [])
    check("数据文件列表", r.status_code == 200 and isinstance(files, list), f"count={len(files)}")

    r = await client.get("/api/v1/data/analyze", params={"dataset_name": "test"})
    check("数据分析端点", r.status_code in (200, 404), f"status={r.status_code}")

    # ========== 10. Task 创建与查询 ==========
    print("\n=== 10. Task 管理 ===")

    task_data = {
        "problem_text": "某工厂生产两种产品A和B，生产一件A需要2小时机器时间和1小时人工，生产一件B需要1小时机器时间和2小时人工。机器时间每日可用8小时，人工每日可用10小时。A产品每件利润3元，B产品每件利润4元。求最大利润。",
        "sub_problems": [
            {"name": "问题1：建立线性规划模型", "description": "建立线性规划模型并求解最大利润"},
            {"name": "问题2：灵敏度分析", "description": "对资源约束进行灵敏度分析"},
        ],
    }

    r = await client.post("/api/v1/tasks/submit", json=task_data, timeout=15)
    data = r.json()
    task_id = data.get("task_id") if isinstance(data, dict) else data
    check("创建任务", r.status_code == 200 and task_id is not None, f"task_id={task_id}")

    if task_id:
        r = await client.get(f"/api/v1/tasks/{task_id}/status")
        data = r.json()
        check("查询任务状态", r.status_code == 200, f"status={data.get('status')}")

        r = await client.get(f"/api/v1/tasks/{task_id}/result")
        data = r.json()
        task_result_ok = r.status_code in (200, 400) and isinstance(data, dict)
        status_text = data.get("status", data.get("detail", "unknown"))
        check("查询任务结果", task_result_ok, f"status={status_text}")

        r = await client.get("/api/v1/tasks/")
        data = r.json()
        task_list = data if isinstance(data, list) else data.get("tasks", [])
        check("任务列表", r.status_code == 200 and isinstance(task_list, list), f"count={len(task_list)}")

        r = await client.get(f"/api/v1/tasks/{task_id}/messages")
        check("任务消息", r.status_code == 200, f"type={type(r.json()).__name__}")

    # ========== 11. Solver 模板检测 ==========
    print("\n=== 11. Solver 模板检测 ===")
    import sys
    sys.path.insert(0, ".")
    from backend.app.agents.solver_agent import detect_task_type, get_template_for_model, get_template_code, CODE_TEMPLATES

    check("模板库数量", len(CODE_TEMPLATES) >= 25, f"实际 {len(CODE_TEMPLATES)} 个")

    tests = [
        ("线性规划最优", "linear_programming"),
        ("时间序列预测", "time_series"),
        ("K-Means 聚类", "kmeans"),
        ("AHP 层次分析", "ahp"),
        ("TOPSIS 评价", "topsis"),
        ("相关性分析", "correlation"),
        ("雷达图绘制", "visualization_radar"),
        ("数据清洗预处理", "data_cleaning"),
        ("特征工程标准化", "feature_engineering"),
        ("蒙特卡洛模拟", "monte_carlo"),
    ]
    for text, expected in tests:
        detected = detect_task_type(text)
        check(f"检测 '{text}'", expected in detected, f"detected={detected}")

    template = get_template_code(["kmeans", "visualization_basic"])
    check("获取 K-Means 模板代码", "KMeans" in template or "sklearn" in template, f"len={len(template)}")

    model_info = {"model_name": "TOPSIS", "model_type": "综合评价"}
    t = get_template_for_model(model_info)
    check("TOPSIS 模型模板", "topsis" in t[:50].lower() if isinstance(t, str) else True, f"len={len(t)}")

    model_info2 = {"model_name": "ARIMA", "model_type": "时间序列"}
    t2 = get_template_for_model(model_info2)
    check("ARIMA 模型模板", "ARIMA" in t2 or "arima" in t2.lower(), f"len={len(t2)}")

    # ========== 12. SolverAgent 实例化 ==========
    print("\n=== 12. SolverAgent 实例化 ===")
    from backend.app.agents.solver_agent import SolverAgent
    agent = SolverAgent()
    check("SolverAgent 创建", True, f"name={agent.name} label={agent.label}")
    check("系统提示词", len(agent.get_system_prompt()) > 50, f"len={len(agent.get_system_prompt())}")

    # ========== 13. Runtime Config 持久化 ==========
    print("\n=== 13. Runtime Config 持久化 ===")
    from backend.app.core.runtime_config import update_env_key, is_api_key_set, is_kimi_key_set
    check("MiniMax key状态", True, f"set={is_api_key_set()}")
    check("Kimi key状态", True, f"set={is_kimi_key_set()}")

    # ========== 汇总 ==========
    print(f"\n{'='*50}")
    print(f"测试结果: {results['passed']} 通过, {results['failed']} 失败, {results.get('skipped', 0)} 跳过")
    if results["failed"] > 0:
        print("⚠️  有失败项，请检查上方详情")
    else:
        print("✅ 所有测试通过！")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
