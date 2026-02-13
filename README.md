# LLM Leads Insights

招投标数据流水线与看板：面向天眼查导出的银行招投标 xlsx，完成清洗、项目分组、招标–中标关联、AI/大模型打标与可视化分析。

---

## 目录

- [环境与依赖](#环境与依赖)
- [数据与目录结构](#数据与目录结构)
- [流水线与运行方式](#流水线与运行方式)
- [看板](#看板)
- [文件说明](#文件说明)
- [复杂逻辑解读](#复杂逻辑解读)

---

## 环境与依赖

- Python 3.8+
- 依赖见 `requirements.txt`：

```
pandas>=1.5.0
openpyxl>=3.0.0
streamlit>=1.28.0
plotly>=5.18.0
```

安装：`pip install -r requirements.txt`

---

## 数据与目录结构

- **原始数据**：`data/*.xlsx`（天眼查招投标导出，表头通常在第 7 行，列含：项目名称、发布日期、招采单位、中标单位、中标金额等）
- **中间产出**（由流水线生成，可被 `run_pipeline.py` 清理）：
  - `data_cleaned/` — 清洗层
  - `data_grouped/` — 分组层（含 project_id、tender_round）
  - `data_linked/` — 关联层（含 link_type、related_tender_id、related_bid_id）
  - `data_analysis/` — 分析层（含 is_ai、is_llm、llm_layer）
  - `data_quality/` — 质量报告（report.md 等）

流水线**不会**修改 `data/`，仅读写上述中间目录。

---

## 流水线与运行方式

**一键全量（默认先清理再跑）：**

```bash
python run_pipeline.py
```

**不清理、仅重跑各步（覆盖已有产出）：**

```bash
python run_pipeline.py --no-clean
```

**分步执行：**

```bash
python run_clean.py      # 1. 清洗
python run_group.py      # 2. 分组
python run_link.py       # 3. 关联
python run_analysis.py   # 4. 分析
python run_quality_report.py  # 5. 质量报告
```

---

## 看板

基于分析层 `data_analysis/tender_analysis.csv` 的交互式看板：

```bash
streamlit run app_dashboard.py
```

功能概览：

- **筛选**：年份、是否大模型/AI、客户、记录类型、层级、关联类型、**供应商（中标单位）**
- **Tab**：年度趋势、项目类型、层级分布、客户分布（含大模型客户×层级、客户×项目 Top5）、金额分析（项目维度、中标优先）、**项目追踪**（时间线+招标-中标配对）、明细表
- **金额口径**：按**项目**汇总，每项目只计一条金额，**有中标金额时优先取中标金额**
- **项目追踪**：选择项目后查看招标-中标配对表与时间线图

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `run_pipeline.py` | 流水线入口：清洗→分组→关联→分析→质量报告 |
| `run_clean.py` / `tender_clean.py` | 清洗：record_type、project_name_core、amount_wan_yuan |
| `run_group.py` / `tender_group.py` | 分组：canonical_core、相似度聚类、project_id、tender_round |
| `run_link.py` / `tender_link.py` | 关联：同一 project_id 内招标-中标按时间配对 |
| `run_analysis.py` / `analysis_layer.py` / `analysis_config.py` | 分析：is_ai、is_llm、llm_layer |
| `run_quality_report.py` / `quality_report.py` | 质量报告：金额缺失率、单位分布、项目内招标/中标等 |
| `app_dashboard.py` | Streamlit 看板与项目级金额逻辑 |

---

## 复杂逻辑解读

以下结合代码与示例说明项目中较复杂的实现，便于维护与二次开发。

---

### 1. 清洗层：记录类型与项目核心名（tender_clean.py）

**目标**：从原始「项目名称」得到 `record_type`（招标/中标/其他）和 `project_name_core`（去掉轮次、公告后缀、日期后的业务名）。

**记录类型（按优先级匹配）**

```python
# tender_clean.py 第 11-34 行
RECORD_TYPE_RULES = [
    ("中标候选人公示", "中标候选人公示"),
    ("中标公告", "中标公告"),
    ...
    ("招标公告", "招标公告"),
    ("采购公告", "采购公告"),
    ("询价", "询价"),
]
# parse_record_type：按顺序若 keyword in s 则返回对应 label，否则 "其他"
```

**要点**：顺序决定优先级。例如「XX 中标候选人公示」会命中「中标候选人公示」而不是「中标公告」。

**项目核心名（三阶段去掉噪音）**

- 先去掉**轮次/批次**（ROUND_PATTERNS）：如「（第二次）」「第1次」「一批」
- 再去掉**公告类型后缀**（SUFFIX_PATTERNS）：如「招标公告」「结果公示」「**评审结果公示**」「**征询变更公告**」
- 最后去掉**日期**（NOISE_PATTERNS），并统一空白、截断 200 字

**示例**：

| 原始项目名称 | record_type | project_name_core（示意） |
|--------------|-------------|---------------------------|
| 中国民生银行深度学习大模型训练与推理平台软件采购**评审结果公示** | 结果公示 | 中国民生银行…软件采购 |
| 中国民生银行深度学习大模型训练与推理平台软件采购**征询变更公告** | 其他 | 中国民生银行…软件采购 |

若「评审结果公示」不单独写在前，只写「结果公示」，则第一条会留下「评审」，两条 core 不一致，分组会拆成两个项目；因此 SUFFIX 里**长、具体后缀要写在短的前面**。

---

### 2. 分组层：规范化 + 相似度聚类（tender_group.py）

**目标**：把同一客户下「写法不同但语义同一项目」的标题归到同一个 `project_id`。

**2.1 按客户分组（只在同一客户内合并）**

```python
# _build_customer_core_to_project_id（约 182-184 行）
by_customer = defaultdict(list)
for c, core in customer_cores:
    by_customer[c].append(core)
for customer, cores in by_customer.items():
    unique_cores = list(dict.fromkeys(cores))
    clusters = _cluster_cores(unique_cores, threshold, sim_cache)
```

不同客户的 core 永远不会一起聚类，因此不会跨客户合并项目。

**2.2 分组用规范 core（canonical_core_for_grouping）**

在清洗得到的 `project_name_core` 上再做一次规范化（64-80 行）：

- 去掉首部**项目编号**：`^\d{4}[-]?[A-Za-z]+[-]?\d+[：:\s]*`（如 2025-ZH-0098）
- 去掉首部**客户名**（若 core 以客户名开头）
- 全角括号→半角、多余空白规整

这样「中国民生银行股份有限公司_深度学习…」与「深度学习…」在去客户名后一致，便于后续相似度比较。

**2.3 前缀分桶（避免 O(n²) 全量比较）**

```python
# _cluster_cores（约 124-129 行）
prefix_len = min(PREFIX_BUCKET_LEN, min(lengths, default=1))  # 8
buckets = defaultdict(list)
for i, s in enumerate(unique_cores):
    prefix = (s or "")[:prefix_len]
    buckets[prefix].append(i)
# 后续只在同一 bucket_indices 内做相似度聚类
```

用每个 core 的**前 8 个字符**做桶键，只在同桶内两两比较。例如「深度学习大模型…」与「人工智能平台…」前缀不同，不会比较，既减少计算又避免误并。

**2.4 桶过大则不做相似度（安全阀）**

```python
# 约 134-136 行
if len(bucket_indices) > MAX_BUCKET_SIZE_FOR_SIMILARITY:  # 80
    all_clusters.extend([{i} for i in bucket_indices])
    continue
```

某前缀下 core 数 > 80 时，该桶内不再做相似度合并，每项单独成簇，防止大桶 O(n²) 导致超时。

**2.5 代表法聚类（长串优先当代表）**

```python
# 约 137-148 行
order = sorted(bucket_indices, key=lambda i: -len(unique_cores[i]))  # 长→短
for idx in order:
    core = unique_cores[idx]
    for rep_i, members in clusters:
        if _similarity(core, unique_cores[rep_i], sim_cache) >= threshold:
            members.add(idx)
            assigned = True
            break
    if not assigned:
        clusters.append((idx, {idx}))
```

- 每个簇保留一个**代表**（rep_i），新 core 只和**各簇代表**比较，≥ 阈值（默认 0.88）则加入该簇，否则新建簇。
- 按长度降序处理，先出现的「更长、更完整」的 core 更容易成为代表，避免短标题当代表导致误并。

**2.6 相似度计算（_similarity）**

```python
# 约 91-110 行
# 长度比过小直接 0；短串是长串子串且长度比≥0.8 则直接 0.9；否则 SequenceMatcher.ratio()
# 结果带缓存，避免重复计算
```

**2.7 两轮簇间合并**

```python
# 约 150-161 行
for _ in range(2):
    ...
    if _similarity(代表i, 代表j, ...) >= threshold:
        clusters[i][1].update(clusters[j][1])
        clusters.pop(j)
        merged = True
        break   # 每轮只合并一对就 break
```

每轮**最多合并一对**就 `break`，所以需要两轮才能完成「A-B 合并后再与 C 合并」这类两段链；两轮是效果与开销的折中，不做完整传递闭包。

**2.8 project_id 生成**

每个簇选一个代表（代码中取簇内最长 core），`project_id = make_project_id(customer, 代表)`，即客户名规范化 + MD5(客户+代表) 前 12 位，同簇所有 (customer, canonical_core) 映射到同一 id。

---

### 3. 关联层：招标–中标按时间配对（tender_link.py）

**目标**：在同一 `project_id` 内，为每条**中标**记录找到「当前尚未被占用的、最近的一条**招标**」，产出 link_type、related_tender_id、related_bid_id。

**单遍按时间扫描（核心状态：last_tender_by_project）**

```python
# 约 58-89 行：按 project_id, 发布日期, tender_round 排序后遍历
order = df.sort_values([project_id_col, "_sort_date", "_tender_round"], ...).index.tolist()
for idx in order:
    pid = df.loc[idx, project_id_col]
    if df.loc[idx, "_is_tender"]:
        last_tender_by_project[pid] = df.loc[idx, "row_id"]   # 更新「当前招标」
        link_type[i] = "仅招标"
    elif df.loc[idx, "_is_bid"]:
        last_tender = last_tender_by_project.get(pid)
        if last_tender is not None:
            link_type[i] = "已关联"
            related_tender_id[i] = last_tender
            tender_has_bid.add(last_tender)
        else:
            link_type[i] = "仅中标"
```

- **招标**：只更新该项目的「当前招标」row_id。
- **中标**：若存在「当前招标」，则与其中标配对并标记该招标已被占用；否则记为「仅中标」。

随后（95-112 行）再为招标行回填 `related_bid_id`（任选一个指向它的中标），并区分「仅招标」与「已关联」。

**示例**（同一 project_id 按时间）：  
招标1 → 招标2 → 中标A → 中标B  
- 中标A 配对 招标2（当前招标）；中标B 时「当前招标」仍是招标2，但招标2 已被 A 占用。当前实现是「当前招标」被第一次中标占用后不再更新，因此 B 会与「当前招标」配对（即仍为招标2）。若希望 B 配对新的招标，需改逻辑；现有逻辑是「每条中标找最近一条招标」，且一条招标可被多条中标指向（如多包）。

---

### 4. 分析层：AI/大模型与层级（analysis_layer.py + analysis_config.py）

**目标**：打标 is_ai、is_llm，以及 llm_layer（算力/模型/平台/应用），层级优先级 **应用 > 平台 > 模型 > 算力**。

**匹配文本**：`项目名称 + " " + project_name_core`，避免只匹配标题或只匹配 core 导致漏标。

**L1 is_ai**：先命中 L1_KEYWORDS（人工智能、大模型、深度学习等）；若仅命中「人工智能」且命中 L1_EXCLUDE_PATTERN（装修、支行、小镇等），且无 L2、无「大模型」「平台」「建设」等，则判为非 AI，用于过滤挂名「人工智能」的非相关项目。

**L3 层级**：按 LAYER_ORDER 依次匹配各层正则；先匹配到的先返回，从而实现应用 > 平台 > 模型 > 算力。仅对 is_llm 为 True 的行打层级，否则「未分类」。

---

### 5. 看板：项目级金额与中标优先（app_dashboard.py）

**目标**：金额按**项目**汇总，每项目只计**一条**金额；若有中标金额则**优先取中标**。

```python
# get_project_amounts（约 20-35 行）
has_amt = d[d["_has_amount"]].copy()
has_amt["_is_bid"] = has_amt["record_type"].astype(str).isin(BID_RECORD_TYPES)
has_amt = has_amt.sort_values(["_is_bid", "发布日期"], ascending=[False, True])
first_per_project = has_amt.groupby("project_id", as_index=False).first()
```

- 只保留有有效金额的记录，打标是否中标类。
- 排序：**中标类在前**（_is_bid 降序），再按发布日期升序。
- 按 project_id 取 `.first()`：每个项目一条；自然得到「有中标取中标，否则取第一条有效金额」。

看板中「金额分析」「客户×项目 Top5」等均基于此项目级金额表，保证不重复叠加且口径一致。

---

以上为项目中复杂部分的实现要点与示例；修改规则或阈值时建议先跑小样本与质量报告再全量重跑。
