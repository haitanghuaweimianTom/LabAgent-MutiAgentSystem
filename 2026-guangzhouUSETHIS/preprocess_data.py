#!/usr/bin/env python3
"""
数据预处理脚本
===============

将 data/ 目录下的原始数据和根目录的 CSV 数据整合为系统可直接使用的格式：
1. brent_wti_daily.xlsx - 布伦特+WTI 日度价格（2016-2026）
2. china_oil_adjust_history.xlsx - 国内成品油调价历史
3. china_cpi_ppi_monthly.xlsx - CPI+PPI 月度数据
4. macro_data.xlsx - 宏观经济指标（进口量、油价等）
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent

def clean_chinese_csv(path):
    """读取带 BOM 和中文编码的 CSV"""
    for enc in ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    return pd.read_csv(path, encoding='utf-8-sig', on_bad_lines='skip')

def preprocess():
    results = {}

    # 1. 布伦特 + WTI 日度价格（从 data/ 优先，回退到根目录）
    print("处理国际原油日度价格...")
    brent_daily_file = BASE / "data" / "DCOILBRENTEU-Brent.csv"
    wti_daily_file = BASE / "data" / "DCOILWTICO-WTI.csv"
    if not brent_daily_file.exists():
        brent_daily_file = BASE / "brent_daily.csv"
    if not wti_daily_file.exists():
        wti_daily_file = BASE / "wti_daily.csv"

    brent = pd.read_csv(brent_daily_file)
    wti = pd.read_csv(wti_daily_file)

    # 标准化列名
    brent.columns = ['date', 'brent']
    wti.columns = ['date', 'wti']
    for df in [brent, wti]:
        df['date'] = pd.to_datetime(df['date'])

    # 合并
    oil_daily = pd.merge(brent, wti, on='date', how='outer').sort_values('date')
    # 只保留 2016-2026
    oil_daily = oil_daily[(oil_daily['date'] >= '2016-01-01')].copy()
    oil_daily.to_excel(BASE / "brent_wti_daily.xlsx", index=False)
    results['brent_wti_daily'] = str(BASE / "brent_wti_daily.xlsx")
    print(f"  brent_wti_daily.xlsx: {len(oil_daily)} 条记录")

    # 2. 国内成品油调价历史
    print("处理国内成品油调价数据...")
    china_oil = clean_chinese_csv(BASE / "china_oil_prices.csv")
    china_oil.to_excel(BASE / "china_oil_adjust_history.xlsx", index=False)
    results['china_oil_adjust_history'] = str(BASE / "china_oil_adjust_history.xlsx")
    print(f"  china_oil_adjust_history.xlsx: {len(china_oil)} 条记录")

    # 3. CPI + PPI 月度数据
    print("处理 CPI 和 PPI 数据...")
    cpi_monthly = clean_chinese_csv(BASE / "china_cpi_monthly.csv")
    ppi_monthly = clean_chinese_csv(BASE / "china_ppi_monthly.csv")
    with pd.ExcelWriter(BASE / "china_cpi_ppi_monthly.xlsx", engine='openpyxl') as writer:
        cpi_monthly.to_excel(writer, sheet_name='CPI', index=False)
        ppi_monthly.to_excel(writer, sheet_name='PPI', index=False)
    results['china_cpi_ppi_monthly'] = str(BASE / "china_cpi_ppi_monthly.xlsx")
    print(f"  china_cpi_ppi_monthly.xlsx: CPI {len(cpi_monthly)} 条, PPI {len(ppi_monthly)} 条")

    # 4. 宏观经济数据（进口、油价月度等）
    print("处理宏观经济数据...")
    imports = clean_chinese_csv(BASE / "china_imports.csv")

    # 从 data/ 读取 IMF 月度油价
    imf_oil = None
    imf_file = BASE / "data" / "IMF_原油月度价格_2009_2026.csv"
    if imf_file.exists():
        imf_oil = pd.read_csv(imf_file, encoding='utf-8-sig')

    with pd.ExcelWriter(BASE / "macro_data.xlsx", engine='openpyxl') as writer:
        imports.to_excel(writer, sheet_name='imports', index=False)
        if imf_oil is not None:
            imf_oil.to_excel(writer, sheet_name='oil_monthly', index=False)

    results['macro_data'] = str(BASE / "macro_data.xlsx")
    print(f"  macro_data.xlsx: 进口 {len(imports)} 条" + (f", IMF油价 {len(imf_oil)} 条" if imf_oil is not None else ""))

    # 5. 生成数据说明文件
    print("生成数据说明文档...")
    summary = """# 2026年广州B题 成品油价格调控机制 - 数据说明

## 数据来源
- 国际原油价格: FRED (DCOILBRENTEU, DCOILWTICO)
- 国内成品油调价: 卓创资讯/隆众资讯汇总
- 宏观经济: 国家统计局、海关总署

## 文件列表

| 文件名 | 内容 | 时间范围 |
|--------|------|----------|
| brent_wti_daily.xlsx | 布伦特+WTI 日度价格（美元/桶） | 2016-2026 |
| china_oil_adjust_history.xlsx | 国内汽柴油调价历史记录（元/吨） | 2000-2026 |
| china_cpi_ppi_monthly.xlsx | 中国CPI/PPI月度数据（两个sheet） | 1996-2026 |
| macro_data.xlsx | 原油进口量、IMF月度油价 | 2009-2026 |

## 关键统计
"""
    summary += f"- 布伦特日均价（2016-2026）: ${oil_daily['brent'].mean():.2f}/桶\n"
    summary += f"- 布伦特最高价: ${oil_daily['brent'].max():.2f}/桶 ({oil_daily.loc[oil_daily['brent'].idxmax(), 'date']:%Y-%m-%d})\n"
    summary += f"- 布伦特最低价: ${oil_daily['brent'].min():.2f}/桶 ({oil_daily.loc[oil_daily['brent'].idxmin(), 'date']:%Y-%m-%d})\n"
    summary += f"- 国内调价记录: {len(china_oil)} 次\n"
    summary += f"- CPI月度记录: {len(cpi_monthly)} 条\n"
    summary += f"- PPI月度记录: {len(ppi_monthly)} 条\n"

    (BASE / "data_summary.md").write_text(summary, encoding='utf-8')

    print(f"\n数据预处理完成！共生成 {len(results)} 个数据文件：")
    for name, path in results.items():
        print(f"  - {name}: {path}")
    return results

if __name__ == '__main__':
    preprocess()
