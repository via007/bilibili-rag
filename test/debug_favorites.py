"""
测试收藏夹视频列表问题

直接调用 BilibiliService 来诊断：
1. 收藏夹只返回1个视频时，video_info 的 season/ugc_season 字段结构
2. series_id 获取是否正确
3. get_series_videos 是否能返回正确的视频列表
"""
import asyncio
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.bilibili import BilibiliService
from loguru import logger
import json


async def test_series_detection():
    """测试系列视频检测逻辑"""

    # 从环境变量或配置文件获取 cookie
    # 这里需要真实的 SESSDATA 才能测试
    # 请先在 .env 中配置或直接在这里填入测试用 Cookie

    print("=" * 60)
    print("收藏夹视频列表问题诊断")
    print("=" * 60)

    # 提示用户输入测试信息
    print("\n请选择测试方式：")
    print("1. 输入 BVID 测试视频信息获取 (用于分析 season 字段)")
    print("2. 输入系列 ID 测试 get_series_videos")
    print("3. 退出")

    choice = input("\n请输入选项 (1/2/3): ").strip()

    if choice == "1":
        bvid = input("请输入 BVID (如 BV1xx411c7mD): ").strip()
        if not bvid:
            print("BVID 不能为空")
            return

        print(f"\n正在获取视频信息: {bvid}")
        print("-" * 40)

        # 创建 service 实例（需要真实的 cookie）
        # TODO: 从配置文件或环境变量获取
        print("错误: 需要配置 SESSDATA cookie")
        print("请在代码中填入真实的 Cookie 进行测试")

    elif choice == "2":
        series_id = input("请输入系列 ID (如 12345): ").strip()
        if not series_id:
            print("系列 ID 不能为空")
            return

        try:
            series_id = int(series_id)
        except ValueError:
            print("系列 ID 必须是数字")
            return

        print(f"\n正在获取系列视频列表: series_id={series_id}")
        print("-" * 40)

        print("错误: 需要配置 SESSDATA cookie")
        print("请在代码中填入真实的 Cookie 进行测试")

    elif choice == "3":
        print("退出")
    else:
        print(f"无效的选项: {choice}")


