#!/usr/bin/env python3
"""测试 akshare 板块（行业/概念）实时行情接口"""
import sys
import asyncio

# ── 配置 ──
# 改成你想测试的板块代码
TEST_BOARD_CODE = "BK0447"  # 光模块 / 半导体等


async def test_akshare_board():
    try:
        import akshare as ak
    except ImportError:
        print("✗ akshare 未安装，请先 pip install akshare")
        sys.exit(1)

    print(f"=== 1. 测试获取全部行业板块名称（轻量接口）===")
    try:
        df = await asyncio.to_thread(ak.stock_board_industry_name_em)
        print(f"  行数: {df.shape[0]}, 列: {list(df.columns)}")
        print(f"  前5行:\n{df.head().to_string()}")
    except Exception as e:
        print(f"  ✗ 失败: {e}")

    print(f"\n=== 2. 测试获取全部概念板块名称（轻量接口）===")
    try:
        df = await asyncio.to_thread(ak.stock_board_concept_name_em)
        print(f"  行数: {df.shape[0]}, 列: {list(df.columns)}")
        print(f"  前5行:\n{df.head().to_string()}")
    except Exception as e:
        print(f"  ✗ 失败: {e}")

    print(f"\n=== 3. 测试获取指定板块实时行情（{TEST_BOARD_CODE}）===")
    # 先在行业板块中查找
    try:
        df = await asyncio.to_thread(ak.stock_board_industry_spot_em)
        match = df[df['板块代码'].astype(str).str.strip() == TEST_BOARD_CODE]
        if not match.empty:
            row = match.iloc[0]
            print(f"  【行业板块】查到 {TEST_BOARD_CODE}:")
            for col in df.columns:
                print(f"    {col}: {row[col]}")
        else:
            print(f"  行业板块中未找到 {TEST_BOARD_CODE}，尝试概念板块...")
    except Exception as e:
        print(f"  industry_spot 失败: {e}")

    try:
        df = await asyncio.to_thread(ak.stock_board_concept_spot_em)
        match = df[df['板块代码'].astype(str).str.strip() == TEST_BOARD_CODE]
        if not match.empty:
            row = match.iloc[0]
            print(f"  【概念板块】查到 {TEST_BOARD_CODE}:")
            for col in df.columns:
                print(f"    {col}: {row[col]}")
        else:
            print(f"  概念板块中也未找到 {TEST_BOARD_CODE}")
    except Exception as e:
        print(f"  concept_spot 失败: {e}")

    print(f"\n=== 4. 测试获取板块成分股（{TEST_BOARD_CODE}）===")
    try:
        df = await asyncio.to_thread(ak.stock_sector_detail, symbol=TEST_BOARD_CODE)
        print(f"  成分股数量: {df.shape[0]}")
        print(f"  列: {list(df.columns)}")
        if not df.empty:
            print(f"  涨跌幅统计:\n{df['涨跌幅'].describe()}")
            print(f"  前5只:\n{df.head().to_string()}")
    except Exception as e:
        print(f"  ✗ 失败: {e}")

    print(f"\n=== 5. 测试按名称模糊搜索板块 ===")
    try:
        df = await asyncio.to_thread(ak.stock_board_industry_name_em)
        keyword = "半导体"
        mask = df['板块名称'].str.contains(keyword)
        hits = df[mask]
        print(f"  搜索 '{keyword}' 找到 {len(hits)} 个:")
        print(hits.to_string())
    except Exception as e:
        print(f"  ✗ 失败: {e}")


if __name__ == "__main__":
    asyncio.run(test_akshare_board())
