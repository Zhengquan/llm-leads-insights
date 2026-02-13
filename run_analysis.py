# -*- coding: utf-8 -*-
"""
数据分析层：读取关联层 data_linked/tender_linked.csv，
在保留全部已有列的基础上新增 is_ai、is_llm、llm_layer，写出到 data_analysis/。
"""
import os
import re
import pandas as pd
from analysis_layer import apply_analysis

LINKED_DIR = "data_linked"
ANALYSIS_DIR = "data_analysis"
LINKED_FILE = "tender_linked.csv"


def run():
    linked_path = os.path.join(LINKED_DIR, LINKED_FILE)
    if not os.path.isfile(linked_path):
        print(f"未找到关联层文件 {linked_path}，请先执行 run_link.py")
        return

    df = pd.read_csv(linked_path, encoding="utf-8-sig")
    df = apply_analysis(
        df,
        name_col="项目名称",
        core_col="project_name_core",
    )

    os.makedirs(ANALYSIS_DIR, exist_ok=True)
    out_path = os.path.join(ANALYSIS_DIR, "tender_analysis.csv")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"已写入 {out_path}，共 {len(df)} 条（保留关联层全部列 + is_ai, is_llm, llm_layer）")

    # 按客户写出
    for customer in df["customer"].unique():
        sub = df[df["customer"] == customer]
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", str(customer))[:80]
        sub.to_csv(
            os.path.join(ANALYSIS_DIR, f"{safe_name}.csv"),
            index=False,
            encoding="utf-8-sig",
        )
    print(f"已按客户写出 {df['customer'].nunique()} 个 CSV 到 {ANALYSIS_DIR}/")

    # 简要统计（按记录）
    print("\n--- 按记录统计 ---")
    print("is_ai True:", df["is_ai"].sum())
    print("is_llm True:", df["is_llm"].sum())
    print("llm_layer 分布（仅 is_llm 行）:")
    print(df[df["is_llm"]]["llm_layer"].value_counts().to_string())
    # 按 project_id 统计（主层级取优先级最高：应用>平台>模型>算力）
    def project_primary_layer(ser):
        for layer in ("应用", "平台", "模型", "算力"):
            if (ser == layer).any():
                return layer
        return "未分类"
    g = df.groupby("project_id").agg({"is_ai": "max", "is_llm": "max", "llm_layer": project_primary_layer})
    print("\n--- 按项目(project_id)统计 ---")
    print("AI 项目数:", g["is_ai"].sum())
    print("大模型项目数:", g["is_llm"].sum())
    print("大模型项目内 llm_layer 分布:")
    print(g[g["is_llm"]]["llm_layer"].value_counts().to_string())


if __name__ == "__main__":
    run()
