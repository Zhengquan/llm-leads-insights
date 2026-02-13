# -*- coding: utf-8 -*-
"""
数据分析层：在关联层之上打标 is_ai、is_llm、llm_layer（算力/模型/平台/应用）。
不修改上游列，仅新增分析用列。
"""
import pandas as pd

from analysis_config import (
    L1_KEYWORDS,
    L1_EXCLUDE_PATTERN,
    L2_KEYWORDS,
    L3_SUANLI,
    L3_MODEL,
    L3_PLATFORM,
    L3_APP,
    LAYER_ORDER,
)


def _search(pat, s):
    if not s or not isinstance(s, str):
        return False
    return bool(pat.search(s))


def is_ai(text: str) -> bool:
    """L1：是否 AI 项目。排除仅「人工智能」+ 装修/支行/小镇等。"""
    if not text or not isinstance(text, str):
        return False
    if not L1_KEYWORDS.search(text):
        return False
    # 仅当命中「人工智能」且含排除词时排除
    if "人工智能" in text and L1_EXCLUDE_PATTERN.search(text):
        if not L2_KEYWORDS.search(text) and "大模型" not in text and "平台" not in text and "建设" not in text:
            return False
    return True


def is_llm(text: str) -> bool:
    """L2：是否大模型项目。"""
    return _search(L2_KEYWORDS, text)


def primary_layer(text: str) -> str:
    """L3：主层级，优先级 应用 > 平台 > 模型 > 算力。未命中任一层返回「未分类」。"""
    if not text or not isinstance(text, str):
        return "未分类"
    for layer in LAYER_ORDER:
        if layer == "应用" and _search(L3_APP, text):
            return "应用"
        if layer == "平台" and _search(L3_PLATFORM, text):
            return "平台"
        if layer == "模型" and _search(L3_MODEL, text):
            return "模型"
        if layer == "算力" and _search(L3_SUANLI, text):
            return "算力"
    return "未分类"


def apply_analysis(
    df: pd.DataFrame,
    name_col: str = "项目名称",
    core_col: str = "project_name_core",
) -> pd.DataFrame:
    """
    对 DataFrame 每行打标 is_ai、is_llm、llm_layer。
    匹配文本 = 项目名称 + 空格 + project_name_core。
    """
    df = df.copy()
    text = (df[name_col].fillna("").astype(str) + " " + df[core_col].fillna("").astype(str)).str.strip()
    df["is_ai"] = text.map(is_ai)
    df["is_llm"] = text.map(is_llm)
    # llm_layer：仅对 is_llm 为 True 的打层级，否则空或「未分类」
    layer = text.map(primary_layer)
    df["llm_layer"] = layer.where(df["is_llm"], "未分类")
    return df
