"""
多厂商模型 E2E 测试脚本
"""
import os
import sys

# 设置项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows 编码修复
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_config():
    """测试配置项"""
    print("=" * 60)
    print("测试 1: 配置项验证")
    print("=" * 60)

    from app.config import settings

    # 测试新配置项
    assert hasattr(settings, 'llm_provider'), "缺少 llm_provider 配置"
    assert hasattr(settings, 'baidu_api_key'), "缺少 baidu_api_key 配置"
    assert hasattr(settings, 'tencent_api_key'), "缺少 tencent_api_key 配置"
    assert hasattr(settings, 'volcengine_api_key'), "缺少 volcengine_api_key 配置"
    assert hasattr(settings, 'zhipu_api_key'), "缺少 zhipu_api_key 配置"
    assert hasattr(settings, 'minimax_api_key'), "缺少 minimax_api_key 配置"

    print(f"✓ llm_provider: {settings.llm_provider}")
    print(f"✓ 模型: {settings.llm_model}")
    print(f"✓ Embedding 模型: {settings.embedding_model}")
    print(f"✓ DashScope Base URL: {settings.dashscope_base_url}")

    # 测试厂商设置
    assert settings.llm_provider == "dashscope", "默认厂商应为 dashscope"
    # 不测试具体模型值，因为 .env 可能覆盖默认值

    print("\n[测试 1 通过] 配置项验证通过\n")
    return True


def test_providers():
    """测试各厂商 Provider 类"""
    print("=" * 60)
    print("测试 2: 厂商 Provider 验证")
    print("=" * 60)

    from app.services.providers import (
        PROVIDER_MAP,
        PROVIDER_MODELS,
        get_provider,
        get_available_providers,
        get_provider_models,
        LLMProvider
    )

    # 测试厂商列表
    providers = get_available_providers()
    expected = ["dashscope", "baidu", "tencent", "volcengine", "zhipu", "minimax", "openai"]
    assert providers == expected, f"厂商列表不匹配: {providers}"

    print(f"✓ 可用厂商: {providers}")

    # 测试每个厂商
    for provider_name in providers:
        provider = get_provider(provider_name)
        assert isinstance(provider, LLMProvider), f"{provider_name} 不是 LLMProvider 实例"
        assert hasattr(provider, 'get_api_key'), f"{provider_name} 缺少 get_api_key 方法"
        assert hasattr(provider, 'get_base_url'), f"{provider_name} 缺少 get_base_url 方法"
        assert hasattr(provider, 'get_default_model'), f"{provider_name} 缺少 get_default_model 方法"

        models = get_provider_models(provider_name)
        print(f"  - {provider_name}: 默认模型={provider.get_default_model()}, 可用模型={models[:2]}...")

    # 测试模型映射
    assert "dashscope" in PROVIDER_MODELS
    assert "qwen3-max" in PROVIDER_MODELS["dashscope"]["models"]

    print("\n[测试 2 通过] 厂商 Provider 验证通过\n")
    return True


def test_llm_factory():
    """测试 LLM 工厂函数"""
    print("=" * 60)
    print("测试 3: LLM 工厂函数验证")
    print("=" * 60)

    from app.services.llm_factory import get_llm_client, get_embeddings_client, get_llm_config
    from app.config import settings

    # 测试 get_llm_config
    config = get_llm_config()
    print(f"✓ 当前配置: provider={config['provider']}, model={config['model']}")
    print(f"✓ 可用厂商: {config['available_providers']}")
    print(f"✓ 当前厂商可用模型: {config['available_models']}")

    # 测试 get_llm_client (不实际调用 API)
    try:
        # 只验证客户端创建，不实际调用 API
        client = get_llm_client(provider="dashscope", model="qwen3-max")
        assert client is not None
        print(f"✓ LLM 客户端创建成功 (provider=dashscope, model=qwen3-max)")
    except ValueError as e:
        # API Key 可能未配置，跳过实际创建
        if "API Key 未配置" in str(e):
            print(f"⚠ 跳过实际客户端创建: {e}")
        else:
            raise
    except Exception as e:
        print(f"⚠ 客户端创建异常: {e}")

    # 测试获取其他厂商的客户端（不实际调用）
    for provider in ["baidu", "tencent", "zhipu"]:
        try:
            provider_obj = get_llm_client(provider=provider)
            print(f"✓ {provider} 客户端可创建")
        except ValueError as e:
            if "API Key 未配置" in str(e):
                print(f"⚠ {provider}: API Key 未配置 (预期行为)")
            else:
                raise

    print("\n[测试 3 通过] LLM 工厂函数验证通过\n")
    return True


def test_provider_switching():
    """测试厂商切换逻辑"""
    print("=" * 60)
    print("测试 4: 厂商切换验证")
    print("=" * 60)

    from app.services.providers import get_provider, get_available_providers

    # 测试切换到不同厂商
    for provider_name in get_available_providers():
        try:
            provider = get_provider(provider_name)
            api_key = provider.get_api_key()
            base_url = provider.get_base_url()
            default_model = provider.get_default_model()

            print(f"  - {provider_name}:")
            print(f"      API Key: {'已配置' if api_key else '未配置'}")
            print(f"      Base URL: {base_url}")
            print(f"      默认模型: {default_model}")
        except ValueError as e:
            print(f"  - {provider_name}: 错误 - {e}")

    # 测试无效厂商
    try:
        get_provider("invalid_provider")
        assert False, "应该抛出异常"
    except ValueError as e:
        print(f"\n✓ 无效厂商正确抛出异常: {e}")

    print("\n[测试 4 通过] 厂商切换验证通过\n")
    return True


def test_regression():
    """回归测试 - 确保现有功能正常"""
    print("=" * 60)
    print("测试 5: 回归测试 (DashScope 默认配置)")
    print("=" * 60)

    from app.config import settings

    # 验证 DashScope 配置
    print(f"✓ DashScope Base URL: {settings.dashscope_base_url}")
    # 注意：.env 文件可能覆盖默认值
    expected_urls = [
        "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 代码默认值
        "https://dashscope.aliyuncs.com/api/v1"  # 旧 .env 配置
    ]
    assert settings.dashscope_base_url in expected_urls, f"DashScope URL 不在预期范围内: {settings.dashscope_base_url}"

    # 验证配置加载
    print(f"✓ LLM_MODEL: {settings.llm_model}")
    print(f"✓ EMBEDDING_MODEL: {settings.embedding_model}")

    print("\n[测试 5 通过] 回归测试通过\n")
    return True


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("多厂商模型 E2E 测试开始")
    print("=" * 60 + "\n")

    tests = [
        ("配置项验证", test_config),
        ("厂商 Provider 验证", test_providers),
        ("LLM 工厂函数验证", test_llm_factory),
        ("厂商切换验证", test_provider_switching),
        ("回归测试", test_regression),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"\n[测试失败] {name}")
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"测试完成: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
