# -*- coding: utf-8 -*-
"""
招标–中标关联：在同一 project_id 下，按发布日期排序，
为每条中标记录关联「前一条未配对的招标」，产出 link_type、related_tender_id、related_bid_id。
不修改分组层已有列，仅新增关联相关列。
"""
import pandas as pd
import numpy as np
from typing import List, Tuple

# 招标类：招标公告、采购公告、竞争性谈判/磋商、询价
TENDER_RECORD_TYPES = {"招标公告", "采购公告", "竞争性谈判", "竞争性磋商", "询价"}
# 中标类：中标公告、中标候选人公示、成交结果/公告、结果公示
BID_RECORD_TYPES = {"中标公告", "中标候选人公示", "成交结果", "成交公告", "结果公示"}


def _is_tender(record_type: str) -> bool:
    return record_type in TENDER_RECORD_TYPES


def _is_bid(record_type: str) -> bool:
    return record_type in BID_RECORD_TYPES


def assign_link(
    df: pd.DataFrame,
    project_id_col: str = "project_id",
    record_type_col: str = "record_type",
    date_col: str = "发布日期",
    tender_round_col: str = "tender_round",
) -> pd.DataFrame:
    """
    为每条记录分配 row_id、link_type、related_tender_id、related_bid_id。
    - 在同一 project_id 内按 发布日期、tender_round 排序，按时间顺序为每条中标找「前一条招标」配对。
    - link_type: 已关联 | 仅招标 | 仅中标
    - 中标行的 related_tender_id = 配对的招标行 row_id；招标行的 related_bid_id = 任一条配对的中标行 row_id（取第一条）。
    """
    df = df.copy()
    n = len(df)
    df["row_id"] = [f"R{i}" for i in range(n)]

    # 解析日期以便排序
    dates = pd.to_datetime(df[date_col], errors="coerce")
    df["_sort_date"] = dates
    df["_tender_round"] = df.get(tender_round_col, 1).fillna(1).astype(int)
    df["_is_tender"] = df[record_type_col].astype(str).map(_is_tender)
    df["_is_bid"] = df[record_type_col].astype(str).map(_is_bid)

    link_type = ["其他"] * n
    related_tender_id: List[str] = [""] * n
    related_bid_id: List[str] = [""] * n
    row_id_to_idx = {df["row_id"].iloc[i]: i for i in range(n)}

    # 每个 project_id 下，记录「当前最近的招标 row_id」以及「该招标已被哪些中标指向」
    last_tender_by_project = {}
    tender_has_bid = set()  # row_id of 招标 that has at least one 中标

    # 按 project_id, 日期, tender_round 排序后的索引顺序处理
    order = df.sort_values(
        [project_id_col, "_sort_date", "_tender_round"],
        na_position="last",
    ).index.tolist()

    for idx in order:
        i = row_id_to_idx[df.loc[idx, "row_id"]]
        pid = df.loc[idx, project_id_col]
        if pid not in last_tender_by_project:
            last_tender_by_project[pid] = None

        if df.loc[idx, "_is_tender"]:
            last_tender_by_project[pid] = df.loc[idx, "row_id"]
            link_type[i] = "仅招标"
            related_bid_id[i] = ""
            related_tender_id[i] = ""
        elif df.loc[idx, "_is_bid"]:
            last_tender = last_tender_by_project.get(pid)
            if last_tender is not None:
                link_type[i] = "已关联"
                related_tender_id[i] = last_tender
                related_bid_id[i] = ""
                tender_has_bid.add(last_tender)
            else:
                link_type[i] = "仅中标"
                related_tender_id[i] = ""
                related_bid_id[i] = ""
        else:
            # 其他类型不参与配对
            link_type[i] = "其他"
            related_tender_id[i] = ""
            related_bid_id[i] = ""

    df["link_type"] = link_type
    df["related_tender_id"] = related_tender_id
    df["related_bid_id"] = related_bid_id

    # 招标行：未被打过「已关联」的改为 仅招标；已关联的填 related_bid_id（任选一个指向它的中标）
    bid_to_tender = {}  # bid row_id -> tender row_id
    for i in range(n):
        if df["related_tender_id"].iloc[i]:
            bid_to_tender[df["row_id"].iloc[i]] = df["related_tender_id"].iloc[i]
    tender_to_one_bid = {}
    for bid_rid, tender_rid in bid_to_tender.items():
        if tender_rid not in tender_to_one_bid:
            tender_to_one_bid[tender_rid] = bid_rid
    for i in range(n):
        rid = df["row_id"].iloc[i]
        if df["_is_tender"].iloc[i]:
            if rid not in tender_has_bid:
                df.loc[df.index[i], "link_type"] = "仅招标"
            else:
                df.loc[df.index[i], "link_type"] = "已关联"
                df.loc[df.index[i], "related_bid_id"] = tender_to_one_bid.get(rid, "")

    # 去掉辅助列
    df.drop(columns=["_sort_date", "_tender_round", "_is_tender", "_is_bid"], inplace=True, errors="ignore")
    return df


def build_link_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    从带 link_type、related_tender_id、row_id 的 DataFrame 生成「项目–招标–中标」关联表。
    仅包含 已关联 的 (tender_row_id, bid_row_id) 对，每对一行。
    """
    linked = df[df["link_type"] == "已关联"].copy()
    bid_rows = linked[linked["related_tender_id"].astype(str).str.len() > 0]
    if bid_rows.empty:
        return pd.DataFrame(
            columns=["project_id", "tender_row_id", "bid_row_id", "tender_round", "发布日期", "中标单位", "amount_wan_yuan"]
        )
    out = pd.DataFrame({
        "project_id": bid_rows["project_id"].values,
        "tender_row_id": bid_rows["related_tender_id"].values,
        "bid_row_id": bid_rows["row_id"].values,
        "tender_round": bid_rows.get("tender_round", np.nan),
        "发布日期": bid_rows["发布日期"].values,
        "中标单位": bid_rows.get("中标单位", "").values,
        "amount_wan_yuan": bid_rows.get("amount_wan_yuan", np.nan).values,
    })
    return out