async def test_bilibili_api_directly():
    """
    直接测试 B站 API，不通过 session

    这个测试需要:
    1. 一个有效的 SESSDATA cookie
    2. 要测试的 media_id (收藏夹 ID)
    """

    # 配置 - 请填入有效的 Cookie
    SESSDATA = os.getenv("BILI_SESSDATA") or input("请输入 SESSDATA Cookie: ").strip()
    BILI_JCT = os.getenv("BILI_JCT") or ""
    DEDEUSERID = os.getenv("BILI_DEDEUSERID") or ""

    if not SESSDATA:
        print("错误: SESSDATA 不能为空")
        return

    bili = BilibiliService(
        sessdata=SESSDATA,
        bili_jct=BILI_JCT,
        dedeuserid=DEDEUSERID
    )

    print("=" * 60)
    print("B站 API 直接测试")
    print("=" * 60)

    # 测试选项
    print("\n请选择测试内容：")
    print("1. 获取收藏夹列表")
    print("2. 获取收藏夹视频 (指定 media_id)")
    print("3. 获取视频信息 (指定 bvid)")
    print("4. 获取视频分P列表 (指定 bvid)")
    print("5. 获取系列视频 (指定 series_id)")
    print("6. 诊断收藏夹问题 (输入 media_id，自动检测)")

    choice = input("\n请输入选项: ").strip()

    try:
        if choice == "1":
            mid = input("请输入 UP 主 MID (用户 ID): ").strip()
            if not mid:
                mid = DEDEUSERID

            print(f"\n获取用户 {mid} 的收藏夹列表...")
            folders = await bili.get_user_favorites(mid=int(mid) if mid.isdigit() else mid)
            print(f"\n获取到 {len(folders)} 个收藏夹:")
            for f in folders[:10]:
                print(f"  - [{f.get('id')}] {f.get('title')} (共 {f.get('media_count', 0)} 个视频)")
            if len(folders) > 10:
                print(f"  ... 还有 {len(folders) - 10} 个收藏夹")

        elif choice == "2":
            media_id = input("请输入收藏夹 media_id: ").strip()
            if not media_id:
                print("media_id 不能为空")
                return

            print(f"\n获取收藏夹 {media_id} 的视频...")
            result = await bili.get_favorite_content(int(media_id), pn=1, ps=20)
            medias = result.get("medias", [])
            print(f"\n获取到 {len(medias)} 个视频:")
            for m in medias[:5]:
                bvid = m.get("bvid") or m.get("bv_id", "N/A")
                title = m.get("title", "N/A")
                print(f"  - [{bvid}] {title}")
            if len(medias) > 5:
                print(f"  ... 还有 {len(medias) - 5} 个视频")
            print(f"\nhas_more: {result.get('has_more')}")

        elif choice == "3":
            bvid = input("请输入 BVID: ").strip()
            if not bvid:
                print("BVID 不能为空")
                return

            print(f"\n获取视频 {bvid} 的信息...")
            info = await bili.get_video_info(bvid)

            print("\n=== 视频基本信息 ===")
            print(f"标题: {info.get('title')}")
            print(f"作者: {info.get('owner', {}).get('name') if isinstance(info.get('owner'), dict) else info.get('owner')}")
            print(f"时长: {info.get('duration')} 秒")

            print("\n=== 季节/系列相关字段 ===")
            print(f"season: {info.get('season')}")
            print(f"ugc_season: {info.get('ugc_season')}")
            print(f"page_data: {info.get('page_data')}")

            # 提取可能的 series_id
            season = info.get("season")
            ugc_season = info.get("ugc_season")

            series_id = None
            if isinstance(season, dict):
                series_id = season.get("id")
            elif season and not isinstance(season, dict):
                series_id = int(season) if str(season).isdigit() else None

            if not series_id and isinstance(ugc_season, dict):
                series_id = ugc_season.get("id")
            elif not series_id and ugc_season and not isinstance(ugc_season, dict):
                series_id = int(ugc_season) if str(ugc_season).isdigit() else None

            if not series_id:
                page_data = info.get("page_data", {})
                series_id = page_data.get("season_id")

            print(f"\n=== 提取的 series_id: {series_id} ===")

            if series_id:
                print(f"\n检测到 series_id: {series_id}，正在获取系列视频...")
                series_videos = await bili.get_series_videos(series_id)
                print(f"系列视频数量: {len(series_videos)}")
                for v in series_videos[:5]:
                    print(f"  - [{v.get('bvid')}] {v.get('title')}")
                if len(series_videos) > 5:
                    print(f"  ... 还有 {len(series_videos) - 5} 个视频")

        elif choice == "4":
            bvid = input("请输入 BVID: ").strip()
            if not bvid:
                print("BVID 不能为空")
                return

            print(f"\n获取视频 {bvid} 的分P列表...")
            pages = await bili.get_video_pagelist(bvid)
            print(f"\n分P数量: {len(pages)}")
            for p in pages:
                print(f"  P{p.get('page')}: {p.get('part')} (cid: {p.get('cid')})")

        elif choice == "5":
            series_id = input("请输入系列 ID: ").strip()
            if not series_id:
                print("系列 ID 不能为空")
                return

            print(f"\n获取系列 {series_id} 的视频...")
            videos = await bili.get_series_videos(int(series_id))
            print(f"\n获取到 {len(videos)} 个视频:")
            for v in videos[:10]:
                print(f"  - [{v.get('bvid')}] {v.get('title')}")
            if len(videos) > 10:
                print(f"  ... 还有 {len(videos) - 10} 个视频")

        elif choice == "6":
            media_id = input("请输入收藏夹 media_id: ").strip()
            if not media_id:
                print("media_id 不能为空")
                return

            print(f"\n{'='*60}")
            print(f"诊断收藏夹 {media_id} 的问题")
            print(f"{'='*60}")

            # Step 1: 获取收藏夹视频
            print("\n[Step 1] 获取收藏夹视频...")
            all_videos = await bili.get_all_favorite_videos(int(media_id))
            print(f"收藏夹总共 {len(all_videos)} 个条目")

            if len(all_videos) == 1:
                video = all_videos[0]
                bvid = video.get("bvid") or video.get("bv_id")
                title = video.get("title", "N/A")
                print(f"\n只有 1 个条目: [{bvid}] {title}")

                print("\n[Step 2] 获取视频详细信息，检查是否是系列...")
                video_info = await bili.get_video_info(bvid)

                print("\n=== video_info 关键字段 ===")
                print(f"title: {video_info.get('title')}")
                print(f"season: {video_info.get('season')}")
                print(f"ugc_season: {video_info.get('ugc_season')}")
                print(f"page_data: {video_info.get('page_data')}")

                # 提取 series_id
                season = video_info.get("season")
                ugc_season = video_info.get("ugc_season")
                page_data = video_info.get("page_data", {})

                series_id = None
                series_source = None

                if isinstance(season, dict):
                    series_id = season.get("id")
                    series_source = "season dict"
                elif season and not isinstance(season, dict):
                    if str(season).isdigit():
                        series_id = int(season)
                        series_source = "season direct"

                if not series_id and isinstance(ugc_season, dict):
                    series_id = ugc_season.get("id")
                    series_source = "ugc_season dict"
                elif not series_id and ugc_season and not isinstance(ugc_season, dict):
                    if str(ugc_season).isdigit():
                        series_id = int(ugc_season)
                        series_source = "ugc_season direct"

                if not series_id and page_data:
                    series_id = page_data.get("season_id")
                    series_source = "page_data.season_id"

                print(f"\n=== 提取的 series_id: {series_id} (来源: {series_source}) ===")

                if series_id:
                    print(f"\n[Step 3] 使用 series_id={series_id} 获取系列视频...")
                    series_videos = await bili.get_series_videos(series_id)
                    print(f"get_series_videos 返回 {len(series_videos)} 个视频")

                    if series_videos:
                        print("\n系列视频列表 (前5个):")
                        for v in series_videos[:5]:
                            print(f"  - [{v.get('bvid')}] {v.get('title')}")
                        if len(series_videos) > 5:
                            print(f"  ... 还有 {len(series_videos) - 5} 个视频")

                        # 检查 title 是否正确
                        first_title = series_videos[0].get("title", "")
                        if title in first_title or first_title in title:
                            print("\n⚠️ 警告: 系列视频的第一个标题包含收藏夹标题，可能存在混淆!")
                        else:
                            print("\n✓ 系列视频标题与收藏夹标题不同，看起来正常")
                    else:
                        print("\n❌ get_series_videos 返回空列表!")
                        print("可能的原因:")
                        print("  1. series_id 格式不正确")
                        print("  2. B站 API 变更")
                        print("  3. 该系列不是标准系列类型")
                else:
                    print("\n❌ 无法提取 series_id!")
                    print("可能的原因:")
                    print("  1. 该视频不是任何系列的一部分")
                    print("  2. B站 API 返回的字段结构不同")
                    print("  3. 需要检查其他字段")

            elif len(all_videos) > 1:
                print(f"\n收藏夹包含 {len(all_videos)} 个条目，无需检查系列")
                print("前5个条目:")
                for v in all_videos[:5]:
                    bvid = v.get("bvid") or v.get("bv_id", "N/A")
                    title = v.get("title", "N/A")
                    print(f"  - [{bvid}] {title}")
            else:
                print("\n收藏夹为空!")

        else:
            print(f"无效的选项: {choice}")

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await bili.close()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Bilibili RAG - 收藏夹问题诊断工具")
    print("=" * 60)
    print("\n此脚本直接调用 B站 API 进行测试")
    print("需要有效的 SESSDATA Cookie")
    print()

    # 检查是否有 Cookie 环境变量
    if os.getenv("BILI_SESSDATA"):
        print("✓ 检测到 BILI_SESSDATA 环境变量")
        asyncio.run(test_bilibili_api_directly())
    else:
        print("✗ 未检测到 BILI_SESSDATA 环境变量")
        print("\n可以设置环境变量后运行:")
        print("  Windows: set BILI_SESSDATA=your_sessdata && python test/debug_favorites.py")
        print("  Linux/Mac: export BILI_SESSDATA=your_sessdata && python test/debug_favorites.py")
        print()
        response = input("是否继续并手动输入 Cookie? (y/n): ").strip().lower()
        if response == "y":
            asyncio.run(test_bilibili_api_directly())
        else:
            print("退出")