# -*- coding: utf-8 -*-
"""
招投标数据清洗：记录类型、项目核心名、金额解析。
适用于天眼查导出的招投标(不包含拟建) xlsx。
"""
import re
from typing import Optional, Tuple


# 记录类型：按关键词优先级匹配
RECORD_TYPE_RULES = [
    ("中标候选人公示", "中标候选人公示"),
    ("中标公告", "中标公告"),
    ("成交结果", "成交结果"),
    ("成交公告", "成交公告"),
    ("结果公示", "结果公示"),       # 结果公示、入围结果公示等
    ("竞争性谈判", "竞争性谈判"),
    ("竞争性磋商", "竞争性磋商"),
    ("招标公告", "招标公告"),
    ("采购公告", "采购公告"),
    ("询价", "询价"),
]
DEFAULT_RECORD_TYPE = "其他"


def parse_record_type(project_name: str) -> str:
    """根据项目名称判断记录类型：招标公告 / 中标公告 / 成交结果 等。"""
    if not project_name or not isinstance(project_name, str):
        return DEFAULT_RECORD_TYPE
    s = project_name.strip()
    for keyword, label in RECORD_TYPE_RULES:
        if keyword in s:
            return label
    return DEFAULT_RECORD_TYPE


# 用于项目核心名：去掉的轮次/批次表述（保留核心业务名）
ROUND_PATTERNS = [
    re.compile(r"[（(]第?[一二三四五六七八九十百\d]+[次批期][）)]"),  # （第二次）、(第一次) 先整段去掉
    re.compile(r"[一二三四五六七八九十百]+次"),             # 一次、二次
    re.compile(r"第[一二三四五六七八九十\d]+[次批期]"),     # 第1次、第二批
    re.compile(r"[一二三四五六七八九十\d]+[批期]"),         # 一批、二批
    re.compile(r"（[一二三四五六七八九十\d]+[批期]）"),     # （一）批
    re.compile(r"\([一二三四五六七八九十\d]+[批期]\)"),     # (1)批
]
# 去掉的后缀（公告类型）
SUFFIX_PATTERNS = [
    re.compile(r"招标公告$"),
    re.compile(r"中标公告$"),
    re.compile(r"中标候选人公示$"),
    re.compile(r"成交结果公告?$"),
    re.compile(r"成交公告$"),
    re.compile(r"采购公告$"),
    re.compile(r"竞争性谈判.*$"),
    re.compile(r"竞争性磋商.*$"),
    re.compile(r"询价.*$"),
    re.compile(r"结果信息公开$"),
    re.compile(r"结果公示$"),
    re.compile(r"入围结果公示$"),
]
# 日期、编号等噪音
NOISE_PATTERNS = [
    re.compile(r"\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}"),  # 2024-05-07
    re.compile(r"\d{4}\.\d{1,2}\.\d{1,2}"),
]


def parse_project_name_core(project_name: str) -> str:
    """从项目名称提取核心名：去掉一次/二次、招标/中标等后缀，做简单归一化。"""
    if not project_name or not isinstance(project_name, str):
        return ""
    s = project_name.strip()
    if not s:
        return ""

    # 去掉轮次/批次
    for pat in ROUND_PATTERNS:
        s = pat.sub("", s)
    # 去掉公告类型后缀
    for pat in SUFFIX_PATTERNS:
        s = pat.sub("", s)
    # 去掉日期
    for pat in NOISE_PATTERNS:
        s = pat.sub("", s)

    # 统一空白、竖线等
    s = re.sub(r"[\s\|]+", " ", s)
    s = s.strip(" \-_|")
    return s[:200] if s else ""  # 截断过长


def parse_amount(raw: str) -> Tuple[Optional[float], str, bool]:
    """
    解析中标金额字符串，统一为万元。

    Returns:
        (amount_wan_yuan, unit_detected, is_missing)
        - amount_wan_yuan: 万元数值，无法解析为 None
        - unit_detected: "万元" | "元" | "未知"
        - is_missing: 是否视为缺失（空、-、无法解析）
    """
    if raw is None or (isinstance(raw, float) and (raw != raw or raw == 0)):
        return None, "未知", True
    s = str(raw).strip()
    if not s or s == "-" or s.lower() == "nan":
        return None, "未知", True

    unit_detected = "未知"
    num_str = s

    # 万元：如 94.02万元、20万元
    m_wan = re.search(r"([\d.,]+)\s*万", s)
    if m_wan:
        unit_detected = "万元"
        num_str = m_wan.group(1).replace(",", "")
        try:
            val = float(num_str)
            return round(val, 4), unit_detected, False
        except ValueError:
            return None, unit_detected, True

    # 仅元：如 1000元、1,000元（需转为万）
    m_yuan = re.search(r"([\d.,]+)\s*元", s)
    if m_yuan:
        unit_detected = "元"
        num_str = m_yuan.group(1).replace(",", "")
        try:
            val = float(num_str) / 10000.0
            return round(val, 4), unit_detected, False
        except ValueError:
            return None, unit_detected, True

    # 纯数字：无单位时按数值启发判断（< 10000 倾向认为是万，否则倾向是元）
    m_num = re.search(r"^([\d.,]+)$", s)
    if m_num:
        num_str = m_num.group(1).replace(",", "")
        try:
            val = float(num_str)
            if val > 0:
                if val < 10000:
                    return round(val, 4), "万元", False  # 假定为万
                return round(val / 10000.0, 4), "元", False  # 假定为元
        except ValueError:
            pass
    return None, "未知", True


def clean_row(project_name: str, amount_raw: str) -> dict:
    """对单条记录做三项清洗，返回新增字段字典。"""
    record_type = parse_record_type(project_name)
    project_core = parse_project_name_core(project_name)
    amount_wan, amount_unit, amount_missing = parse_amount(amount_raw)
    return {
        "record_type": record_type,
        "project_name_core": project_core,
        "amount_wan_yuan": amount_wan,
        "amount_unit_detected": amount_unit,
        "amount_is_missing": amount_missing,
    }
