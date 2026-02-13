# -*- coding: utf-8 -*-
"""
项目分组：在清洗层之上，为每条记录分配 project_id 与 tender_round。
采用「规范化 + 相似度合并」：先得到 canonical_core，再按名称相似度聚类，同一簇共用一个 project_id。
"""
import re
import hashlib
from difflib import SequenceMatcher
from typing import Dict, List, Set, Tuple

# 项目编号：行首 年份-字母-数字 如 2025-ZH-0098：、2025-ZH-0015
PROJECT_CODE_PATTERN = re.compile(r"^\d{4}[-]?[A-Za-z]+[-]?\d+[：:\s]*", re.IGNORECASE)

# 中文数字 -> 阿拉伯数字
CN_NUM = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "百": 100, "十一": 11, "十二": 12, "十三": 13, "十四": 14,
    "十五": 15, "十六": 16, "十七": 17, "十八": 18, "十九": 19,
    "二十": 20, "三十": 30, "四十": 40, "五十": 50,
}
TENDER_ROUND_PATTERNS = [
    re.compile(r"[（(]第?([一二三四五六七八九十\d]+)[次批期][）)]"),
    re.compile(r"第([一二三四五六七八九十\d]+)[次批期]"),
    re.compile(r"([一二三四五六七八九十]+)[次批期]"),
]

# 相似度合并阈值，≥ 则视为同一项目
SIMILARITY_THRESHOLD = 0.88


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self.parent[rx] = ry


def _cn_to_int(s: str) -> int:
    s = str(s).strip()
    if not s:
        return 1
    if s.isdigit():
        return max(1, int(s))
    if s in CN_NUM:
        return CN_NUM[s]
    if s == "十":
        return 10
    if len(s) == 2 and s[0] in CN_NUM and s[1] == "十":
        return CN_NUM[s[0]] * 10
    if len(s) == 2 and s[0] == "十" and s[1] in CN_NUM:
        return 10 + CN_NUM[s[1]]
    return 1


def canonical_core_for_grouping(customer: str, project_name_core: str) -> str:
    """
    分组用规范 core：去掉首部项目编号、首部客户名，统一括号与空白。
    便于同一项目的多种标题写法归到同一 project_id。
    """
    if not project_name_core or not isinstance(project_name_core, str):
        return ""
    s = project_name_core.strip()
    # 去掉首部项目编号
    s = PROJECT_CODE_PATTERN.sub("", s).strip()
    # 去掉首部客户名
    if customer and isinstance(customer, str) and s.startswith(customer):
        s = s[len(customer):].strip()
    # 统一全角括号、多余空白
    s = re.sub(r"（", "(", s)
    s = re.sub(r"）", ")", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:200] if s else ""


# 前缀分桶长度：仅在同一前缀桶内做相似度比较
PREFIX_BUCKET_LEN = 8
# 长度比过滤：长度差过大直接视为不相似
MIN_LENGTH_RATIO = 0.5
# 桶内超过此数量只做精确匹配，不做相似度合并，避免大桶 O(n*rep) 过慢
MAX_BUCKET_SIZE_FOR_SIMILARITY = 80


def _similarity(a: str, b: str, _cache: Dict[Tuple[str, str], float] = None) -> float:
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    if la > lb:
        a, b, la, lb = b, a, lb, la
    if la / lb < MIN_LENGTH_RATIO:
        return 0.0
    key = (a, b)
    if _cache is not None and key in _cache:
        return _cache[key]
    # 快速路径：短串是长串子串且长度比足够则直接判相似
    if a in b and la / lb >= 0.8:
        r = 0.9
    else:
        r = SequenceMatcher(None, a, b).ratio()
    if _cache is not None and len(_cache) < 50000:
        _cache[key] = r
    return r


