"""
诊断 B站系列视频获取问题

关键问题:
1. /x/v3/fav/resource/deal/season 这个 API 可能是用于"处理"系列，而非"获取"系列视频
2. /x/vseries/season 才是获取系列视频的正确 API

本脚本验证:
1. 不同的 series_id 获取方式
2. 不同 API 的返回结果
3. 找到获取系列视频的正确方法
"""
import asyncio
import aiohttp
import json
import sys
import os


BASE_URL = "https://api.bilibili.com"


async def diagnose_series_api():
    """诊断系列视频获取问题"""

    print("=" * 70)
    print("B站系列视频获取诊断")
    print("=" * 70)

    # 获取 Cookie
    sessdata = os.getenv("BILI_SESSDATA")
    if not sessdata:
        print("\n请先设置 BILI_SESSDATA 环境变量:")
        print("  Windows: set BILI_SESSDATA=你的SESSDATA")
        print("  然后重新运行此脚本")
        return

    cookies = {"SESSDATA": sessdata}

    bvid = input("\n请输入一个属于系列的视频 BVID (如 BV1xx411c7mD): ").strip()
    if not bvid:
        print("BVID 不能为空")
        return

    async with aiohttp.ClientSession() as session:
        # Step 1: 获取视频基本信息
        print(f"\n[Step 1] 获取视频 {bvid} 的基本信息...")
        view_url = f"{BASE_URL}/x/web-interface/view"
        params = {"bvid": bvid}

        async with session.get(view_url, params=params, cookies=cookies) as resp:
            data = await resp.json()
            if data.get("code") != 0:
                print(f"获取视频信息失败: {data.get('message')}")
                return

            video_data = data.get("data", {})
            print(f"视频标题: {video_data.get('title')}")

            # 检查所有可能的系列 ID 字段
            print("\n[Step 2] 检查所有可能的系列 ID 字段...")

            print(f"\n1. season: {video_data.get('season')}")
            print(f"2. ugc_season: {video_data.get('ugc_season')}")
            print(f"3. page_data.season_id: {video_data.get('page_data', {}).get('season_id')}")
            print(f"4. static_url: {video_data.get('static_url')}")

            # 检查 season 类型的结构
            season = video_data.get("season")
            ugc_season = video_data.get("ugc_season")

            series_ids_to_test = []

            if isinstance(season, dict):
                sid = season.get("id")
                if sid:
                    series_ids_to_test.append(("season.id", sid))

            if isinstance(ugc_season, dict):
                sid = ugc_season.get("id")
                if sid:
                    series_ids_to_test.append(("ugc_season.id", sid))

            page_data = video_data.get("page_data", {})
            sid = page_data.get("season_id")
            if sid:
                series_ids_to_test.append(("page_data.season_id", sid))

            # 也检查直接的 season 值
            if season and not isinstance(season, dict):
                series_ids_to_test.append(("season_direct", season))

            if ugc_season and not isinstance(ugc_season, dict):
                series_ids_to_test.append(("ugc_season_direct", ugc_season))

            print(f"\n[Step 3] 找到的 series_ids: {series_ids_to_test}")

            # 测试每个 series_id
            for source, series_id in series_ids_to_test:
                print(f"\n{'='*70}")
                print(f"测试 {source}: series_id = {series_id}")
                print(f"{'='*70}")

                # 方法1: /x/v3/fav/resource/deal/season
                print(f"\n  [API 1] /x/v3/fav/resource/deal/season")
                url1 = f"{BASE_URL}/x/v3/fav/resource/deal/season"
                params1 = {"id": series_id, "type": 2, "pn": 1, "ps": 100}
                try:
                    async with session.get(url1, params=params1, cookies=cookies) as resp1:
                        data1 = await resp1.json()
                        print(f"    code: {data1.get('code')}")
                        print(f"    message: {data1.get('message')}")
                        if data1.get("code") == 0:
                            medias = data1.get("data", {}).get("medias", []) or []
                            print(f"    medias 数量: {len(medias)}")
                            if medias:
                                print(f"    第一个 medias 的 title: {medias[0].get('title')}")
                                print(f"    第一个 medias 的 keys: {list(medias[0].keys())}")
                except Exception as e:
                    print(f"    异常: {e}")

                # 方法2: /x/vseries/season
                print(f"\n  [API 2] /x/vseries/season")
                url2 = f"{BASE_URL}/x/vseries/season"
                params2 = {"id": series_id}
                try:
                    async with session.get(url2, params=params2, cookies=cookies) as resp2:
                        data2 = await resp2.json()
                        print(f"    code: {data2.get('code')}")
                        print(f"    message: {data2.get('message')}")
                        if data2.get("code") == 0:
                            episodes = data2.get("data", {}).get("episodes", []) or []
                            print(f"    episodes 数量: {len(episodes)}")
                            if episodes:
                                print(f"    第一个 episode 的 title: {episodes[0].get('title')}")
                                print(f"    第一个 episode 的 keys: {list(episodes[0].keys())}")
                except Exception as e:
                    print(f"    异常: {e}")

                # 方法3: /x/series/v1/season/seasonInfo
                print(f"\n  [API 3] /x/series/v1/season/seasonInfo")
                url3 = f"{BASE_URL}/x/series/v1/season/seasonInfo"
                params3 = {"season_id": series_id}
                try:
                    async with session.get(url3, params=params3, cookies=cookies) as resp3:
                        data3 = await resp3.json()
                        print(f"    code: {data3.get('code')}")
                        print(f"    message: {data3.get('message')}")
                        if data3.get("code") == 0:
                            media = data3.get("data", {}).get("media", {})
                            print(f"    media title: {media.get('title')}")
                            episodes = data3.get("data", {}).get("episodes", []) or []
                            print(f"    episodes 数量: {len(episodes)}")
                except Exception as e:
                    print(f"    异常: {e}")

                # 方法4: /x/polymer/web-dynamic/v1/season_detail
                print(f"\n  [API 4] /x/polymer/web-dynamic/v1/season_detail")
                url4 = f"{BASE_URL}/x/polymer/web-dynamic/v1/season_detail"
                params4 = {"season_id": series_id}
                try:
                    async with session.get(url4, params=params4, cookies=cookies) as resp4:
                        data4 = await resp4.json()
                        print(f"    code: {data4.get('code')}")
                        print(f"    message: {data4.get('message')}")
                        if data4.get("code") == 0:
                            items = data4.get("data", {}).get("items", [])
                            print(f"    items 数量: {len(items)}")
                except Exception as e:
                    print(f"    异常: {e}")


if __name__ == "__main__":
    asyncio.run(diagnose_series_api())
