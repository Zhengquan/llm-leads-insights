# -*- coding: utf-8 -*-
"""
在 data/ 下读取天眼查招投标 xlsx，执行记录类型 + 项目核心名 + 金额解析，
输出带清洗字段的 CSV 到 data_cleaned/（按客户单文件或合并均可）。
"""
import os
import re
import pandas as pd
from tender_clean import clean_row

DATA_DIR = "data"
OUT_DIR = "data_cleaned"
EXCEL_HEADER_ROW = 6  # 天眼查表头在第 7 行，0-based=6


def customer_from_filename(filename: str) -> str:
    """从文件名解析客户名：【天眼查】招投标(不包含拟建)-客户全称(流水号).xlsx"""
    m = re.match(r"【天眼查】招投标\(不包含拟建\)-(.+?)\(\d+.*\)\.xlsx", filename)
    return m.group(1).strip() if m else filename


def load_one_sheet(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, header=EXCEL_HEADER_ROW)
    df = df.dropna(how="all")
    return df


def run():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = [f for f in os.listdir(DATA_DIR) if f.endswith(".xlsx")]
    if not files:
        print("未在 data/ 下找到 xlsx 文件")
        return

    all_dfs = []
    for f in sorted(files):
        path = os.path.join(DATA_DIR, f)
        customer = customer_from_filename(f)
        df = load_one_sheet(path)
        # 列名兼容
        name_col = "项目名称" if "项目名称" in df.columns else df.columns[1]
        amount_col = "中标金额" if "中标金额" in df.columns else df.columns[5]

        rows = []
        for _, r in df.iterrows():
            extra = clean_row(
                r.get(name_col, ""),
                r.get(amount_col, ""),
            )
            rows.append(extra)
        add = pd.DataFrame(rows)
        out_df = pd.concat([df.reset_index(drop=True), add], axis=1)
        out_df["customer"] = customer
        out_df["source_file"] = f
        all_dfs.append(out_df)

    combined = pd.concat(all_dfs, ignore_index=True)
    out_path = os.path.join(OUT_DIR, "tender_cleaned.csv")
    combined.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"已写入 {out_path}，共 {len(combined)} 条")

    # 按客户各存一份（可选）
    for customer in combined["customer"].unique():
        sub = combined[combined["customer"] == customer]
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", customer)[:80]
        sub.to_csv(
            os.path.join(OUT_DIR, f"{safe_name}.csv"),
            index=False,
            encoding="utf-8-sig",
        )
    print(f"已按客户写出 {combined['customer'].nunique()} 个 CSV 到 {OUT_DIR}/")


if __name__ == "__main__":
    run()
