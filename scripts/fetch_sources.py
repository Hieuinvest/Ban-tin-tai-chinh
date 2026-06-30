"""
fetch_sources.py
Lấy tin thô từ các nguồn RSS/feed công khai, gom lại thành một khối text
để đưa cho Claude tổng hợp thành bản tin.

Chạy: python3 fetch_sources.py > raw_sources.txt
"""

import time
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
    ("Vietstock - Doanh nghiệp niêm yết", "https://vietstock.vn/737/doanh-nghiep/doanh-nghiep-niem-yet.rss", "TTCK Việt Nam"),
    ("VnEconomy - Chứng khoán", "https://vneconomy.vn/chung-khoan.rss", "TTCK Việt Nam"),
    ("CafeF - Chứng khoán", "https://cafef.vn/thi-truong-chung-khoan.rss", "TTCK Việt Nam"),
    ("VietnamBiz - Chứng khoán", "https://vietnambiz.vn/chung-khoan.rss", "TTCK Việt Nam"),

    # --- Thế giới / thị trường quốc tế ---
    ("Vietstock - Chứng khoán thế giới", "https://vietstock.vn/773/the-gioi/chung-khoan-the-gioi.rss", "Thế giới"),
    ("WSJ Markets", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", "Thế giới"),
    ("Investing.com - Tin thị trường", "https://www.investing.com/rss/news_25.rss", "Thế giới"),
    ("CNBC - Markets", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", "Thế giới"),

    # --- Vàng & hàng hóa ---
    ("Vietstock - Hàng hóa", "https://vietstock.vn/737/hang-hoa/vang.rss", "Vàng & Hàng hóa"),
    ("OilPrice - Main", "https://oilprice.com/rss/main", "Vàng & Hàng hóa"),
    ("Kitco News", "https://www.kitco.com/rss/KitcoNews.xml", "Vàng & Hàng hóa"),

    # --- Crypto ---
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "Crypto"),
    ("Cointelegraph", "https://cointelegraph.com/rss", "Crypto"),
    ("Vietstock - Tiền điện tử", "https://vietstock.vn/761/chung-khoan/tien-ao.rss", "Crypto"),

    # --- Vĩ mô / thời sự kinh tế ---
    ("VnEconomy - Thời sự", "https://vneconomy.vn/thoi-su.rss", "Vĩ mô & Thời sự"),
    ("VnEconomy - Tài chính", "https://vneconomy.vn/tai-chinh.rss", "Vĩ mô & Thời sự"),
    ("Vietstock - Vĩ mô", "https://vietstock.vn/737/vi-mo/vi-mo-dau-tu.rss", "Vĩ mô & Thời sự"),
    ("CafeF - Vĩ mô", "https://cafef.vn/vi-mo-dau-tu.rss", "Vĩ mô & Thời sự"),

    # --- Bất động sản ---
    ("VnEconomy - Bất động sản", "https://vneconomy.vn/bat-dong-san.rss", "Bất động sản"),
    ("Vietstock - Bất động sản", "https://vietstock.vn/734/bat-dong-san/doanh-nghiep-bat-dong-san.rss", "Bất động sản"),
    ("CafeF - Bất động sản", "https://cafef.vn/bat-dong-san.rss", "Bất động sản"),
]

# Chỉ lấy tin trong N giờ gần nhất để bản tin luôn "nóng".
# Nếu lọc theo cửa sổ này làm MẤT HẾT tin của 1 nguồn, sẽ tự động lấy
# N_FALLBACK tin mới nhất (không lọc giờ) để tránh bản tin trống.
HOURS_WINDOW = 36
N_FALLBACK_ITEMS = 6

HEADERS = {
    # Giả lập trình duyệt Chrome thật — nhiều site VN chặn User-Agent mặc định của thư viện
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 3


def _http_get_with_retry(url):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)
    raise last_err


def fetch_feed(name, url, group):
    """Lấy 1 feed RSS, trả về list các tin. Ưu tiên tin trong khung giờ gần
    nhất; nếu lọc giờ làm rỗng kết quả, fallback lấy N tin mới nhất bất kể
    thời gian (tốt hơn là để bản tin không có dữ liệu)."""
    try:
        resp = _http_get_with_retry(url)
        parsed = feedparser.parse(resp.content)
    except Exception as e:
        print(f"[LỖI] Không lấy được nguồn '{name}' ({url}): {e}", flush=True)
        return []

    if not parsed.entries:
        bozo_msg = getattr(parsed, "bozo_exception", None)
        print(f"[CẢNH BÁO] Nguồn '{name}' trả về 0 mục feed. "
              f"(bozo={parsed.get('bozo')}, lỗi parse={bozo_msg})", flush=True)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_WINDOW)

    def to_item(entry):
        title = entry.get("title", "").strip()
        summary = entry.get("summary", entry.get("description", "")).strip()
        link = entry.get("link", "")
        pub_dt = None
        if entry.get("published_parsed"):
            pub_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif entry.get("updated_parsed"):
            pub_dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        return {
            "source": name,
            "group": group,
            "title": title,
            "summary": summary,
            "link": link,
            "published": pub_dt.isoformat() if pub_dt else "không rõ",
            "_pub_dt": pub_dt,
        }

    all_items = [to_item(e) for e in parsed.entries[:20]]

    recent_items = [
        it for it in all_items
        if it["_pub_dt"] is None or it["_pub_dt"] >= cutoff
    ]

    if recent_items:
        return recent_items[:15]

    # Fallback: cửa sổ giờ làm rỗng kết quả (feed có vẻ không cập nhật
    # gần đây, hoặc thiếu trường ngày) → vẫn lấy vài tin mới nhất theo
    # thứ tự feed trả về, để tránh nguồn bị bỏ trắng hoàn toàn.
    print(f"[CẢNH BÁO] '{name}': không có tin nào trong {HOURS_WINDOW}h gần nhất, "
          f"lấy tạm {N_FALLBACK_ITEMS} tin mới nhất theo feed.", flush=True)
    return all_items[:N_FALLBACK_ITEMS]


def main():
    all_items = []
    ok_count = 0
    fail_sources = []

    for name, url, group in SOURCES:
        items = fetch_feed(name, url, group)
        status = "OK" if items else "RỖNG"
        print(f"[{status}] {name}: lấy được {len(items)} tin", flush=True)
        if items:
            ok_count += 1
        else:
            fail_sources.append(name)
        all_items.extend(items)

    print(f"\n[TỔNG KẾT] {ok_count}/{len(SOURCES)} nguồn có dữ liệu. "
          f"Tổng {len(all_items)} tin.", flush=True)
    if fail_sources:
        print(f"[TỔNG KẾT] Nguồn không lấy được tin: {', '.join(fail_sources)}", flush=True)

    # In ra dạng text có cấu trúc để Claude dễ đọc
    print("\n" + "=" * 70)
    print(f"TỔNG HỢP NGUỒN TIN — {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70 + "\n")

    by_group = {}
    for item in all_items:
        by_group.setdefault(item["group"], []).append(item)

    if not all_items:
        print("(!) KHÔNG LẤY ĐƯỢC TIN TỪ BẤT KỲ NGUỒN NÀO TRONG LẦN CHẠY NÀY.")
        return

    for group, items in by_group.items():
        print(f"\n### NHÓM: {group} ###\n")
        for it in items:
            print(f"- [{it['source']}] {it['title']}")
            if it["summary"]:
                s = it["summary"][:400].replace("\n", " ")
                print(f"  Tóm tắt: {s}")
            print(f"  Link: {it['link']}")
            print(f"  Thời gian: {it['published']}")
            print()


if __name__ == "__main__":
    main()
