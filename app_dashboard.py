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

# 中标类记录类型：有中标金额时优先取此类
BID_RECORD_TYPES = {"中标公告", "中标候选人公示", "成交结果", "成交公告", "结果公示"}


def get_project_amounts(d: pd.DataFrame) -> pd.DataFrame:
    """
    按项目维度计算金额，每个项目只取一条金额；有中标类记录且该条有金额时优先用中标金额。
    返回 DataFrame：project_id, amount_wan_yuan, year, customer, llm_layer（一行一项目，仅含有效金额的项目）。
    """
    if "_amount" not in d.columns or "_has_amount" not in d.columns:
        return pd.DataFrame(columns=["project_id", "amount_wan_yuan", "year", "customer", "llm_layer"])
    has_amt = d[d["_has_amount"]].copy()
    if has_amt.empty:
        return pd.DataFrame(columns=["project_id", "amount_wan_yuan", "year", "customer", "llm_layer"])
    has_amt["_is_bid"] = has_amt["record_type"].astype(str).isin(BID_RECORD_TYPES)
    # 每组 project_id：先选中标类有金额的，再选任意有金额的；取第一条
    has_amt = has_amt.sort_values(["_is_bid", "发布日期"], ascending=[False, True])
    first_per_project = has_amt.groupby("project_id", as_index=False).first()
    out = first_per_project[["project_id", "_amount", "year", "customer", "llm_layer"]].copy()
    out = out.rename(columns={"_amount": "amount_wan_yuan"})
    return out


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

    if d.empty:
        st.warning("当前筛选条件下无数据，请放宽筛选条件。")
        return

    # 金额列：统一为数值型，缺失用 NaN（需在 get_project_amounts 前计算）
    if "amount_wan_yuan" in d.columns:
        d["_amount"] = pd.to_numeric(d["amount_wan_yuan"], errors="coerce")
    else:
        d["_amount"] = float("nan")
    d["_has_amount"] = d["_amount"].notna() & (d["_amount"] > 0)

    # 指标卡
    n_rec = len(d)
    n_proj = d["project_id"].nunique()
    st.sidebar.metric("当前筛选记录数", n_rec)
    st.sidebar.metric("当前筛选项目数", n_proj)
    project_amt = get_project_amounts(d)
    if not project_amt.empty:
        st.sidebar.metric("当前筛选总金额(万元)", f"{project_amt['amount_wan_yuan'].sum():,.0f}")

    # ----- 主区域：多 Tab -----
    tab_trend, tab_type, tab_layer, tab_customer, tab_amount, tab_track, tab_detail = st.tabs(
        ["年度趋势", "项目类型", "层级分布", "客户分布", "金额分析", "项目追踪", "明细表"]
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

    with tab_amount:
        st.subheader("金额分析")
        st.caption("按项目维度汇总，每个项目只计一次金额；有中标金额时优先取中标类记录的金额。")
        if project_amt.empty:
            st.info("当前筛选下无有效金额数据（无项目具备 amount_wan_yuan 有效值）。")
        else:
            n_proj_total = d["project_id"].nunique()
            n_proj_with_amt = len(project_amt)
            total_wan = project_amt["amount_wan_yuan"].sum()
            avg_wan = total_wan / n_proj_with_amt if n_proj_with_amt else 0
            missing_pct = (1 - n_proj_with_amt / n_proj_total) * 100 if n_proj_total else 0
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("有金额项目数", f"{n_proj_with_amt:,}")
            c2.metric("总金额(万元)", f"{total_wan:,.0f}")
            c3.metric("平均金额(万元/项目)", f"{avg_wan:,.1f}")
            c4.metric("金额缺失率", f"{missing_pct:.1f}%")

            st.subheader("按年度金额趋势（项目维度）")
            by_year = project_amt.groupby("year")["amount_wan_yuan"].agg(["sum", "count", "mean"]).reset_index()
            by_year.columns = ["year", "总金额_万元", "有金额项目数", "平均金额_万元"]
            fig_amt = px.bar(by_year, x="year", y="总金额_万元", title="年度总金额(万元)")
            fig_amt.update_layout(xaxis_title="年份", yaxis_title="总金额(万元)")
            st.plotly_chart(fig_amt, use_container_width=True)
            fig_cnt = px.bar(by_year, x="year", y="有金额项目数", title="年度有金额项目数")
            fig_cnt.update_layout(xaxis_title="年份", yaxis_title="项目数")
            st.plotly_chart(fig_cnt, use_container_width=True)

            st.subheader("按客户金额汇总（项目维度）")
            top_cust = st.slider("客户金额 Top N", 5, 25, 10, key="amt_cust")
            by_cust_amt = project_amt.groupby("customer")["amount_wan_yuan"].agg(["sum", "count", "mean"]).reset_index()
            by_cust_amt.columns = ["customer", "总金额_万元", "有金额项目数", "平均金额_万元"]
            by_cust_amt = by_cust_amt.sort_values("总金额_万元", ascending=False).head(top_cust)
            fig_cust = px.bar(by_cust_amt, x="总金额_万元", y="customer", orientation="h", title=f"客户总金额 Top {top_cust}(万元)")
            st.plotly_chart(fig_cust, use_container_width=True)
            st.dataframe(by_cust_amt.set_index("customer"), use_container_width=True)

            if d["is_llm"].any():
                st.subheader("大模型项目：按层级金额（项目维度）")
                llm_projects = d[d["is_llm"]]["project_id"].unique()
                pa_llm = project_amt[project_amt["project_id"].isin(llm_projects)]
                if not pa_llm.empty:
                    by_layer_amt = pa_llm.groupby("llm_layer")["amount_wan_yuan"].agg(["sum", "count", "mean"]).reset_index()
                    by_layer_amt.columns = ["层级", "总金额_万元", "项目数", "平均_万元"]
                    fig_layer = px.bar(by_layer_amt, x="层级", y="总金额_万元", title="大模型项目按层级总金额(万元)")
                    st.plotly_chart(fig_layer, use_container_width=True)
                    st.dataframe(by_layer_amt.set_index("层级"), use_container_width=True)

            st.subheader("单项目金额分布(万元)")
            fig_hist = px.histogram(project_amt, x="amount_wan_yuan", nbins=50, title="每项目取一条金额的分布")
            fig_hist.update_layout(xaxis_title="金额(万元)", yaxis_title="项目数")
            st.plotly_chart(fig_hist, use_container_width=True)

    with tab_track:
        st.subheader("项目视角：招投标追踪")
        st.caption("选择项目后查看该项目的招标时间、中标单位与中标时间等时间线；已关联的招标-中标将成对展示。")
        projects = d.groupby("project_id").agg(
            项目名=("project_name_core", "first"),
            客户=("customer", "first"),
            记录数=("project_id", "count"),
        ).reset_index()
        projects["_label"] = projects.apply(
            lambda r: f"{r['项目名'] or r['project_id']} ({r['客户']}) · {r['记录数']}条",
            axis=1,
        )
        options = projects["project_id"].tolist()
        if not options:
            st.info("当前筛选下无项目。")
        else:
            proj_idx = projects.set_index("project_id")
            pid = st.selectbox(
                "选择项目",
                options=options,
                format_func=lambda x: proj_idx.loc[x, "_label"] if x in proj_idx.index else str(x),
                key="track_project",
            )
            proj_d = d[d["project_id"] == pid].copy()
            proj_d = proj_d.sort_values("发布日期", ascending=True).reset_index(drop=True)
            # 招标-中标配对表（仅已关联）
            linked = proj_d[proj_d["link_type"] == "已关联"].copy()
            has_tender_id = linked["related_tender_id"].astype(str).str.len() > 0
            linked = linked[has_tender_id]
            row_to_tender = proj_d.set_index("row_id") if "row_id" in proj_d.columns else pd.DataFrame()
            pairs = []
            if "row_id" in proj_d.columns and not linked.empty and not row_to_tender.empty:
                for _, bid_row in linked.iterrows():
                    tid = bid_row.get("related_tender_id")
                    if pd.isna(tid) or not tid:
                        continue
                    tender = row_to_tender.loc[row_to_tender.index == tid]
                    if tender.empty:
                        continue
                    tender = tender.iloc[0]
                    tender_date = tender.get("发布日期", "")
                    tender_org = tender.get("招采单位", "") or tender.get("采购单位", "") or ""
                    bid_date = bid_row.get("发布日期", "")
                    bid_org = bid_row.get("中标单位", "") or ""
                    amt = bid_row.get("amount_wan_yuan", "")
                    pairs.append({
                        "招标日期": tender_date,
                        "招采单位": tender_org,
                        "中标日期": bid_date,
                        "中标单位": bid_org,
                        "中标金额(万元)": amt,
                    })
            if pairs:
                st.subheader("招标-中标配对（已关联）")
                st.dataframe(pd.DataFrame(pairs), use_container_width=True)
            # 时间线可视化：按日期排序的全部记录
            st.subheader("时间线（全部记录）")
            tl = proj_d.copy()
            tl["发布日期"] = pd.to_datetime(tl["发布日期"], errors="coerce")
            tl = tl.dropna(subset=["发布日期"]).sort_values("发布日期").reset_index(drop=True)
            if tl.empty:
                st.caption("无有效发布日期，无法绘制时间线。")
            else:
                # 同一天多条时错开 y，避免完全重叠
                tl["_y"] = tl["发布日期"].copy()
                same_day_rank = tl.groupby(tl["_y"].dt.normalize()).cumcount()
                tl["_y"] = tl["_y"] + same_day_rank * pd.Timedelta(hours=2)
                # 悬停文案
                def _hover(row):
                    parts = [f"<b>{row['发布日期'].strftime('%Y-%m-%d') if hasattr(row['发布日期'], 'strftime') else row['发布日期']}</b>", f"类型: {row.get('record_type', '')}", f"关联: {row.get('link_type', '')}"]
                    if row.get("招采单位") and pd.notna(row.get("招采单位")):
                        parts.append(f"招采单位: {row['招采单位']}")
                    if row.get("中标单位") and pd.notna(row.get("中标单位")):
                        parts.append(f"中标单位: {row['中标单位']}")
                    if row.get("amount_wan_yuan") and pd.notna(row.get("amount_wan_yuan")):
                        parts.append(f"金额: {row['amount_wan_yuan']} 万元")
                    return "<br>".join(parts)
                tl["_hover"] = tl.apply(_hover, axis=1)
                # 类型配色
                type_order = ["招标公告", "采购公告", "竞争性谈判", "竞争性磋商", "询价", "中标公告", "中标候选人公示", "成交结果", "成交公告", "结果公示", "其他"]
                uniq_types = tl["record_type"].dropna().unique().tolist()
                type_palette = px.colors.qualitative.Set2
                color_map = {t: type_palette[i % len(type_palette)] for i, t in enumerate(type_order) if t in uniq_types}
                color_map.update({t: type_palette[(len(color_map) + i) % len(type_palette)] for i, t in enumerate(uniq_types) if t not in color_map})
                fig_tl = go.Figure()
                y_min, y_max = tl["_y"].min(), tl["_y"].max()
                fig_tl.add_shape(type="line", x0=0, y0=y_min, x1=0, y1=y_max, line=dict(color="rgba(0,0,0,0.3)", width=2))
                for rtype in tl["record_type"].dropna().unique():
                    sub = tl[tl["record_type"] == rtype]
                    fig_tl.add_trace(go.Scatter(
                        x=[0] * len(sub),
                        y=sub["_y"],
                        mode="markers+text",
                        marker=dict(size=14, color=color_map.get(rtype, "#888"), symbol="circle", line=dict(width=1, color="white")),
                        text=sub["record_type"],
                        textposition="middle right",
                        textfont=dict(size=11),
                        customdata=sub["_hover"],
                        hovertemplate="%{customdata}<extra></extra>",
                        name=rtype,
                        legendgroup=rtype,
                    ))
                fig_tl.update_layout(
                    title="",
                    xaxis=dict(showticklabels=False, zeroline=False, range=[-0.15, 1.2]),
                    yaxis=dict(type="date", title="发布日期", gridcolor="rgba(0,0,0,0.06)"),
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                    margin=dict(l=60, r=120),
                    height=400,
                    hovermode="closest",
                )
                st.plotly_chart(fig_tl, use_container_width=True)
                # 下方保留表格便于复制
                with st.expander("查看时间线数据表"):
                    timeline_cols = ["发布日期", "record_type", "link_type"]
                    if "招采单位" in proj_d.columns:
                        timeline_cols.append("招采单位")
                    if "中标单位" in proj_d.columns:
                        timeline_cols.append("中标单位")
                    if "amount_wan_yuan" in proj_d.columns:
                        timeline_cols.append("amount_wan_yuan")
                    timeline_cols = [c for c in timeline_cols if c in proj_d.columns]
                    show = proj_d[timeline_cols].copy()
                    show = show.rename(columns={"amount_wan_yuan": "金额(万元)", "record_type": "类型", "link_type": "关联"})
                    st.dataframe(show.sort_values("发布日期", ascending=True), use_container_width=True)

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
