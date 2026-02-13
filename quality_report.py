# -*- coding: utf-8 -*-
"""
数据质量报告：金额缺失率、单位分布、项目内招标/中标条数、project_name_core 空/过短比例。
供规则微调（相似度阈值、轮次正则等）参考。
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

from tender_link import TENDER_RECORD_TYPES, BID_RECORD_TYPES

# project_name_core 过短阈值（字符数）
CORE_NAME_MIN_LEN = 5


def _ensure_bool_missing(df: pd.DataFrame) -> pd.Series:
    """amount_is_missing 可能为字符串或布尔，统一为 True/False。"""
    s = df.get("amount_is_missing")
    if s is None:
        return pd.Series(True, index=df.index)
    if s.dtype == bool:
        return s
    return s.astype(str).str.strip().str.lower().isin(("true", "1", "yes"))


def amount_missing_by_customer(df: pd.DataFrame) -> pd.DataFrame:
    """各客户：金额缺失率、记录数。"""
    work = df.assign(_missing=_ensure_bool_missing(df))
    g = work.groupby("customer", dropna=False).agg(
        total=("customer", "count"),
        missing=("_missing", "sum"),
    ).reset_index()
    g["missing_rate"] = (g["missing"] / g["total"]).round(4)
    g["missing_pct"] = (g["missing_rate"] * 100).round(2).astype(str) + "%"
    return g[["customer", "total", "missing", "missing_rate", "missing_pct"]]


def amount_missing_by_record_type(df: pd.DataFrame) -> pd.DataFrame:
    """各 record_type：金额缺失率、记录数。"""
    work = df.assign(_missing=_ensure_bool_missing(df))
    g = work.groupby("record_type", dropna=False).agg(
        total=("record_type", "count"),
        missing=("_missing", "sum"),
    ).reset_index()
    g["missing_rate"] = (g["missing"] / g["total"]).round(4)
    g["missing_pct"] = (g["missing_rate"] * 100).round(2).astype(str) + "%"
    return g[["record_type", "total", "missing", "missing_rate", "missing_pct"]]


def amount_unit_by_customer(df: pd.DataFrame) -> pd.DataFrame:
    """各客户：amount_unit_detected 分布（万元/元/未知 数量）。"""
    unit = df.get("amount_unit_detected")
    if unit is None:
        return pd.DataFrame(columns=["customer", "unit", "count"])
    unit = unit.astype(str).fillna("未知")
    g = df.assign(unit=unit).groupby(["customer", "unit"], dropna=False).size().reset_index(name="count")
    pivot = g.pivot(index="customer", columns="unit", values="count").fillna(0).astype(int)
    return pivot.reset_index()


def amount_unit_by_record_type(df: pd.DataFrame) -> pd.DataFrame:
    """各 record_type：amount_unit_detected 分布。"""
    unit = df.get("amount_unit_detected")
    if unit is None:
        return pd.DataFrame(columns=["record_type", "unit", "count"])
    unit = unit.astype(str).fillna("未知")
    g = df.assign(unit=unit).groupby(["record_type", "unit"], dropna=False).size().reset_index(name="count")
    pivot = g.pivot(index="record_type", columns="unit", values="count").fillna(0).astype(int)
    return pivot.reset_index()


def project_tender_bid_balance(df: pd.DataFrame) -> pd.DataFrame:
    """
    同一 project_id 下招标条数 vs 中标条数。
    若存在 link_type，用其区分；否则用 record_type 是否在 招标类/中标类。
    """
    if "project_id" not in df.columns:
        return pd.DataFrame(columns=["project_id", "tender_count", "bid_count", "other_count", "balance_note"])

    record_type = df.get("record_type", pd.Series("", index=df.index)).astype(str)
    work = df.assign(
        _is_tender=record_type.isin(TENDER_RECORD_TYPES),
        _is_bid=record_type.isin(BID_RECORD_TYPES),
    )
    g = work.groupby("project_id", dropna=False).agg(
        tender_count=("_is_tender", "sum"),
        bid_count=("_is_bid", "sum"),
        total=("project_id", "count"),
    ).reset_index()
    g["other_count"] = g["total"] - g["tender_count"] - g["bid_count"]

    def note(row):
        t, b = row["tender_count"], row["bid_count"]
        if t == 0 and b > 0:
            return "仅有中标无招标"
        if t > 0 and b == 0:
            return "仅有招标无中标"
        if t > 0 and b > 0:
            return "招标与中标均有"
        return "无招无中"

    g["balance_note"] = g.apply(note, axis=1)
    return g[["project_id", "tender_count", "bid_count", "other_count", "balance_note"]]


def project_balance_summary(balance_df: pd.DataFrame) -> pd.DataFrame:
    """对 project_tender_bid_balance 的统计汇总：各 balance_note 数量。"""
    if balance_df.empty or "balance_note" not in balance_df.columns:
        return pd.DataFrame(columns=["balance_note", "project_count"])
    return balance_df.groupby("balance_note", dropna=False).size().reset_index(name="project_count")


def core_name_quality(df: pd.DataFrame, min_len: int = CORE_NAME_MIN_LEN) -> Dict[str, Any]:
    """
    project_name_core 为空或过短的比例。
    返回 dict: total, empty_count, short_count, empty_rate, short_rate, by_customer (DataFrame)。
    """
    core = df.get("project_name_core")
    if core is None:
        return {"total": len(df), "empty_count": 0, "short_count": 0, "empty_rate": 0.0, "short_rate": 0.0, "by_customer": pd.DataFrame()}
    core = core.astype(str).str.strip()
    total = len(df)
    empty = (core == "") | (core == "nan")
    empty_count = empty.sum()
    short = (core.str.len() > 0) & (core.str.len() < min_len) & ~empty
    short_count = short.sum()
    by_customer = df.assign(_empty=empty, _short=short).groupby("customer", dropna=False).agg(
        total=("customer", "count"),
        empty=("_empty", "sum"),
        short=("_short", "sum"),
    ).reset_index()
    by_customer["empty_rate"] = (by_customer["empty"] / by_customer["total"]).round(4)
    by_customer["short_rate"] = (by_customer["short"] / by_customer["total"]).round(4)
    return {
        "total": total,
        "empty_count": int(empty_count),
        "short_count": int(short_count),
        "empty_rate": round(empty_count / total, 4) if total else 0.0,
        "short_rate": round(short_count / total, 4) if total else 0.0,
        "by_customer": by_customer,
    }


def build_report(df: pd.DataFrame) -> str:
    """生成 Markdown 格式的简要质量报告。"""
    lines = ["# 招投标数据质量报告", ""]

    lines.append("## 1. 各客户金额缺失率")
    lines.append("")
    by_cust = amount_missing_by_customer(df)
    lines.append("```\n" + by_cust.to_string(index=False) + "\n```")
    lines.append("")

    lines.append("## 2. 各 record_type 金额缺失率")
    lines.append("")
    by_type = amount_missing_by_record_type(df)
    lines.append("```\n" + by_type.to_string(index=False) + "\n```")
    lines.append("")

    lines.append("## 3. 各客户 amount_unit_detected 分布")
    lines.append("")
    unit_cust = amount_unit_by_customer(df)
    lines.append("```\n" + unit_cust.to_string(index=False) + "\n```")
    lines.append("")

    lines.append("## 4. 各 record_type amount_unit_detected 分布")
    lines.append("")
    unit_type = amount_unit_by_record_type(df)
    lines.append("```\n" + unit_type.to_string(index=False) + "\n```")
    lines.append("")

    lines.append("## 5. 同一项目下招标条数 vs 中标条数（汇总）")
    lines.append("")
    balance = project_tender_bid_balance(df)
    summary = project_balance_summary(balance)
    lines.append("```\n" + summary.to_string(index=False) + "\n```")
    lines.append("")

    lines.append("## 6. project_name_core 空/过短比例")
    lines.append("")
    cq = core_name_quality(df)
    lines.append(f"- 总记录数: {cq['total']}")
    lines.append(f"- 为空条数: {cq['empty_count']}，占比: {cq['empty_rate']*100:.2f}%")
    lines.append(f"- 过短(<{CORE_NAME_MIN_LEN}字)条数: {cq['short_count']}，占比: {cq['short_rate']*100:.2f}%")
    lines.append("")
    if not cq["by_customer"].empty:
        lines.append("按客户:")
        lines.append("```\n" + cq["by_customer"].to_string(index=False) + "\n```")
    lines.append("")

    return "\n".join(lines)
