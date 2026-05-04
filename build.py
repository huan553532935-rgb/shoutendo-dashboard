#!/usr/bin/env python3
"""
寿仁堂 内部数据看板 - 数据更新脚本
用法: python3 build.py
功能: 读取「每日销售明细.csv」，计算所有看板指标，更新 index.html 中的数据。
"""

import csv
import json
import re
import os
from collections import defaultdict

CSV_FILE = "每日销售明细.csv"
HTML_FILE = "index.html"


def classify(product_name):
    """根据产品名称推断品类"""
    name = product_name.strip()
    if "蛋白" in name:
        return "蛋白类"
    if "丙球" in name:
        return "丙球类"
    if "胸腺" in name or "肽" in name or "肽君沙" in name:
        return "肽类"
    if "赛典" in name or "普乐沙福" in name:
        return "抗癌类"
    if any(k in name for k in ["亚胺", "舒巴坦", "泊沙", "两性", "红霉素", "美法仑", "克拉屈滨"]):
        return "抗生素"
    if any(k in name for k in ["来士普", "富马酸", "比索洛尔"]):
        return "慢病用药"
    if any(k in name for k in ["康王", "西瓜霜", "明目地黄", "特普宁"]):
        return "OTC/中成药"
    if "护理垫" in name:
        return "耗材"
    return "其他"


def parse_csv(filepath):
    """Parse the CSV and return monthly aggregated data."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到数据文件: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.strip().split("\n")
    reader = csv.DictReader(lines[1:])  # row 1 = title, row 2 = header

    monthly = defaultdict(lambda: {
        "revenue": 0.0,
        "txns": 0,
        "products": defaultdict(lambda: {"revenue": 0.0, "units": 0}),
        "all_products": set(),
    })

    for row in reader:
        date_str = row.get("时间", "").strip()
        if not date_str:
            continue
        try:
            month, day = date_str.split("/")
            month_key = f"{int(month):02d}"
        except ValueError:
            continue

        product = row.get("品名", "").strip()
        if not product:
            continue

        try:
            qty = float(row.get("数量", "0").strip())
            total = float(row.get("总价", "0").strip())
        except ValueError:
            continue

        monthly[month_key]["revenue"] += total
        monthly[month_key]["txns"] += 1
        monthly[month_key]["products"][product]["revenue"] += total
        monthly[month_key]["products"][product]["units"] += qty
        monthly[month_key]["all_products"].add(product)

    return monthly


def compute_dashboard(monthly):
    """Compute all dashboard KPIs from monthly data."""
    sorted_months = sorted(monthly.keys())
    if not sorted_months:
        raise ValueError("CSV 中没有有效数据")

    # Latest complete month (skip incomplete current month if < 20% of prev month txns)
    latest = sorted_months[-1]
    prev = None
    if len(sorted_months) >= 2:
        prev_candidate = sorted_months[-2]
        # If latest month has < 20% of previous month's transactions, it's likely incomplete
        if monthly[latest]["txns"] < monthly[prev_candidate]["txns"] * 0.2:
            latest = prev_candidate
            if len(sorted_months) >= 3:
                prev = sorted_months[-3]
        else:
            prev = prev_candidate

    m = monthly[latest]
    prev_m = monthly.get(prev) if prev else None

    # Top 3 products by revenue
    top3 = sorted(m["products"].items(), key=lambda x: x[1]["revenue"], reverse=True)[:3]

    # All-time products
    all_products = set()
    for mk in monthly:
        all_products.update(monthly[mk]["all_products"])

    # Category revenue
    cat_rev = defaultdict(float)
    for prod, data in m["products"].items():
        cat = classify(prod)
        cat_rev[cat] += data["revenue"]
    top_cat = max(cat_rev.items(), key=lambda x: x[1])[0]

    sell_through = len(m["all_products"]) / len(all_products) * 100
    avg_order = m["revenue"] / m["txns"] if m["txns"] > 0 else 0

    rev_change = ((m["revenue"] - prev_m["revenue"]) / prev_m["revenue"] * 100) if prev_m and prev_m["revenue"] > 0 else 0
    txn_change = ((m["txns"] - prev_m["txns"]) / prev_m["txns"] * 100) if prev_m and prev_m["txns"] > 0 else 0

    return {
        "month_label": f"{latest}月",
        "revenue": round(m["revenue"]),
        "prev_revenue": round(prev_m["revenue"]) if prev_m else 0,
        "txns": m["txns"],
        "prev_txns": prev_m["txns"] if prev_m else 0,
        "rev_change": round(rev_change, 1),
        "txn_change": round(txn_change, 1),
        "sell_through": round(sell_through),
        "active_products": len(m["all_products"]),
        "total_products": len(all_products),
        "avg_order": round(avg_order),
        "top_category": top_cat,
        "top3": [
            {
                "name": p,
                "revenue": round(d["revenue"]),
                "units": int(d["units"]),
                "category": classify(p),
            }
            for p, d in top3
        ],
    }


def write_html(data):
    """Update index.html with computed dashboard data."""
    if not os.path.exists(HTML_FILE):
        raise FileNotFoundError(f"找不到 HTML 文件: {HTML_FILE}")

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Build the data object string
    products_str = ",\n    ".join(
        f'{{ name: "{p["name"]}", category: "{p["category"]}", revenue: {p["revenue"]}, units: {p["units"]} }}'
        for p in data["top3"]
    )

    new_data_block = f"""// ── Real data from 每日销售明细.csv ({data["month_label"]} = latest complete month) ──
