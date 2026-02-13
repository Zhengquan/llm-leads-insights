# -*- coding: utf-8 -*-
"""
项目分组层：读取清洗层 data_cleaned/tender_cleaned.csv，
在保留全部原有列的基础上新增 project_id、tender_round，写出到 data_grouped/。
不读取、不修改 data/ 或 data_cleaned/ 中的原始/清洗文件内容，仅追加分组字段后写入新目录。
"""
import os
import re
import pandas as pd
from tender_group import assign_project_ids

CLEANED_DIR = "data_cleaned"
GROUPED_DIR = "data_grouped"
CLEANED_FILE = "tender_cleaned.csv"


def run():
    cleaned_path = os.path.join(CLEANED_DIR, CLEANED_FILE)
    if not os.path.isfile(cleaned_path):
        print(f"未找到清洗层文件 {cleaned_path}，请先执行 run_clean.py")
        return

    df = pd.read_csv(cleaned_path, encoding="utf-8-sig")
    project_ids, tender_rounds = assign_project_ids(
        df,
        customer_col="customer",
        project_name_core_col="project_name_core",
    )
    df = df.copy()
    df["project_id"] = project_ids
    df["tender_round"] = tender_rounds

    os.makedirs(GROUPED_DIR, exist_ok=True)
    out_path = os.path.join(GROUPED_DIR, "tender_grouped.csv")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"已写入 {out_path}，共 {len(df)} 条（保留清洗层全部列 + project_id, tender_round）")

    # 按客户写出分组后 CSV（与清洗层结构对应，仅多两列）
    for customer in df["customer"].unique():
        sub = df[df["customer"] == customer]
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", str(customer))[:80]
        sub.to_csv(
            os.path.join(GROUPED_DIR, f"{safe_name}.csv"),
            index=False,
            encoding="utf-8-sig",
        )
    print(f"已按客户写出 {df['customer'].nunique()} 个 CSV 到 {GROUPED_DIR}/")
    print(f"项目组数（去重 project_id）: {df['project_id'].nunique()}")


if __name__ == "__main__":
    run()
