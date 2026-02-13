# -*- coding: utf-8 -*-
"""
招投标分析看板：基于 data_analysis/tender_analysis.csv 的交互式可视化。
支持按年度趋势、项目类型、层级、客户等筛选与汇总。
运行: streamlit run app_dashboard.py
"""
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ANALYSIS_DIR = "data_analysis"
ANALYSIS_FILE = "tender_analysis.csv"


@st.cache_data
def load_data():
    path = os.path.join(ANALYSIS_DIR, ANALYSIS_FILE)
    if not os.path.isfile(path):
        return None
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["发布日期"] = pd.to_datetime(df["发布日期"], errors="coerce")
    df["year"] = df["发布日期"].dt.year
    return df


def main():
    st.set_page_config(page_title="招投标分析看板", page_icon="📊", layout="wide")
    st.title("招投标数据分析看板")
    st.caption("数据来源：分析层 tender_analysis.csv，支持按年度、类型、层级、客户筛选与下钻")

    df = load_data()
    if df is None:
        st.error(f"未找到 {ANALYSIS_DIR}/{ANALYSIS_FILE}，请先执行 run_analysis.py")
        return

    # ----- 侧边栏筛选 -----
    st.sidebar.header("筛选条件")
    years = sorted(df["year"].dropna().astype(int).unique().tolist())
    if not years:
        years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
    year_range = st.sidebar.select_slider(
        "年份范围",
        options=years,
        value=(min(years), max(years)),
    )
    only_llm = st.sidebar.checkbox("仅大模型项目 (is_llm)", False)
    only_ai = st.sidebar.checkbox("仅 AI 项目 (is_ai)", False)

    customers = ["全部"] + sorted(df["customer"].dropna().unique().astype(str).tolist())
    sel_customer = st.sidebar.multiselect("客户", customers, default=["全部"])
    record_types = ["全部"] + sorted(df["record_type"].dropna().unique().astype(str).tolist())
    sel_record_type = st.sidebar.multiselect("记录类型 (record_type)", record_types, default=["全部"])
    layer_options = ["全部"] + [x for x in ["应用", "平台", "模型", "算力", "未分类"] if (df["llm_layer"] == x).any()]
    sel_layer = st.sidebar.multiselect("层级 (llm_layer)", layer_options, default=["全部"])
    link_options = ["全部"] + sorted(df["link_type"].dropna().unique().astype(str).tolist())
    sel_link = st.sidebar.multiselect("关联类型 (link_type)", link_options, default=["全部"])

    # 应用筛选
    year_min, year_max = year_range[0], year_range[1]
    d = df[(df["year"] >= year_min) & (df["year"] <= year_max)].copy()
    if only_llm:
        d = d[d["is_llm"] == True]
    if only_ai:
        d = d[d["is_ai"] == True]
    if "全部" not in sel_customer:
        d = d[d["customer"].astype(str).isin(sel_customer)]
    if "全部" not in sel_record_type:
        d = d[d["record_type"].astype(str).isin(sel_record_type)]
    if "全部" not in sel_layer:
        d = d[d["llm_layer"].astype(str).isin(sel_layer)]
    if "全部" not in sel_link:
        d = d[d["link_type"].astype(str).isin(sel_link)]

    # 指标卡
    n_rec = len(d)
    n_proj = d["project_id"].nunique()
    st.sidebar.metric("当前筛选记录数", n_rec)
    st.sidebar.metric("当前筛选项目数", n_proj)

    if d.empty:
        st.warning("当前筛选条件下无数据，请放宽筛选条件。")
        return

    # ----- 主区域：多 Tab -----
    tab_trend, tab_type, tab_layer, tab_customer, tab_detail = st.tabs(
        ["年度趋势", "项目类型", "层级分布", "客户分布", "明细表"]
    )

    with tab_trend:
        st.subheader("按年度趋势")
        col1, col2 = st.columns(2)
        with col1:
            metric_trend = st.radio("统计口径", ["记录数", "项目数(project_id 去重)"], horizontal=True)
        with col2:
            split_trend = st.selectbox(
                "趋势拆分（可选）",
                ["不拆分", "按是否大模型", "按层级(llm_layer)", "按记录类型(record_type)"],
            )
        if metric_trend == "项目数(project_id 去重)":
            agg = d.groupby("year")["project_id"].nunique().reset_index(name="count")
        else:
            agg = d.groupby("year").size().reset_index(name="count")
        if split_trend == "不拆分":
            fig = px.line(agg, x="year", y="count", markers=True, title="年度数量趋势")
        else:
            if split_trend == "按是否大模型":
                d["_split"] = d["is_llm"].map({True: "大模型", False: "非大模型"})
            elif split_trend == "按层级(llm_layer)":
                d["_split"] = d["llm_layer"]
            else:
                d["_split"] = d["record_type"]
            if metric_trend == "项目数(project_id 去重)":
                agg2 = d.groupby(["year", "_split"])["project_id"].nunique().reset_index(name="count")
            else:
                agg2 = d.groupby(["year", "_split"]).size().reset_index(name="count")
            fig = px.line(agg2, x="year", y="count", color="_split", markers=True, title="年度趋势（按维度拆分）")
        fig.update_layout(xaxis_title="年份", yaxis_title="数量", legend_title="")
        st.plotly_chart(fig, use_container_width=True)

    with tab_type:
        st.subheader("按项目类型 (record_type)")
        by_type = d.groupby("record_type", dropna=False).size().reset_index(name="count")
        by_type = by_type.sort_values("count", ascending=True)
        fig = px.bar(by_type, x="count", y="record_type", orientation="h", title="记录类型分布")
        fig.update_layout(xaxis_title="数量", yaxis_title="记录类型")
        st.plotly_chart(fig, use_container_width=True)
        col_pie, col_table = st.columns(2)
        with col_pie:
            fig_pie = px.pie(by_type, values="count", names="record_type", title="占比")
            st.plotly_chart(fig_pie, use_container_width=True)
        with col_table:
            st.dataframe(by_type.set_index("record_type"), use_container_width=True)

    with tab_layer:
        st.subheader("按层级 (llm_layer)")
        by_layer = d.groupby("llm_layer", dropna=False).size().reset_index(name="count")
        by_layer = by_layer.sort_values("count", ascending=True)
        fig = px.bar(by_layer, x="count", y="llm_layer", orientation="h", title="层级分布")
        fig.update_layout(xaxis_title="数量", yaxis_title="层级")
        st.plotly_chart(fig, use_container_width=True)
        # 仅大模型时展示层级×年度 热力
        if d["is_llm"].any():
            cross = d[d["is_llm"]].groupby(["year", "llm_layer"]).size().reset_index(name="count")
            pivot = cross.pivot(index="llm_layer", columns="year", values="count").fillna(0)
            st.subheader("大模型项目：层级 × 年度")
            fig_heat = px.imshow(pivot, text_auto=".0f", aspect="auto", title="层级 × 年份 数量")
            st.plotly_chart(fig_heat, use_container_width=True)

    with tab_customer:
        st.subheader("按客户 (customer)")
        top_n = st.slider("展示前 N 个客户", 5, 30, 15)
        by_cust = d.groupby("customer").size().reset_index(name="count").sort_values("count", ascending=False).head(top_n)
        fig = px.bar(by_cust, x="count", y="customer", orientation="h", title=f"客户记录数 Top {top_n}")
        fig.update_layout(xaxis_title="数量", yaxis_title="客户")
        st.plotly_chart(fig, use_container_width=True)
        # 客户 × 层级（仅大模型）
        if d["is_llm"].any():
            cust_layer = d[d["is_llm"]].groupby(["customer", "llm_layer"]).size().reset_index(name="count")
            cust_layer_wide = cust_layer.pivot(index="customer", columns="llm_layer", values="count").fillna(0)
            st.subheader("大模型项目：客户 × 层级")
            st.dataframe(cust_layer_wide.head(20), use_container_width=True)

    with tab_detail:
        st.subheader("明细数据")
        display_cols = ["项目名称", "发布日期", "customer", "record_type", "llm_layer", "is_ai", "is_llm", "link_type", "中标单位", "amount_wan_yuan"]
        display_cols = [c for c in display_cols if c in d.columns]
        st.dataframe(d[display_cols].sort_values("发布日期", ascending=False), use_container_width=True, height=400)

    st.sidebar.divider()
    st.sidebar.caption("运行 run_analysis.py 可更新分析层数据后刷新本页")
    # 导出当前筛选结果为 CSV
    buf = d.to_csv(index=False, encoding="utf-8-sig")
    st.sidebar.download_button("下载当前筛选结果 (CSV)", buf, file_name="tender_filtered.csv", mime="text/csv")


if __name__ == "__main__":
    main()
