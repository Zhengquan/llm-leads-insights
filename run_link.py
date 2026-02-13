# -*- coding: utf-8 -*-
"""
招标–中标关联层：读取分组层 data_grouped/tender_grouped.csv，
在保留全部已有列的基础上新增 row_id、link_type、related_tender_id、related_bid_id，
并输出「项目–招标–中标」关联表到 data_linked/。
不修改 data_grouped/ 或更上层输出。
"""
import os
import re
import pandas as pd
from tender_link import assign_link, build_link_table

GROUPED_DIR = "data_grouped"
LINKED_DIR = "data_linked"
GROUPED_FILE = "tender_grouped.csv"


def run():
    grouped_path = os.path.join(GROUPED_DIR, GROUPED_FILE)
    if not os.path.isfile(grouped_path):
        print(f"未找到分组层文件 {grouped_path}，请先执行 run_group.py")
        return

    df = pd.read_csv(grouped_path, encoding="utf-8-sig")
    df = assign_link(
        df,
        project_id_col="project_id",
        record_type_col="record_type",
        date_col="发布日期",
        tender_round_col="tender_round",
    )

    os.makedirs(LINKED_DIR, exist_ok=True)
    out_path = os.path.join(LINKED_DIR, "tender_linked.csv")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"已写入 {out_path}，共 {len(df)} 条（保留分组层全部列 + row_id, link_type, related_tender_id, related_bid_id）")

    link_table = build_link_table(df)
    link_path = os.path.join(LINKED_DIR, "link_table.csv")
    link_table.to_csv(link_path, index=False, encoding="utf-8-sig")
    print(f"已写入 {link_path}，已关联对数 {len(link_table)}")

    # 按客户写出关联后 CSV
    for customer in df["customer"].unique():
        sub = df[df["customer"] == customer]
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", str(customer))[:80]
        sub.to_csv(
            os.path.join(LINKED_DIR, f"{safe_name}.csv"),
            index=False,
            encoding="utf-8-sig",
        )
    print(f"已按客户写出 {df['customer'].nunique()} 个 CSV 到 {LINKED_DIR}/")

    # 简要统计
    print("\nlink_type 分布:")
    print(df["link_type"].value_counts().to_string())


if __name__ == "__main__":
    run()