def _cluster_cores(unique_cores: List[str], threshold: float, sim_cache: Dict = None) -> List[Set[int]]:
    """对一组 core 做相似度聚类，返回 list of set of indices。按前缀分桶后仅在桶内聚类。"""
    from collections import defaultdict
    n = len(unique_cores)
    if n == 0:
        return []
    if n == 1:
        return [{0}]
    if sim_cache is None:
        sim_cache = {}
    # 按前缀分桶
    lengths = [len(s) for s in unique_cores if s]
    prefix_len = min(PREFIX_BUCKET_LEN, min(lengths, default=1))
    buckets = defaultdict(list)
    for i, s in enumerate(unique_cores):
        prefix = (s or "")[:prefix_len]
        buckets[prefix].append(i)
    all_clusters = []
    for bucket_indices in buckets.values():
        if not bucket_indices:
            continue
        if len(bucket_indices) > MAX_BUCKET_SIZE_FOR_SIMILARITY:
            # 大桶不跑相似度，每项单独成簇，避免过慢
            all_clusters.extend([{i} for i in bucket_indices])
            continue
        order = sorted(bucket_indices, key=lambda i: -len(unique_cores[i]))
        clusters = []
        for idx in order:
            core = unique_cores[idx]
            assigned = False
            for rep_i, members in clusters:
                if _similarity(core, unique_cores[rep_i], sim_cache) >= threshold:
                    members.add(idx)
                    assigned = True
                    break
            if not assigned:
                clusters.append((idx, {idx}))
        for _ in range(2):
            merged = False
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    if _similarity(unique_cores[clusters[i][0]], unique_cores[clusters[j][0]], sim_cache) >= threshold:
                        clusters[i][1].update(clusters[j][1])
                        clusters.pop(j)
                        merged = True
                        break
                if merged:
                    break
        all_clusters.extend([m for _, m in clusters])
    return all_clusters


def _build_customer_core_to_project_id(
    customer_cores: List[Tuple[str, str]],
    threshold: float = SIMILARITY_THRESHOLD,
) -> Dict[Tuple[str, str], str]:
    """
    对 (customer, canonical_core) 按 customer 分组，组内按前缀分桶 + 代表法聚类，
    返回 (customer, canonical_core) -> project_id。
    """
    from collections import defaultdict
    by_customer = defaultdict(list)
    for c, core in customer_cores:
        by_customer[c].append(core)
    mapping = {}
    sim_cache = {}
    for customer, cores in by_customer.items():
        unique_cores = list(dict.fromkeys(cores))
        n = len(unique_cores)
        if n == 0:
            continue
        clusters = _cluster_cores(unique_cores, threshold, sim_cache)
        for members in clusters:
            rep = max([unique_cores[i] for i in members], key=len)
            pid = make_project_id(customer, rep)
            for i in members:
                mapping[(customer, unique_cores[i])] = pid
    return mapping


def make_project_id(customer: str, project_name_core: str) -> str:
    key = f"{customer}\n{project_name_core or ''}"
    h = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    safe_customer = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]", "_", customer)[:40]
    return f"{safe_customer}_{h}"


def parse_tender_round(project_name: str) -> int:
    if not project_name or not isinstance(project_name, str):
        return 1
    s = project_name.strip()
    for pat in TENDER_ROUND_PATTERNS:
        m = pat.search(s)
        if m:
            return max(1, _cn_to_int(m.group(1)))
    return 1


def assign_project_ids(
    df,
    customer_col: str = "customer",
    project_name_core_col: str = "project_name_core",
    similarity_threshold: float = SIMILARITY_THRESHOLD,
) -> Tuple[list, list]:
    """
    对 DataFrame 每行：规范化得到 canonical_core，按 customer 内相似度合并后分配 project_id。
    返回 (project_ids, tender_rounds)，与 df 同长。
    """
    name_col = "项目名称" if "项目名称" in df.columns else None
    if name_col is None:
        name_col = [c for c in df.columns if "项目" in str(c) or "名称" in str(c)]
        name_col = name_col[0] if name_col else None

    # 列向量，避免逐行 iterrows
    cust_ser = df[customer_col].fillna("").astype(str)
    core_ser = df[project_name_core_col].fillna("").astype(str)
    customer_cores = [
        (c, canonical_core_for_grouping(c, co) or co)
        for c, co in zip(cust_ser, core_ser)
    ]
    mapping = _build_customer_core_to_project_id(customer_cores, threshold=similarity_threshold)

    project_ids = [
        mapping.get((c, k), make_project_id(c, k))
        for c, k in customer_cores
    ]
    if name_col:
        name_ser = df[name_col].fillna("").astype(str)
        tender_rounds = [parse_tender_round(n) for n in name_ser]
    else:
        tender_rounds = [1] * len(df)
    return project_ids, tender_rounds
