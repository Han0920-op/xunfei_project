"""Offline operator validation. Never installs data or marks it verified itself."""
import argparse
from datetime import datetime

from pesticides import CHINA_TIME, MAX_AGE_DAYS, load_catalog


def main():
    parser = argparse.ArgumentParser(description="校验人工整理的登记快照；不能代替官方信息核验")
    parser.add_argument("path")
    args = parser.parse_args()
    try:
        catalog = load_catalog(args.path)
    except (OSError, ValueError):
        parser.exit(1, "文件不可读取或未通过结构校验。请按 docs/pesticide-data.md 检查字段、来源域名及重复号。\n")
    today = datetime.now(CHINA_TIME).date()
    stale = sum(not 0 <= (today - r.source.reviewed_on).days <= MAX_AGE_DAYS for r in catalog.records)
    unknown = sum(r.status == "unknown" for r in catalog.records)
    technical = sum(r.technical_material for r in catalog.records)
    print(f"结构校验通过：{len(catalog.records)} 条；需复核资料日期：{stale} 条；当前状态未知：{unknown} 条；原药母药：{technical} 条。此结果不证明当前登记有效或允许施药。")


if __name__ == "__main__":
    main()
