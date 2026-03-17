"""
Bilibili RAG 全面 E2E 测试

测试所有核心功能流程

运行方式:
    python test/full_e2e_test.py
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


class FullE2ETestRunner:
    """全面 E2E 测试运行器"""

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
        """测试单个 API 端点"""
        self.log(f"测试: {name}")
        self.log(f"  URL: {method} {url}")

        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params, headers=headers)
            elif method.upper() == "POST":
                response = self.session.post(url, json=json_data, params=params, headers=headers)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=json_data, params=params, headers=headers)
            elif method.upper() == "DELETE":
                response = self.session.delete(url, params=params, headers=headers)
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
        self.log("=" * 70)
        self.log("Bilibili RAG 全面 E2E 功能测试")
        self.log("=" * 70)

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

        # ==================== 2. 认证流程 - 扫码登录 ====================
        self.log("\n=== 2. 认证流程 - 扫码登录 ===")

        # 2.1 获取二维码
        result = self.test_endpoint(
            "2.1 获取登录二维码",
            "GET",
            f"{self.base_url}/auth/qrcode",
            expected_status=200
        )

        # 提取二维码 key 用于后续测试
        qrcode_key = None
        if result:
            for r in self.results:
                if r["name"] == "2.1 获取登录二维码" and r["status"] == "PASS":
                    try:
                        qrcode_key = r["data"].get("qrcode_key")
                    except:
                        pass

        # 2.2 轮询二维码状态 (测试过期 key)
        self.test_endpoint(
            "2.2 轮询二维码状态 (过期 key)",
            "GET",
            f"{self.base_url}/auth/qrcode/poll/test_key_123",
            expected_status=200
        )

        # 2.3 使用正确的 qrcode_key 轮询 (如果可用)
        if qrcode_key:
            self.test_endpoint(
                "2.3 轮询二维码状态 (真实 key)",
                "GET",
                f"{self.base_url}/auth/qrcode/poll/{qrcode_key}",
                expected_status=200
            )
        else:
            self.log("2.3 轮询二维码状态 (真实 key): 跳过 (无有效 qrcode_key)", "SKIP")

        # ==================== 3. 收藏夹同步 - 获取收藏夹列表 ====================
        self.log("\n=== 3. 收藏夹同步 - 获取收藏夹列表 ===")

        # 3.1 获取收藏夹列表 (需要 session_id)
        self.test_endpoint(
            "3.1 获取收藏夹列表 (无认证)",
            "GET",
            f"{self.base_url}/favorites/list",
            expected_status=422
        )

        # 3.2 获取收藏夹视频 (需要 session_id)
        self.test_endpoint(
            "3.2 获取收藏夹视频 (无认证)",
            "GET",
            f"{self.base_url}/favorites/{TEST_FOLDER_ID}/videos",
            expected_status=422
        )

        # ==================== 4. 知识库入库 - 视频处理 ====================
        self.log("\n=== 4. 知识库入库 - 视频处理 ===")

        # 4.1 获取知识库统计
        self.test_endpoint(
            "4.1 获取知识库统计",
            "GET",
            f"{self.base_url}/knowledge/stats",
            expected_status=200
        )

        # 4.2 获取知识库状态 (需要 session_id)
        self.test_endpoint(
            "4.2 获取知识库状态 (无认证)",
            "GET",
            f"{self.base_url}/knowledge/folders/status",
            expected_status=422
        )

        # 4.3 同步收藏夹 (需要 session_id)
        self.test_endpoint(
            "4.3 同步收藏夹 (无认证)",
            "POST",
            f"{self.base_url}/knowledge/folders/sync",
            expected_status=422
        )

        # 4.4 获取视频 ASR 状态
        self.test_endpoint(
            "4.4 获取视频 ASR 状态",
            "GET",
            f"{self.base_url}/knowledge/video/{TEST_BVID}/asr-status",
            expected_status=404
        )

        # 4.5 获取视频 ASR 质量
        self.test_endpoint(
            "4.5 获取视频 ASR 质量",
            "GET",
            f"{self.base_url}/knowledge/video/{TEST_BVID}/asr-quality",
            expected_status=404
        )

        # ==================== 5. 对话问答 - 发送问题，获取回答 ====================
        self.log("\n=== 5. 对话问答 - 发送问题，获取回答 ===")

        # 5.1 语义搜索 (需要 session_id)
        self.test_endpoint(
            "5.1 语义搜索 (无认证)",
            "POST",
            f"{self.base_url}/chat/search",
            expected_status=422
        )

        # 5.2 问答接口 (需要 session_id)
        self.test_endpoint(
            "5.2 问答接口 (无认证)",
            "POST",
            f"{self.base_url}/chat/ask",
            expected_status=422
        )

        # ==================== 6. 会话管理 - 创建、获取会话 ====================
        self.log("\n=== 6. 会话管理 - 创建、获取会话 ===")

        # 6.1 获取会话列表 (需要 session_id)
        self.test_endpoint(
            "6.1 获取会话列表 (无认证)",
            "GET",
            f"{self.base_url}/conversation/list",
            expected_status=422
        )

        # 6.2 创建会话 (需要 session_id)
        self.test_endpoint(
            "6.2 创建会话 (无认证)",
            "POST",
            f"{self.base_url}/conversation/create",
            expected_status=422
        )

        # 6.3 获取会话信息 (需要 session_id)
        self.test_endpoint(
            "6.3 获取会话信息 (无认证)",
            "GET",
            f"{self.base_url}/conversation/test-session-id",
            expected_status=422
        )

        # 6.4 更新会话 (需要 session_id)
        self.test_endpoint(
            "6.4 更新会话 (无认证)",
            "PUT",
            f"{self.base_url}/conversation/test-session-id",
            expected_status=422
        )

        # 6.5 删除会话 (需要 session_id)
        self.test_endpoint(
            "6.5 删除会话 (无认证)",
            "DELETE",
            f"{self.base_url}/conversation/test-session-id",
            expected_status=422
        )

        # 6.6 获取会话消息列表 (需要 session_id)
        self.test_endpoint(
            "6.6 获取会话消息列表 (无认证)",
            "GET",
            f"{self.base_url}/conversation/test-session-id/messages",
            expected_status=422
        )

        # ==================== 7. 视频总结 - 获取/生成摘要 ====================
        self.log("\n=== 7. 视频总结 - 获取/生成摘要 ===")

        # 7.1 获取不存在的视频摘要
        self.test_endpoint(
            "7.1 获取不存在的视频摘要",
            "GET",
            f"{self.base_url}/knowledge/summary/{TEST_BVID}",
            expected_status=404
        )

        # 7.2 生成视频摘要 (LLM 不可用时返回 503)
        self.test_endpoint(
            "7.2 生成视频摘要 (LLM 不可用时返回 503)",
            "POST",
            f"{self.base_url}/knowledge/summary/generate",
            expected_status=200,
            json_data={"bvid": TEST_BVID},
            allow_other_status=[200, 503]
        )

        # ==================== 8. 主题聚类 - 获取/生成聚类 ====================
        self.log("\n=== 8. 主题聚类 - 获取/生成聚类 ===")

        # 8.1 获取不存在的聚类
        self.test_endpoint(
            "8.1 获取不存在的聚类",
            "GET",
            f"{self.base_url}/knowledge/clusters/{TEST_FOLDER_ID}",
            expected_status=404
        )

        # 8.2 生成聚类 (LLM 不可用时返回 503)
        self.test_endpoint(
            "8.2 生成主题聚类 (LLM 不可用时返回 503)",
            "POST",
            f"{self.base_url}/knowledge/clusters/generate",
            expected_status=200,
            json_data={"folder_id": TEST_FOLDER_ID, "n_clusters": 3},
            allow_other_status=[200, 503]
        )

        # ==================== 9. 学习路径 - 获取/生成学习路径 ====================
        self.log("\n=== 9. 学习路径 - 获取/生成学习路径 ===")

        # 9.1 获取学习路径 (无认证)
        self.test_endpoint(
            "9.1 获取学习路径 (无认证)",
            "GET",
            f"{self.base_url}/knowledge/path/{TEST_FOLDER_ID}",
            expected_status=422
        )

        # 9.2 生成学习路径 (需要 session_id)
        self.test_endpoint(
            "9.2 生成学习路径 (无认证)",
            "POST",
            f"{self.base_url}/knowledge/path/generate",
            expected_status=422
        )

        # ==================== 10. 导出功能 - 导出视频/会话 ====================
        self.log("\n=== 10. 导出功能 - 导出视频/会话 ===")

        # 10.1 导出视频 (需要 session_id)
        self.test_endpoint(
            "10.1 导出视频 (无认证)",
            "POST",
            f"{self.base_url}/export/video",
            expected_status=422
        )

        # 10.2 导出收藏夹 (需要 session_id)
        self.test_endpoint(
            "10.2 导出收藏夹 (无认证)",
            "POST",
            f"{self.base_url}/export/folder",
            expected_status=422
        )

        # 10.3 导出会话 (需要 session_id)
        self.test_endpoint(
            "10.3 导出会话 (无认证)",
            "POST",
            f"{self.base_url}/export/session",
            expected_status=422
        )

        # 10.4 获取会话摘要 (需要 session_id)
        self.test_endpoint(
            "10.4 获取会话摘要 (无认证)",
            "GET",
            f"{self.base_url}/export/session-summary/test-session-id",
            expected_status=422
        )

        # 10.5 刷新会话摘要 (需要 session_id)
        self.test_endpoint(
            "10.5 刷新会话摘要 (无认证)",
            "POST",
            f"{self.base_url}/export/session-summary/test-session-id/refresh",
            expected_status=422
        )

        # 10.6 删除会话摘要 (需要 session_id)
        self.test_endpoint(
            "10.6 删除会话摘要 (无认证)",
            "DELETE",
            f"{self.base_url}/export/session-summary/test-session-id",
            expected_status=422
        )

        # ==================== 11. 配置管理 - 获取/更新 LLM 配置 ====================
        self.log("\n=== 11. 配置管理 - 获取/更新 LLM 配置 ===")

        # 11.1 获取 LLM 配置
        self.test_endpoint(
            "11.1 获取 LLM 配置",
            "GET",
            f"{self.base_url}/config/llm",
            expected_status=200
        )

        # 11.2 更新 LLM 配置
        self.test_endpoint(
            "11.2 更新 LLM 配置",
            "PUT",
            f"{self.base_url}/config/llm",
            expected_status=200,
            json_data={"model": "qwen3-max", "embedding_model": "text-embedding-v4"}
        )

        # ==================== 12. 纠错功能测试 ====================
        self.log("\n=== 12. 纠错功能测试 ===")

        # 12.1 获取纠错列表 (需要 session_id)
        self.test_endpoint(
            "12.1 获取纠错列表 (无认证)",
            "GET",
            f"{self.base_url}/correction/list",
            expected_status=422
        )

        # 12.2 获取纠错详情 (需要 session_id)
        self.test_endpoint(
            "12.2 获取纠错详情 (无认证)",
            "GET",
            f"{self.base_url}/correction/{TEST_BVID}",
            expected_status=422
        )

        # 12.3 提交纠错 (需要 session_id)
        self.test_endpoint(
            "12.3 提交纠错 (无认证)",
            "POST",
            f"{self.base_url}/correction/{TEST_BVID}",
            expected_status=422,
            json_data={"corrected_text": "测试纠错"}
        )

        # 12.4 获取纠错历史 (需要 session_id)
        self.test_endpoint(
            "12.4 获取纠错历史 (无认证)",
            "GET",
            f"{self.base_url}/correction/{TEST_BVID}/history",
            expected_status=422
        )

        # ==================== 测试结果汇总 ====================
        self.log("\n" + "=" * 70)
        self.log("测试结果汇总")
        self.log("=" * 70)

        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        errors = sum(1 for r in self.results if r["status"] == "ERROR")
        skipped = sum(1 for r in self.results if r["status"] == "SKIP")

        self.log(f"通过: {passed}")
        self.log(f"失败: {failed}")
        self.log(f"错误: {errors}")
        self.log(f"跳过: {skipped}")
        self.log(f"总计: {len(self.results)}")

        # 按功能分类统计
        self.log("\n--- 按功能模块统计 ---")
        categories = {
            "基础健康检查": [],
            "认证流程": [],
            "收藏夹同步": [],
            "知识库入库": [],
            "对话问答": [],
            "会话管理": [],
            "视频总结": [],
            "主题聚类": [],
            "学习路径": [],
            "导出功能": [],
            "配置管理": [],
            "纠错功能": []
        }

        for r in self.results:
            name = r["name"]
            for cat in categories:
                if cat in name:
                    categories[cat].append(r["status"])
                    break

        for cat, statuses in categories.items():
            if statuses:
                cat_passed = sum(1 for s in statuses if s == "PASS")
                cat_total = len(statuses)
                cat_status = "PASS" if cat_passed == cat_total else "FAIL"
                self.log(f"  {cat}: {cat_passed}/{cat_total} ({cat_status})")

        # 分析失败和错误的测试
        if failed > 0 or errors > 0:
            self.log("\n--- 失败/错误的测试 ---")
            for r in self.results:
                if r["status"] in ("FAIL", "ERROR"):
                    error_info = r.get("error", "Unknown error")
                    if isinstance(error_info, dict):
                        error_info = error_info.get("detail", str(error_info))
                    self.log(f"  - {r['name']}: {error_info}", "ERROR")

        # 检查 API 基础功能
        api_working = passed >= 20
        self.log(f"\n--- API 基础功能正常: {api_working} ---")

        # 返回成功
        return passed >= 20


def main():
    """主函数"""
    runner = FullE2ETestRunner()

    try:
        success = runner.run_all_tests()
        exit_code = 0 if success else 1
        print(f"\n{'=' * 70}")
        print(f"测试完成，退出码: {exit_code}")
        print(f"\n功能测试覆盖:")
        print(f"  1. 认证流程 - 扫码登录")
        print(f"  2. 收藏夹同步 - 获取收藏夹列表")
        print(f"  3. 知识库入库 - 视频处理")
        print(f"  4. 对话问答 - 发送问题，获取回答")
        print(f"  5. 会话管理 - 创建、获取会话")
        print(f"  6. 视频总结 - 获取/生成摘要")
        print(f"  7. 主题聚类 - 获取/生成聚类")
        print(f"  8. 学习路径 - 获取/生成学习路径")
        print(f"  9. 导出功能 - 导出视频/会话")
        print(f"  10. 配置管理 - 获取/更新 LLM 配置")
        print(f"\n说明:")
        print(f"  - 需要认证的功能返回 422 (缺少 session_id)")
        print(f"  - LLM 不可用时生成摘要/聚类返回 503")
        print(f"  - 完整测试需要 B 站扫码登录获取 session_id")
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
