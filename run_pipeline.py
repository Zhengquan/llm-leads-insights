# -*- coding: utf-8 -*-
"""
流水线脚本：按顺序执行 清洗 -> 分组 -> 关联 -> 分析 -> 质量报告。
执行前可选清理中间产出目录（仅清理 data_cleaned / data_grouped / data_linked / data_analysis / data_quality），
不触碰原始数据 data/。
支持重复执行；默认先清理再跑全量，可用 --no-clean 仅重跑不清理。
"""
import argparse
import os
import shutil
import sys

# 仅允许清理的中间产出目录（绝不清理 data/ 原始数据）
INTERMEDIATE_DIRS = [
    "data_cleaned",
    "data_grouped",
    "data_linked",
    "data_analysis",
    "data_quality",
]


def clean_intermediate():
    """清理中间产出目录内容，便于流水线从头重算。不删除 data/。"""
    for d in INTERMEDIATE_DIRS:
        if os.path.isdir(d):
            shutil.rmtree(d)
            print(f"  已清理: {d}/")
        else:
            print(f"  跳过(不存在): {d}/")


def run_pipeline(do_clean: bool = True):
    if do_clean:
        print("--- 清理中间产出（不触碰 data/）---")
        clean_intermediate()
        print()

    print("--- 1/5 清洗层 run_clean ---")
    from run_clean import run as run_clean
    run_clean()
    print()

    print("--- 2/5 分组层 run_group ---")
    from run_group import run as run_group
    run_group()
    print()

    print("--- 3/5 关联层 run_link ---")
    from run_link import run as run_link
    run_link()
    print()

    print("--- 4/5 分析层 run_analysis ---")
    from run_analysis import run as run_analysis
    run_analysis()
    print()

    print("--- 5/5 质量报告 run_quality_report ---")
    from run_quality_report import run as run_quality_report
    run_quality_report()
    print()

    print("流水线执行完毕。")


def main():
    parser = argparse.ArgumentParser(
        description="招投标数据流水线：清洗->分组->关联->分析->质量报告。默认先清理中间目录再执行。"
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="不清理中间目录，直接重跑各步（会覆盖已有产出）",
    )
    args = parser.parse_args()
    run_pipeline(do_clean=not args.no_clean)


if __name__ == "__main__":
    main()
