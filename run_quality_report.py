# -*- coding: utf-8 -*-
"""
数据质量报告：读取关联层（或分组层）数据，生成质量报告与统计表，
便于规则微调（相似度阈值、轮次正则等）。
输出目录：data_quality/
"""
import os

import pandas as pd

from quality_report import (
    amount_missing_by_customer,
    amount_missing_by_record_type,
    amount_unit_by_customer,
    amount_unit_by_record_type,
    project_tender_bid_balance,
    project_balance_summary,
    core_name_quality,
    build_report,
    CORE_NAME_MIN_LEN,
)

LINKED_DIR = "data_linked"
GROUPED_DIR = "data_grouped"
QUALITY_DIR = "data_quality"
LINKED_FILE = "tender_linked.csv"
GROUPED_FILE = "tender_grouped.csv"


def load_latest_layer() -> pd.DataFrame:
    """优先读关联层，若无则读分组层。"""
    linked_path = os.path.join(LINKED_DIR, LINKED_FILE)
    grouped_path = os.path.join(GROUPED_DIR, GROUPED_FILE)
    if os.path.isfile(linked_path):
        return pd.read_csv(linked_path, encoding="utf-8-sig")
    if os.path.isfile(grouped_path):
        return pd.read_csv(grouped_path, encoding="utf-8-sig")
    raise FileNotFoundError(f"未找到 {linked_path} 或 {grouped_path}，请先执行 run_link.py 或 run_group.py")


def run():
    df = load_latest_layer()
    os.makedirs(QUALITY_DIR, exist_ok=True)

    # Markdown 报告
    report_text = build_report(df)
    report_path = os.path.join(QUALITY_DIR, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"已写入 {report_path}")

    # 统计表 CSV（便于后续对比与规则微调）
    amount_missing_by_customer(df).to_csv(
        os.path.join(QUALITY_DIR, "amount_missing_by_customer.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    amount_missing_by_record_type(df).to_csv(
        os.path.join(QUALITY_DIR, "amount_missing_by_record_type.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    amount_unit_by_customer(df).to_csv(
        os.path.join(QUALITY_DIR, "amount_unit_by_customer.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    amount_unit_by_record_type(df).to_csv(
        os.path.join(QUALITY_DIR, "amount_unit_by_record_type.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    balance = project_tender_bid_balance(df)
    balance.to_csv(
        os.path.join(QUALITY_DIR, "project_tender_bid_balance.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    project_balance_summary(balance).to_csv(
        os.path.join(QUALITY_DIR, "project_balance_summary.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    cq = core_name_quality(df)
    if not cq["by_customer"].empty:
        cq["by_customer"].to_csv(
            os.path.join(QUALITY_DIR, "core_name_quality_by_customer.csv"),
            index=False,
            encoding="utf-8-sig",
        )

    print(f"已写入 {QUALITY_DIR}/ 下统计表 CSV")
    print(f"数据量: {len(df)} 条，project_name_core 过短阈值: <{CORE_NAME_MIN_LEN} 字")


if __name__ == "__main__":
    run()
