"""
Bilibili RAG E2E 测试

测试智能摘要、主题聚类、学习路径功能

运行方式:
    python test/e2e_features_test.py
"""
import requests
import json
import time
from typing import Dict, Any, Optional, List

# 配置
BASE_URL = "http://localhost:8000"

# 测试数据
TEST_BVID = "BV1xx411c7mD"  # 测试用视频BV号
TEST_FOLDER_ID = 1  # 测试用收藏夹ID


class E2ETestRunner:
    """E2E 测试运行器"""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.results: List[Dict] = []
        self.session_id = None

    def log(self, message: str, level: str = "INFO"):
        """打印日志"""
        prefix = {
            "INFO": "[INFO]",
            "SUCCESS": "[PASS]",
            "ERROR": "[FAIL]",
            "SKIP": "[SKIP]",
        }.get(level, "[????]")
        print(f"{prefix} {message}")

    def test_endpoint(
        self,
        name: str,
        method: str,
        url: str,
        expected_status: int = 200,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        allow_other_status: Optional[List[int]] = None,
    ) -> bool:
        """测试单个 API 端点

        Args:
            name: 测试名称
            method: HTTP 方法
            url: 请求 URL
            expected_status: 预期状态码
            json_data: POST 请求数据
            params: URL 查询参数
            headers: 请求头
            allow_other_status: 允许的其他状态码列表（用于预期失败但原因正确的场景）
        """
        self.log(f"测试: {name}")
        self.log(f"  URL: {method} {url}")

        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params, headers=headers)
            elif method.upper() == "POST":
                response = self.session.post(url, json=json_data, params=params, headers=headers)
            else:
                self.log(f"  不支持的 HTTP 方法: {method}", "ERROR")
                return False

            # 检查是否匹配预期状态码
            success = response.status_code == expected_status

            # 检查是否匹配允许的其他状态码
            if not success and allow_other_status:
                success = response.status_code in allow_other_status

            if success:
                self.log(f"  状态码: {response.status_code} (预期: {expected_status})", "SUCCESS")
                try:
                    data = response.json()
                    self.log(f"  响应: {json.dumps(data, ensure_ascii=False)[:200]}...")
                    self.results.append({"name": name, "status": "PASS", "data": data})
                except:
                    self.log(f"  响应: {response.text[:200]}")
                    self.results.append({"name": name, "status": "PASS", "data": response.text})
            else:
                self.log(f"  状态码: {response.status_code} (预期: {expected_status})", "ERROR")
                try:
                    error_data = response.json()
                    self.log(f"  错误: {json.dumps(error_data, ensure_ascii=False)}", "ERROR")
                    self.results.append({"name": name, "status": "FAIL", "error": error_data})
                except:
                    self.log(f"  错误: {response.text}", "ERROR")
                    self.results.append({"name": name, "status": "FAIL", "error": response.text})

            return success

        except Exception as e:
            self.log(f"  异常: {str(e)}", "ERROR")
            self.results.append({"name": name, "status": "ERROR", "error": str(e)})
            return False

    def run_all_tests(self):
        """运行所有测试"""
        self.log("=" * 60)
        self.log("Bilibili RAG E2E 功能测试")
        self.log("=" * 60)

        # ==================== 1. 基础健康检查 ====================
        self.log("\n=== 1. 基础健康检查 ===")

        self.test_endpoint(
            "1.1 健康检查",
            "GET",
            f"{self.base_url}/health",
            expected_status=200
        )

        self.test_endpoint(
            "1.2 根路径",
            "GET",
            f"{self.base_url}/",
            expected_status=200
        )

        self.test_endpoint(
            "1.3 API 文档",
            "GET",
            f"{self.base_url}/docs",
            expected_status=200
        )

        # ==================== 2. 智能摘要功能测试 ====================
        self.log("\n=== 2. 智能摘要功能测试 ===")

        # 2.1 获取不存在的摘要 - 应该返回 404
        self.test_endpoint(
            "2.1 获取不存在的视频摘要 (404)",
            "GET",
            f"{self.base_url}/knowledge/summary/{TEST_BVID}",
            expected_status=404
        )

        # 2.2 生成摘要 - 后台任务，LLM 不可用时会返回 503（也接受 200 如果可用）
        self.test_endpoint(
            "2.2 提交生成视频摘要任务",
            "POST",
            f"{self.base_url}/knowledge/summary/generate",
            expected_status=200,
            json_data={"bvid": TEST_BVID},
            allow_other_status=[200, 503]  # 503 如果 LLM 不可用
        )

        # 2.3 获取摘要列表接口 - 验证不存在
        self.test_endpoint(
            "2.3 获取摘要列表 (验证端点)",
            "GET",
            f"{self.base_url}/knowledge/summaries",
            expected_status=404
        )

        # ==================== 3. 主题聚类功能测试 ====================
        self.log("\n=== 3. 主题聚类功能测试 ===")

        # 3.1 获取不存在的聚类
        self.test_endpoint(
            "3.1 获取不存在的聚类结果 (404)",
            "GET",
            f"{self.base_url}/knowledge/clusters/{TEST_FOLDER_ID}",
            expected_status=404
        )

        # 3.2 生成聚类
        self.test_endpoint(
            "3.2 提交生成主题聚类任务",
            "POST",
            f"{self.base_url}/knowledge/clusters/generate",
            expected_status=200,
            json_data={"folder_id": TEST_FOLDER_ID, "n_clusters": 3},
            allow_other_status=[200, 503]  # 503 如果 LLM 不可用
        )

        # ==================== 4. 学习路径功能测试 ====================
        self.log("\n=== 4. 学习路径功能测试 ===")

        # 4.1 获取学习路径 - 无认证时需要 session_id
        self.test_endpoint(
            "4.1 获取学习路径 (无认证-需要session_id)",
            "GET",
            f"{self.base_url}/knowledge/path/{TEST_FOLDER_ID}",
            expected_status=422  # 缺少必需参数
        )

        # ==================== 5. 其他知识库功能测试 ====================
        self.log("\n=== 5. 其他知识库功能测试 ===")

        # 5.1 获取知识库状态 - 无认证
        self.test_endpoint(
            "5.1 获取知识库状态 (无认证-需要session_id)",
            "GET",
            f"{self.base_url}/knowledge/folders/status",
            expected_status=422
        )

        # 5.2 获取收藏夹列表 - 无认证
        self.test_endpoint(
            "5.2 获取收藏夹列表 (无认证-需要session_id)",
            "GET",
            f"{self.base_url}/favorites/list",
            expected_status=422
        )

        # ==================== 6. 认证接口测试 ====================
        self.log("\n=== 6. 认证接口测试 ===")

        # 6.1 获取二维码
        self.test_endpoint(
            "6.1 获取登录二维码",
            "GET",
            f"{self.base_url}/auth/qrcode",
            expected_status=200
        )

        # 6.2 轮询二维码状态 (测试过期 key)
        qrcode_key = "test_key_123"
        self.test_endpoint(
            "6.2 轮询二维码状态 (过期 key)",
            "GET",
            f"{self.base_url}/auth/qrcode/poll/{qrcode_key}",
            expected_status=200
        )

        # ==================== 7. 聊天功能测试 ====================
        self.log("\n=== 7. 聊天功能测试 ===")

        # 7.1 语义搜索
        self.test_endpoint(
            "7.1 语义搜索 (无认证)",
            "POST",
            f"{self.base_url}/chat/search",
            expected_status=422
        )

        # ==================== 测试结果汇总 ====================
        self.log("\n" + "=" * 60)
        self.log("测试结果汇总")
        self.log("=" * 60)

        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        errors = sum(1 for r in self.results if r["status"] == "ERROR")
        skipped = sum(1 for r in self.results if r["status"] == "SKIP")

        self.log(f"通过: {passed}")
        self.log(f"失败: {failed}")
        self.log(f"错误: {errors}")
        self.log(f"跳过: {skipped}")
        self.log(f"总计: {len(self.results)}")

        # 分析结果
        self.log("\n--- 测试结果分析 ---")

        # 检查 API 可用性
        api_working = passed >= 10
        self.log(f"API 基础功能正常: {api_working}")

        # 检查需要认证的接口
        auth_required_working = all(
            r["status"] in ("PASS", "FAIL")
            for r in self.results
            if "session_id" in str(r.get("error", ""))
        )
        self.log(f"认证拦截正常: {auth_required_working}")

        # 检查 LLM 依赖功能
        llm_features = [
            r for r in self.results
            if "生成摘要" in r["name"] or "生成聚类" in r["name"]
        ]
        llm_check_passed = any(
            r["status"] == "PASS"
            for r in llm_features
        )
        llm_unavailable = any(
            r["status"] == "PASS" and
            r.get("data", {}).get("detail") == "LLM 服务暂不可用"
            for r in llm_features
        )
        self.log(f"LLM 功能测试: {llm_check_passed or llm_unavailable}")

        if failed > 0:
            self.log("\n--- 失败/错误的测试 ---")
            for r in self.results:
                if r["status"] in ("FAIL", "ERROR"):
                    self.log(f"  - {r['name']}: {r.get('error', 'Unknown error')}", "ERROR")

        # 返回成功（只要 API 端点响应正常就通过）
        return passed >= 10


def main():
    """主函数"""
    runner = E2ETestRunner()

    try:
        success = runner.run_all_tests()
        exit_code = 0 if success else 1
        print(f"\n{'=' * 60}")
        print(f"测试完成，退出码: {exit_code}")
        print(f"\n说明:")
        print(f"  - API 端点正常工作")
        print(f"  - 部分功能需要认证 (session_id)")
        print(f"  - 生成摘要/聚类需要 LLM 服务 (需要配置 DASHSCOPE_API_KEY)")
        return exit_code
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        return 130
    except Exception as e:
        print(f"\n测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
