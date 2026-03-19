"""
快速测试脚本：验证收藏夹视频列表问题

使用方法:
    set BILI_SESSDATA=你的SESSDATA值
    python test/quick_test.py

或者在 Linux/Mac 上:
    export BILI_SESSDATA=你的SESSDATA值
    python test/quick_test.py
"""
import asyncio
import aiohttp
import json
import os
import sys

BASE_URL = "https://api.bilibili.com"


async def quick_test():
    print("=" * 60)
    print("收藏夹视频列表快速测试")
    print("=" * 60)

    sessdata = os.getenv("BILI_SESSDATA")
    if not sessdata:
        print("\n错误: 请设置 BILI_SESSDATA 环境变量")
        print("\n方法:")
        print("  Windows: set BILI_SESSDATA=你的SESSDATA && python test/quick_test.py")
        print("  Linux/Mac: export BILI_SESSDATA=你的SESSDATA && python test/quick_test.py")
        return

    cookies = {"SESSDATA": sessdata}

    media_id = input("\n请输入收藏夹 media_id: ").strip()
    if not media_id:
        print("media_id 不能为空")
        return

    async with aiohttp.ClientSession() as session:
        # Step 1: 获取收藏夹视频
        print(f"\n[Step 1] 获取收藏夹 {media_id} 的视频...")
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

            print(f"\n收藏夹标题: {info.get('title')}")
            print(f"返回视频数量: {len(medias)}")
            print(f"has_more: {has_more}")

            if len(medias) == 1:
                m = medias[0]
                bvid = m.get("bvid") or m.get("bv_id")
                title = m.get("title")
                print(f"\n⚠️ 警告: 只返回 1 个条目!")
                print(f"  bvid: {bvid}")
                print(f"  title: {title}")

                # Step 2: 获取视频信息
                print(f"\n[Step 2] 获取视频 {bvid} 的详细信息...")
                view_url = f"{BASE_URL}/x/web-interface/view"
                async with session.get(view_url, params={"bvid": bvid}, cookies=cookies) as view_resp:
                    view_data = await view_resp.json()
                    if view_data.get("code") == 0:
                        v = view_data.get("data", {})
                        print(f"  视频标题: {v.get('title')}")
                        print(f"  season: {v.get('season')}")
                        print(f"  ugc_season: {v.get('ugc_season')}")
                        print(f"  page_data: {v.get('page_data')}")

                        # 检查 series 字段
                        series = v.get("series")
                        if series:
                            print(f"  series: {series}")

                        # 获取 season_id
                        season_id = None
                        season = v.get("season")
                        ugc_season = v.get("ugc_season")
                        page_data = v.get("page_data", {})

                        if isinstance(season, dict):
                            season_id = season.get("id")
                        elif season and not isinstance(season, dict) and str(season).isdigit():
                            season_id = int(season)

                        if not season_id and isinstance(ugc_season, dict):
                            season_id = ugc_season.get("id")
                        elif not season_id and ugc_season and not isinstance(ugc_season, dict) and str(ugc_season).isdigit():
                            season_id = int(ugc_season)

                        if not season_id:
                            season_id = page_data.get("season_id")

                        if not season_id and isinstance(series, dict):
                            season_id = series.get("series_id")

                        print(f"\n  获取到的 season_id: {season_id}")

                        if season_id:
                            # Step 3: 尝试获取系列视频
                            print(f"\n[Step 3] 使用 season_id={season_id} 获取系列视频...")

                            # API 1
                            print(f"\n  尝试 API: /x/v3/fav/resource/deal/season")
                            url1 = f"{BASE_URL}/x/v3/fav/resource/deal/season"
                            params1 = {"id": season_id, "type": 2, "pn": 1, "ps": 100}
                            async with session.get(url1, params=params1, cookies=cookies) as r1:
                                d1 = await r1.json()
                                print(f"    code: {d1.get('code')}, message: {d1.get('message')}")
                                if d1.get("code") == 0:
                                    medias1 = d1.get("data", {}).get("medias", []) or []
                                    print(f"    返回 {len(medias1)} 个视频")
                                    if medias1:
                                        print(f"    第一个: [{medias1[0].get('bvid')}] {medias1[0].get('title')}")

                            # API 2
                            print(f"\n  尝试 API: /x/vseries/season")
                            url2 = f"{BASE_URL}/x/vseries/season"
                            params2 = {"id": season_id}
                            async with session.get(url2, params=params2, cookies=cookies) as r2:
                                d2 = await r2.json()
                                print(f"    code: {d2.get('code')}, message: {d2.get('message')}")
                                if d2.get("code") == 0:
                                    eps = d2.get("data", {}).get("episodes", []) or []
                                    print(f"    返回 {len(eps)} 个视频")
                                    if eps:
                                        print(f"    第一个: [{eps[0].get('bvid')}] {eps[0].get('title')}")

                            # API 3
                            print(f"\n  尝试 API: /x/series/v1/season/seasonInfo")
                            url3 = f"{BASE_URL}/x/series/v1/season/seasonInfo"
                            params3 = {"season_id": season_id}
                            async with session.get(url3, params=params3, cookies=cookies) as r3:
                                d3 = await r3.json()
                                print(f"    code: {d3.get('code')}, message: {d3.get('message')}")
                                if d3.get("code") == 0:
                                    eps = d3.get("data", {}).get("episodes", []) or []
                                    print(f"    返回 {len(eps)} 个视频")
                                    if eps:
                                        print(f"    第一个: [{eps[0].get('bvid')}] {eps[0].get('title')}")
                        else:
                            print("\n  ❌ 未能获取到 season_id")
                            print("  该视频可能不属于任何系列，或者需要其他方式获取系列信息")

            elif len(medias) > 1:
                print(f"\n✓ 收藏夹返回 {len(medias)} 个视频，看起来正常")
                print("\n前 5 个视频:")
                for m in medias[:5]:
                    bvid = m.get("bvid") or m.get("bv_id")
                    title = m.get("title")
                    print(f"  [{bvid}] {title}")
            else:
                print("\n收藏夹为空!")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("快速测试: 诊断收藏夹视频列表问题")
    print("=" * 60)
    asyncio.run(quick_test())
