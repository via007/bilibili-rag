"""
直接测试 B站 API 获取收藏夹视频

用于诊断：收藏夹展开时只显示收藏夹标题而非视频列表的问题

用法:
    python test/test_favorite_api.py
"""
import asyncio
import sys
import os
import aiohttp
import json
from typing import Optional

# 配置
BASE_URL = "https://api.bilibili.com"


async def test_favorite_api():
    """直接测试 B站收藏夹 API"""

    print("=" * 60)
    print("B站收藏夹 API 直接测试")
    print("=" * 60)

    # 获取 Cookie
    sessdata = os.getenv("BILI_SESSDATA")
    if not sessdata:
        print("\n请设置 BILI_SESSDATA 环境变量:")
        print("  Windows: set BILI_SESSDATA=你的SESSDATA值")
        print("  然后重新运行此脚本")
        return

    cookies = {"SESSDATA": sessdata}

    async with aiohttp.ClientSession() as session:
        # 获取收藏夹列表
        print("\n[1] 获取收藏夹列表...")
        mid = input("请输入你的 B站 MID (用户ID): ").strip()
        if not mid:
            print("MID 不能为空")
            return

        url = f"{BASE_URL}/x/v3/fav/folder/created/list-all"
        params = {"up_mid": mid}

        async with session.get(url, params=params, cookies=cookies) as resp:
            data = await resp.json()
            if data.get("code") != 0:
                print(f"获取收藏夹列表失败: {data.get('message')}")
                return

            folders = data.get("data", {}).get("list", [])
            print(f"\n获取到 {len(folders)} 个收藏夹:")
            for f in folders[:15]:
                print(f"  [{f.get('id')}] {f.get('title')} (共 {f.get('media_count', 0)} 个)")
            if len(folders) > 15:
                print(f"  ... 还有 {len(folders) - 15} 个")

        # 选择收藏夹获取视频
        media_id = input("\n请输入要诊断的收藏夹 media_id: ").strip()
        if not media_id:
            print("media_id 不能为空")
            return

        print(f"\n[2] 获取收藏夹 {media_id} 的视频列表...")
        url = f"{BASE_URL}/x/v3/fav/resource/list"
        params = {
            "media_id": media_id,
            "pn": 1,
            "ps": 20,
            "platform": "web"
        }

        async with session.get(url, params=params, cookies=cookies) as resp:
            data = await resp.json()
            if data.get("code") != 0:
                print(f"获取收藏夹内容失败: {data.get('message')}")
                return

            info = data.get("data", {}).get("info", {})
            medias = data.get("data", {}).get("medias", []) or []
            has_more = data.get("data", {}).get("has_more", False)

            print(f"\n收藏夹信息: {info.get('title')}")
            print(f"视频数量: {len(medias)}")
            print(f"has_more: {has_more}")

            print(f"\n视频列表:")
            for m in medias:
                bvid = m.get("bvid") or m.get("bv_id", "N/A")
                title = m.get("title", "N/A")
                attr = m.get("attr", 0)
                print(f"  [{bvid}] {title} (attr={attr})")

            # 分析问题
            if len(medias) == 1:
                m = medias[0]
                bvid = m.get("bvid") or m.get("bv_id")
                title = m.get("title", "N/A")
                attr = m.get("attr", 0)

                print(f"\n" + "=" * 60)
                print("⚠️ 问题诊断")
                print("=" * 60)
                print(f"收藏夹只返回 1 个条目: [{bvid}] {title}")
                print(f"attr = {attr}")

                # attr = 9 表示失效视频
                if attr == 9:
                    print("\n⚠️ attr=9 表示这是失效视频!")
                elif "已失效" in title or "已删除" in title:
                    print("\n⚠️ 标题包含'已失效'或'已删除'!")

                # 获取视频详情检查是否是系列
                print(f"\n[3] 检查视频 {bvid} 是否属于某个系列...")

                view_url = f"{BASE_URL}/x/web-interface/view"
                view_params = {"bvid": bvid}

                async with session.get(view_url, params=view_params, cookies=cookies) as view_resp:
                    view_data = await view_resp.json()
                    if view_data.get("code") == 0:
                        view_info = view_data.get("data", {})
                        print(f"\n视频标题: {view_info.get('title')}")
                        print(f"season: {view_info.get('season')}")
                        print(f"ugc_season: {view_info.get('ugc_season')}")
                        print(f"page_data: {view_info.get('page_data')}")

                        # 提取 season_id
                        season = view_info.get("season")
                        ugc_season = view_info.get("ugc_season")
                        page_data = view_info.get("page_data", {})

                        series_id = None
                        if isinstance(season, dict):
                            series_id = season.get("id")
                            print(f"\n从 season dict 获取到 series_id: {series_id}")
                        elif season and not isinstance(season, dict):
                            if str(season).isdigit():
                                series_id = int(season)
                                print(f"\n从 season direct 获取到 series_id: {series_id}")

                        if not series_id and isinstance(ugc_season, dict):
                            series_id = ugc_season.get("id")
                            print(f"从 ugc_season dict 获取到 series_id: {series_id}")
                        elif not series_id and ugc_season and not isinstance(ugc_season, dict):
                            if str(ugc_season).isdigit():
                                series_id = int(ugc_season)
                                print(f"从 ugc_season direct 获取到 series_id: {series_id}")

                        if not series_id and page_data:
                            series_id = page_data.get("season_id")
                            print(f"从 page_data.season_id 获取到 series_id: {series_id}")

                        if series_id:
                            print(f"\n[4] 使用 series_id={series_id} 获取系列视频...")
                            season_url = f"{BASE_URL}/x/v3/fav/resource/deal/season"
                            season_params = {
                                "id": series_id,
                                "type": 2,
                                "pn": 1,
                                "ps": 100
                            }

                            async with session.get(season_url, params=season_params, cookies=cookies) as season_resp:
                                season_data = await season_resp.json()
                                print(f"API 返回 code: {season_data.get('code')}")
                                print(f"API 返回 message: {season_data.get('message')}")

                                if season_data.get("code") == 0:
                                    series_medias = season_data.get("data", {}).get("medias", []) or []
                                    print(f"\n系列视频数量: {len(series_medias)}")
                                    for v in series_medias[:5]:
                                        print(f"  [{v.get('bvid')}] {v.get('title')}")
                                    if len(series_medias) > 5:
                                        print(f"  ... 还有 {len(series_medias) - 5} 个")
                                else:
                                    print(f"获取系列视频失败: {season_data.get('message')}")
                                    # 尝试备用 API
                                    print("\n尝试备用 API /x/vseries/season...")
                                    vseries_url = f"{BASE_URL}/x/vseries/season"
                                    async with session.get(vseries_url, params={"id": series_id}, cookies=cookies) as vs_resp:
                                        vs_data = await vs_resp.json()
                                        print(f"备用 API 返回 code: {vs_data.get('code')}")
                                        if vs_data.get("code") == 0:
                                            episodes = vs_data.get("data", {}).get("episodes", []) or []
                                            print(f"episodes 数量: {len(episodes)}")
                                            for ep in episodes[:5]:
                                                print(f"  [{ep.get('bvid')}] {ep.get('title')}")
                                        else:
                                            print(f"备用 API 也失败: {vs_data.get('message')}")
                        else:
                            print("\n❌ 未找到 series_id!")
                            print("该视频可能不属于任何系列。")
                            print("问题可能是：")
                            print("  1. 收藏夹类型不是标准系列")
                            print("  2. 该收藏夹确实是单个视频")
                            print("  3. B站 API 返回的数据结构不同")
                    else:
                        print(f"获取视频详情失败: {view_data.get('message')}")

            elif len(medias) > 1:
                print(f"\n✓ 收藏夹返回了 {len(medias)} 个视频，看起来正常")
            else:
                print("\n收藏夹为空!")


if __name__ == "__main__":
    asyncio.run(test_favorite_api())