const data = {{
  monthLabel: "{data["month_label"]}",
  monthlyRevenue: {data["revenue"]},
  lastMonthRevenue: {data["prev_revenue"]},
  monthlyTxns: {data["txns"]},
  lastMonthTxns: {data["prev_txns"]},
  revChange: {data["rev_change"]},
  txnChange: {data["txn_change"]},
  sellThrough: {data["sell_through"]},
  totalProducts: {data["total_products"]},
  activeProducts: {data["active_products"]},
  avgOrderValue: {data["avg_order"]},
  topCategory: "{data["top_category"]}",
  products: [
    {products_str}
  ],
}};"""

    # Replace the data block — match from "// ── Real data" to the closing "};"
    pattern = r"// ── Real data from.*?\nconst data = \{.*?\};"
    updated = re.sub(pattern, new_data_block, html, count=1, flags=re.DOTALL)

    if updated == html:
        raise RuntimeError("未找到数据块 — index.html 中的数据格式可能已变更，请检查")

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(updated)

    return True


def main():
    print("寿仁堂 数据看板 · 构建脚本")
    print("=" * 40)

    # 1. Parse CSV
    print(f"📂 读取 {CSV_FILE} ...")
    monthly = parse_csv(CSV_FILE)
    print(f"   找到 {len(monthly)} 个月的数据: {sorted(monthly.keys())}")

    # 2. Compute
    print("🧮 计算指标 ...")
    data = compute_dashboard(monthly)

    # 3. Print summary
    print()
    print(f"   最新完整月份: {data['month_label']}")
    print(f"   营收: ¥{data['revenue']:,}  (环比 {data['rev_change']:+.1f}%)")
    print(f"   交易笔数: {data['txns']:,}  (环比 {data['txn_change']:+.1f}%)")
    print(f"   动销率: {data['sell_through']}%  ({data['active_products']}/{data['total_products']} SKU)")
    print(f"   客单价: ¥{data['avg_order']:,}")
    print(f"   最畅销品类: {data['top_category']}")
    print()
    print("   TOP 3 产品:")
    for i, p in enumerate(data["top3"], 1):
        print(f"   {i}. {p['name']} ({p['category']}) — ¥{p['revenue']:,} / {p['units']} 件")

    # 4. Write HTML
    print()
    print(f"✍️  更新 {HTML_FILE} ...")
    write_html(data)

    print()
    print("✅ 构建完成！")
    print("   现在可以推送到 GitHub 或使用 Vercel CLI 部署。")


if __name__ == "__main__":
    main()
