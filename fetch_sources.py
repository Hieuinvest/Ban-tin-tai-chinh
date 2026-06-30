"""
fetch_sources.py
Lấy tin thô từ các nguồn RSS/feed công khai, gom lại thành một khối text
để đưa cho Claude tổng hợp thành bản tin.

Chạy: python3 fetch_sources.py > raw_sources.txt
"""

import feedparser
import requests
from datetime import datetime, timezone, timedelta

# ----------------------------------------------------------------------
# DANH SÁCH NGUỒN — chỉnh sửa / thêm bớt tại đây
# Mỗi nguồn: (Tên hiển thị, URL RSS, Nhóm chủ đề)
# ----------------------------------------------------------------------
SOURCES = [
    # --- Chứng khoán Việt Nam ---
    ("Vietstock - Tin chứng khoán", "https://vietstock.vn/735/chung-khoan/co-phieu.rss", "TTCK Việt Nam"),
    ("VnEconomy - Chứng khoán", "https://vneconomy.vn/chung-khoan.rss", "TTCK Việt Nam"),

    # --- Thế giới / thị trường quốc tế ---
    ("Vietstock - Chứng khoán thế giới", "https://vietstock.vn/773/the-gioi/chung-khoan-the-gioi.rss", "Thế giới"),
    ("WSJ Markets", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", "Thế giới"),
    ("OilPrice - Main", "https://oilprice.com/rss/main", "Vàng & Hàng hóa"),

    # --- Vàng & hàng hóa ---
    ("Vietstock - Vàng", "https://vietstock.vn/737/hang-hoa/vang.rss", "Vàng & Hàng hóa"),

    # --- Crypto ---
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "Crypto"),
    ("Cointelegraph", "https://cointelegraph.com/rss", "Crypto"),

    # --- Vĩ mô / thời sự kinh tế ---
    ("VnEconomy - Thời sự", "https://vneconomy.vn/thoi-su.rss", "Vĩ mô & Thời sự"),
    ("Vietstock - Vĩ mô", "https://vietstock.vn/737/vi-mo/vi-mo-dau-tu.rss", "Vĩ mô & Thời sự"),

    # --- Bất động sản ---
    ("VnEconomy - Bất động sản", "https://vneconomy.vn/bat-dong-san.rss", "Bất động sản"),
    ("Vietstock - Bất động sản", "https://vietstock.vn/734/bat-dong-san/doanh-nghiep-bat-dong-san.rss", "Bất động sản"),
]

# Chỉ lấy tin trong N giờ gần nhất để bản tin luôn "nóng"
HOURS_WINDOW = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BanTinBot/1.0)"}


def fetch_feed(name, url, group, hours_window=HOURS_WINDOW):
    """Lấy 1 feed RSS, trả về list các tin trong khung giờ gần nhất."""
    items = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as e:
        print(f"[CẢNH BÁO] Không lấy được nguồn '{name}': {e}", flush=True)
        return items

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_window)

    for entry in parsed.entries[:15]:
        title = entry.get("title", "").strip()
        summary = entry.get("summary", entry.get("description", "")).strip()
        link = entry.get("link", "")

        # Lọc theo thời gian nếu feed có published_parsed
        pub_dt = None
        if entry.get("published_parsed"):
            pub_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif entry.get("updated_parsed"):
            pub_dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

        if pub_dt and pub_dt < cutoff:
            continue

        items.append({
            "source": name,
            "group": group,
            "title": title,
            "summary": summary,
            "link": link,
            "published": pub_dt.isoformat() if pub_dt else "không rõ",
        })
    return items


def main():
    all_items = []
    for name, url, group in SOURCES:
        items = fetch_feed(name, url, group)
        print(f"[OK] {name}: lấy được {len(items)} tin", flush=True)
        all_items.extend(items)

    # In ra dạng text có cấu trúc để Claude dễ đọc
    print("\n" + "=" * 70)
    print(f"TỔNG HỢP NGUỒN TIN — {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70 + "\n")

    by_group = {}
    for item in all_items:
        by_group.setdefault(item["group"], []).append(item)

    for group, items in by_group.items():
        print(f"\n### NHÓM: {group} ###\n")
        for it in items:
            print(f"- [{it['source']}] {it['title']}")
            if it["summary"]:
                # cắt bớt summary quá dài
                s = it["summary"][:400].replace("\n", " ")
                print(f"  Tóm tắt: {s}")
            print(f"  Link: {it['link']}")
            print(f"  Thời gian: {it['published']}")
            print()


if __name__ == "__main__":
    main()
