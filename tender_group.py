# -*- coding: utf-8 -*-
"""
项目分组：在清洗层之上，为每条记录分配 project_id 与 tender_round。
不修改清洗层字段，仅新增分组相关列。
"""
import re
import hashlib
from typing import Tuple

# 中文数字 -> 阿拉伯数字
CN_NUM = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "百": 100, "十一": 11, "十二": 12, "十三": 13, "十四": 14,
    "十五": 15, "十六": 16, "十七": 17, "十八": 18, "十九": 19,
    "二十": 20, "三十": 30, "四十": 40, "五十": 50,
}
# 轮次/批次在标题中的多种写法，按优先级匹配
TENDER_ROUND_PATTERNS = [
    # （第二次）、(第一次)、（第2次）
    re.compile(r"[（(]第?([一二三四五六七八九十\d]+)[次批期][）)]"),
    # 第2次、第1批、第二批
    re.compile(r"第([一二三四五六七八九十\d]+)[次批期]"),
    # 二次、一次、二批、一批
    re.compile(r"([一二三四五六七八九十]+)[次批期]"),
]


def _cn_to_int(s: str) -> int:
    """中文数字或阿拉伯数字串 -> int，无法解析返回 1。"""
    s = str(s).strip()
    if not s:
        return 1
    if s.isdigit():
        return max(1, int(s))
    if s in CN_NUM:
        return CN_NUM[s]
    # 十、二十等
    if s == "十":
        return 10
    if len(s) == 2 and s[0] in CN_NUM and s[1] == "十":
        return CN_NUM[s[0]] * 10  # 二十 -> 20
    if len(s) == 2 and s[0] == "十" and s[1] in CN_NUM:
        return 10 + CN_NUM[s[1]]  # 十一 -> 11
    return 1


def parse_tender_round(project_name: str) -> int:
    """
    从项目名称中解析招标轮次（第几次/第几批）。
    未匹配到则返回 1。
    """
    if not project_name or not isinstance(project_name, str):
        return 1
    s = project_name.strip()
    for pat in TENDER_ROUND_PATTERNS:
        m = pat.search(s)
        if m:
            return max(1, _cn_to_int(m.group(1)))
    return 1


def make_project_id(customer: str, project_name_core: str) -> str:
    """
    由客户 + 项目核心名生成稳定 project_id（同组同 id，跨运行一致）。
    """
    key = f"{customer}\n{project_name_core or ''}"
    h = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    safe_customer = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]", "_", customer)[:40]
    return f"{safe_customer}_{h}"


def assign_project_ids(
    df,
    customer_col: str = "customer",
    project_name_core_col: str = "project_name_core",
) -> Tuple[list, list]:
    """
    对 DataFrame 的每一行，根据 customer + project_name_core 生成 project_id。
    返回 (project_ids, tender_rounds)，与 df 同长。
    不修改 df。
    """
    project_ids = []
    tender_rounds = []
    name_col = "项目名称" if "项目名称" in df.columns else None
    if name_col is None:
        name_col = [c for c in df.columns if "项目" in str(c) or "名称" in str(c)]
        name_col = name_col[0] if name_col else None
    for _, r in df.iterrows():
        customer = r.get(customer_col, "") or ""
        core = r.get(project_name_core_col, "") or ""
        project_ids.append(make_project_id(customer, core))
        if name_col is not None:
            tender_rounds.append(parse_tender_round(r.get(name_col, "")))
        else:
            tender_rounds.append(1)
    return project_ids, tender_rounds
