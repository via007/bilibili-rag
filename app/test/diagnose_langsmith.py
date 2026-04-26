"""LangSmith 追踪诊断脚本

运行方式:
    python app/test/diagnose_langsmith.py

诊断内容:
    1. langsmith 包是否安装
    2. 环境变量是否正确设置
    3. 能否创建测试 trace
    4. LangChain / LangGraph 调用是否能被追踪
"""
import os
import sys

print("=" * 60)
print("LangSmith 追踪诊断")
print("=" * 60)

# 1. 检查 langsmith 包
print("\n[1/5] 检查 langsmith 包...")
try:
    import langsmith
    print(f"  ✅ langsmith 已安装 (版本: {langsmith.__version__})")
except ImportError:
    print("  ❌ langsmith 未安装! 请运行: pip install langsmith")
    sys.exit(1)

# 2. 检查环境变量
print("\n[2/5] 检查环境变量...")
tracing_v2 = os.environ.get("LANGCHAIN_TRACING_V2", "")
langsmith_tracing = os.environ.get("LANGSMITH_TRACING", "")
api_key = os.environ.get("LANGSMITH_API_KEY", "")
project = os.environ.get("LANGSMITH_PROJECT", "default")

print(f"  LANGCHAIN_TRACING_V2 = {repr(tracing_v2)}")
print(f"  LANGSMITH_TRACING    = {repr(langsmith_tracing)}")
print(f"  LANGSMITH_API_KEY    = {repr(api_key[:10] + '...' if api_key else '')}")
print(f"  LANGSMITH_PROJECT    = {repr(project)}")

if not api_key:
    print("  ❌ LANGSMITH_API_KEY 未设置!")
    sys.exit(1)

if tracing_v2.lower() != "true" and langsmith_tracing.lower() != "true":
    print("  ❌ 追踪未启用! 请设置 LANGCHAIN_TRACING_V2=true 或 LANGSMITH_TRACING=true")
    sys.exit(1)

print("  ✅ 环境变量配置正确")

# 3. 测试 Client 连接
print("\n[3/5] 测试 LangSmith Client 连接...")
try:
    from langsmith import Client
    client = Client()
    # 尝试列出项目来验证 API key
    projects = list(client.list_projects())
    print(f"  ✅ Client 连接成功 (找到 {len(projects)} 个项目)")
except Exception as e:
    print(f"  ❌ Client 连接失败: {e}")
    sys.exit(1)

# 4. 测试手动 trace
print("\n[4/5] 测试手动创建 trace...")
try:
    run = client.create_run(
        name="diagnose_test",
        run_type="chain",
        inputs={"test": True},
        project_name=project,
    )
    client.update_run(run.id, outputs={"status": "ok"})
    print(f"  ✅ 手动 trace 创建成功 (run_id: {run.id})")
    print(f"     请在 https://smith.langchain.com 查看项目 '{project}'")
except Exception as e:
    print(f"  ❌ 手动 trace 创建失败: {e}")

# 5. 测试 LangChain 自动追踪
print("\n[5/5] 测试 LangChain 自动追踪...")
try:
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    # 这个调用应该自动被 LangSmith 追踪
    response = llm.invoke([HumanMessage(content="Say 'LangSmith tracing works!'")])
    print(f"  ✅ LangChain 调用成功")
    print(f"     响应: {response.content[:50]}...")
    print(f"     请检查 LangSmith 平台是否有新 trace")
except Exception as e:
    print(f"  ⚠️  LangChain 调用失败 (但追踪应该已记录): {e}")
    print(f"     请检查 LangSmith 平台是否有带错误的 trace")

print("\n" + "=" * 60)
print("诊断完成!")
print("=" * 60)
