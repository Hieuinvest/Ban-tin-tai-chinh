"""
generate_newsletter.py — v3
Gọi Claude API 2 lần:
  Lần 1: Claude trả về JSON chứa nội dung bản tin (tiêu đề, tóm tắt, các mục...)
  Lần 2: Script nhúng JSON vào template HTML cố định (không để Claude tự viết CSS)
→ Tránh hẳn lỗi encoding font Google Fonts và lỗi dấu tiếng Việt.
"""

import os, sys, time, json, re, unicodedata, requests
from datetime import datetime, timezone, timedelta

API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = "claude-sonnet-4-6"
VN_TZ   = timezone(timedelta(hours=7))
MAX_TOKENS  = 8000
API_TIMEOUT = 600
API_RETRIES = 3

# ─────────────────────────────────────────────
# PROMPT: Claude chỉ trả về JSON, không HTML
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """\
Bạn là chuyên gia phân tích tài chính, tổng hợp tin tức thành bản tin TTCK chuyên nghiệp.
Phong cách: súc tích, số liệu cụ thể, khách quan, không khuyến nghị mua/bán.

NHIỆM VỤ: Từ dữ liệu tin tức thô, hãy trả về MỘT object JSON hợp lệ theo schema dưới đây.
CHỈ trả về JSON, không có lời giải thích, không có markdown, không có ```json.

SCHEMA (tất cả giá trị là string tiếng Việt, trừ khi ghi chú khác):
{
  "tieu_de": "Câu tiêu đề ngắn bắt tin nổi bật nhất, giống kiểu báo tài chính",
  "tom_tat": "3-5 câu tóm tắt toàn bộ bức tranh thị trường hôm nay",
  "chi_so": [
    {"ten": "VN-Index", "gia_tri": "1.854,97", "thay_doi": "-0,38%", "xu_huong": "down"},
    {"ten": "S&P 500",  "gia_tri": "7.440,43", "thay_doi": "+1,18%", "xu_huong": "up"},
    {"ten": "Dow Jones","gia_tri": "52.000",   "thay_doi": "Kỷ lục", "xu_huong": "up"},
    {"ten": "Nasdaq",   "gia_tri": "...",       "thay_doi": "...",    "xu_huong": "up|down|flat"},
    {"ten": "HNX-Index","gia_tri": "...",       "thay_doi": "...",    "xu_huong": "up|down|flat"},
    {"ten": "Vàng TG",  "gia_tri": "...",       "thay_doi": "...",    "xu_huong": "up|down|flat"},
    {"ten": "Vàng SJC", "gia_tri": "...",       "thay_doi": "...",    "xu_huong": "up|down|flat"},
    {"ten": "Bitcoin",  "gia_tri": "...",       "thay_doi": "...",    "xu_huong": "up|down|flat"},
    {"ten": "Dầu Brent","gia_tri": "...",       "thay_doi": "...",    "xu_huong": "up|down|flat"},
    {"ten": "USD/VND",  "gia_tri": "...",       "thay_doi": "...",    "xu_huong": "up|down|flat"}
  ],
  "panels": [
    {
      "so": "1",
      "tieu_de": "Market Note — TTCK Việt Nam",
      "noi_dung": "4-7 câu phân tích chính về VN-Index, dòng tiền, khối ngoại, cổ phiếu nổi bật. Dùng **in đậm** cho số liệu quan trọng."
    },
    {
      "so": "2",
      "tieu_de": "Vĩ mô trong nước",
      "noi_dung": "4-7 câu về chính sách, lãi suất, tỷ giá, FDI, tin kinh tế vĩ mô VN. Dùng **in đậm** cho số liệu."
    },
    {
      "so": "3",
      "tieu_de": "Điểm nhấn quốc tế",
      "noi_dung": "4-7 câu về Fed/ECB, chứng khoán Mỹ-châu Á, vàng, dầu, crypto, hàng hóa. Dùng **in đậm** cho số liệu."
    }
  ],
  "toan_cau": "2-3 câu tóm tắt chứng khoán & kinh tế toàn cầu để dùng làm subhead cho bảng chỉ số",
  "ham_y": "3-5 câu phân tích hàm ý chiến lược (bull/bear, tác động tới NĐT VN). Kết bằng: 'Tài liệu mang tính thông tin, KHÔNG phải khuyến nghị giao dịch/đầu tư.'",
  "su_kien": ["Sự kiện/dữ liệu cần chú ý 1", "Sự kiện 2", "Sự kiện 3"],
  "nguon": ["Tên nguồn 1 — Tiêu đề bài — URL", "Nguồn 2 — Tiêu đề — URL"]
}

QUY TẮC BẮT BUỘC:
- CHỈ điền số liệu có trong dữ liệu nguồn. Nếu không có, dùng "N/A".
- xu_huong chỉ được là: "up", "down", hoặc "flat".
- JSON phải hợp lệ 100% (dùng dấu nháy kép, escape ký tự đặc biệt đúng chuẩn).
- KHÔNG thêm bất kỳ text nào ngoài JSON object.
"""


def call_api(messages, api_key):
    last_err = None
    for attempt in range(1, API_RETRIES + 1):
        try:
            resp = requests.post(
                API_URL,
                headers={"x-api-key": api_key,
                         "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": MODEL, "max_tokens": MAX_TOKENS,
                      "system": SYSTEM_PROMPT, "messages": messages},
                timeout=API_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_err = e
            wait = 20 * attempt
            print(f"[RETRY {attempt}/{API_RETRIES}] {e} — chờ {wait}s...", flush=True)
            time.sleep(wait)
        except requests.exceptions.HTTPError as e:
            print(f"[LỖI HTTP] {e} — {resp.text[:300]}", file=sys.stderr)
            raise
    raise last_err


def get_json_data(raw_data, date_human, api_key):
    user_msg = (
        f"Hôm nay {date_human} (giờ VN). Dữ liệu tin tức:\n\n{raw_data}\n\n"
        "Trả về JSON theo schema đã định, CHỈ JSON, không gì khác."
    )
    data = call_api([{"role": "user", "content": user_msg}], api_key)
    text = "".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")
    text = unicodedata.normalize("NFC", text.strip())
    # Xóa code fence nếu có
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    # Tìm JSON object trong text
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        text = m.group(0)
    return json.loads(text)


def bold_to_html(s):
    """Chuyển **text** thành <strong>text</strong>"""
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)


def render_html(d, date_str, date_human, weekday_vn):
    """Nhúng dữ liệu JSON vào template HTML cố định — không để Claude viết CSS."""

    # Thẻ chỉ số
    def card(c):
        xu = c.get("xu_huong", "flat")
        color = "#1e6b3e" if xu == "up" else ("#8b1a1a" if xu == "down" else "#5a5248")
        bg    = "#e8f4ec" if xu == "up" else ("#faeaea" if xu == "down" else "#f0ede6")
        arrow = "▲" if xu == "up" else ("▼" if xu == "down" else "≈")
        return f"""<div class="card">
  <div class="card-name">{c['ten']}</div>
  <div class="card-val">{c['gia_tri']}</div>
  <div class="card-chg" style="color:{color};background:{bg}">{arrow} {c['thay_doi']}</div>
</div>"""

    cards_html = "\n".join(card(c) for c in d.get("chi_so", []))

    # 3 panel
    def panel(p):
        return f"""<div class="panel">
  <div class="panel-head">
    <span class="panel-num">{p['so']}</span>
    <span class="panel-title">{p['tieu_de'].upper()}</span>
  </div>
  <p>{bold_to_html(p['noi_dung'])}</p>
</div>"""

    panels_html = "\n".join(panel(p) for p in d.get("panels", []))

    # Sự kiện
    su_kien_html = "".join(f"<li>{e}</li>" for e in d.get("su_kien", []))

    # Nguồn
    def src_line(s):
        parts = s.split(" — ")
        if len(parts) >= 3:
            url = parts[-1].strip()
            label = " — ".join(parts[:-1])
            if url.startswith("http"):
                return f'<li><a href="{url}" target="_blank">{label}</a></li>'
        return f"<li>{s}</li>"
    nguon_html = "".join(src_line(s) for s in d.get("nguon", []))

    ham_y = bold_to_html(d.get("ham_y", ""))
    tom_tat = bold_to_html(d.get("tom_tat", ""))

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bản tin TTCK | {date_str} — {d.get('tieu_de','')}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,'Segoe UI',Arial,sans-serif;background:#F5F0E8;color:#1a1714;font-size:15px;line-height:1.6}}
a{{color:#16263D;text-decoration:none}}
a:hover{{text-decoration:underline}}
strong{{font-weight:700;color:#1a1714}}

/* MASTHEAD */
.masthead{{background:#16263D;color:#c8bfa8;padding:6px 16px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center}}
.masthead a{{color:#c9a24b}}

/* BANNER */
.banner{{background:#1a1714;color:#F5F0E8;padding:28px 20px 20px;text-align:center;border-bottom:3px solid #c9a24b}}
.banner-eye{{font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:#c9a24b;margin-bottom:12px}}
.banner-eye span{{opacity:.5;margin:0 8px}}.banner-eye span::before,.banner-eye span::after{{content:"•"}}
.banner h1{{font-size:clamp(22px,4vw,38px);font-weight:800;line-height:1.15;max-width:700px;margin:0 auto 10px;letter-spacing:-.02em}}
.banner-meta{{font-size:12px;color:#a09580;letter-spacing:.06em;text-transform:uppercase}}

/* DISCLAIMER */
.disclaimer{{background:#eae4d8;text-align:center;font-size:12px;color:#6b6050;padding:7px 16px;border-bottom:1px solid #d4cabb}}

/* WRAP */
.wrap{{max-width:800px;margin:0 auto;padding:0 16px}}

/* LEDE */
.lede-box{{background:#fff;border:1px solid #ddd6c8;border-left:4px solid #16263D;padding:16px 20px;margin:20px 0;font-size:15px;line-height:1.75;color:#2a2520}}

/* CARDS */
.card-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:#c8bfa8;border:1px solid #c8bfa8;margin:0 0 24px}}
.card{{background:#fff;padding:14px 12px;text-align:center}}
.card-name{{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#7a7060;margin-bottom:6px}}
.card-val{{font-size:20px;font-weight:800;color:#16263D;line-height:1.1;margin-bottom:5px}}
.card-chg{{display:inline-block;font-size:11px;font-weight:700;padding:2px 7px;border-radius:2px}}
@media(max-width:600px){{.card-grid{{grid-template-columns:repeat(2,1fr)}}}}

/* ĐIỂM TIN TOÀN CẦU */
.global-bar{{background:#16263D;color:#F5F0E8;padding:14px 20px;margin-bottom:0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}}
.global-bar .gb-label{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#c9a24b;font-weight:700}}
.global-bar .gb-text{{font-size:13px;color:#c8bfa8;max-width:560px;line-height:1.5}}

/* PANELS */
.panel-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#c8bfa8;border:1px solid #c8bfa8;margin-bottom:24px}}
.panel{{background:#fff;padding:18px 16px}}
.panel-head{{display:flex;align-items:center;gap:8px;margin-bottom:12px;padding-bottom:10px;border-bottom:1.5px solid #1a1714}}
.panel-num{{background:#1a1714;color:#F5F0E8;font-size:12px;font-weight:800;width:22px;height:22px;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.panel-title{{font-size:13px;font-weight:800;letter-spacing:.03em;color:#1a1714}}
.panel p{{font-size:13.5px;line-height:1.7;color:#2a2520}}
@media(max-width:640px){{.panel-grid{{grid-template-columns:1fr}}}}

/* SỰ KIỆN */
.events-box{{background:#fff;border:1px solid #ddd6c8;padding:16px 20px;margin-bottom:24px}}
.box-head{{font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#16263D;border-bottom:2px solid #16263D;padding-bottom:8px;margin-bottom:12px}}
.events-box ul{{padding-left:18px}}
.events-box li{{font-size:13.5px;line-height:1.65;margin-bottom:7px;color:#2a2520}}

/* HÀM Ý */
.hamy-box{{background:#16263D;color:#F5F0E8;padding:22px 22px;margin-bottom:24px;border-left:4px solid #c9a24b}}
.hamy-box .box-head{{color:#c9a24b;border-color:#c9a24b}}
.hamy-box p{{font-size:14px;line-height:1.75;color:#c8bfa8}}
.hamy-box strong{{color:#F5F0E8}}

/* NGUỒN */
.nguon-box{{background:#fff;border:1px solid #ddd6c8;padding:16px 20px;margin-bottom:24px}}
.nguon-box ul{{padding-left:18px;columns:2;column-gap:24px}}
.nguon-box li{{font-size:12px;line-height:1.8;margin-bottom:4px;break-inside:avoid}}
.nguon-box a{{color:#16263D;border-bottom:1px solid #ddd6c8}}
@media(max-width:600px){{.nguon-box ul{{columns:1}}}}

/* FOOTER */
footer{{border-top:3px solid #1a1714;padding:16px 0 32px;display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}}
footer .legal{{font-size:11px;color:#7a7060;line-height:1.7;max-width:580px}}
footer .brand{{font-size:11px;color:#7a7060;text-align:right;font-weight:700}}
</style>
</head>
<body>

<div class="masthead">
  <span>Ban tin TTCK · Research Note · {weekday_vn}, {date_str}</span>
  <a href="./index.html">← Tat ca ban tin</a>
</div>

<div class="banner">
  <div class="banner-eye">Ban tin TTCK <span></span> Phat hanh sang som <span></span> {date_human}</div>
  <h1>{d.get('tieu_de','Bản tin TTCK')}</h1>
  <div class="banner-meta">{weekday_vn} · {date_human} · Gio Viet Nam</div>
</div>

<div class="disclaimer">⚠ Tai lieu thong tin tong hop — KHONG phai khuyen nghi giao dich / dau tu</div>

<div class="wrap">

  <div class="lede-box">{tom_tat}</div>

  <div class="card-grid">
{cards_html}
  </div>

  <div class="global-bar">
    <span class="gb-label">Diem tin kinh te toan cau · Gia tri chot {date_str}</span>
    <span class="gb-text">{d.get('toan_cau','')}</span>
  </div>

  <div class="panel-grid">
{panels_html}
  </div>

  <div class="events-box">
    <div class="box-head">★ Su kien & Du lieu can chu y</div>
    <ul>{su_kien_html}</ul>
  </div>

  <div class="hamy-box">
    <div class="box-head">★ Ham y chien luoc</div>
    <p>{ham_y}</p>
  </div>

  <div class="nguon-box">
    <div class="box-head">Nguon tham khao</div>
    <ul>{nguon_html}</ul>
  </div>

</div>

<div class="wrap">
<footer>
  <div class="legal">
    Du lieu tong hop tu cac nguon cong khai (Vietstock, VnEconomy, CafeF, WSJ, CoinDesk...).
    Ban tin mang tinh thong tin, KHONG phai khuyen nghi giao dich / dau tu. Moi quyet dinh
    dau tu can dua tren phan tich doc lap va tu van chuyen gia tai chinh co chung chi.
  </div>
  <div class="brand">Ban tin TTCK<br>{date_str}</div>
</footer>
</div>

</body>
</html>"""


def update_index(output_dir, date_str, title):
    list_path  = os.path.join(output_dir, "_entries.tsv")
    index_path = os.path.join(output_dir, "index.html")
    entries    = []
    if os.path.exists(list_path):
        with open(list_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    d, t = line.split("\t", 1)
                    if d != date_str:
                        entries.append((d, t))
    entries.append((date_str, title))
    entries.sort(key=lambda x: x[0], reverse=True)
    with open(list_path, "w", encoding="utf-8") as f:
        for d, t in entries:
            f.write(f"{d}\t{t}\n")

    rows = "\n".join(
        f'<li><a href="./{d}.html">{d} — {t}</a></li>' for d, t in entries
    )
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
<html lang="vi"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ban tin TTCK</title>
<style>
body{{font-family:-apple-system,Arial,sans-serif;max-width:700px;margin:40px auto;
padding:0 16px;background:#F5F0E8;color:#1a1714}}
h1{{font-size:1.4rem;margin-bottom:20px}}
ul{{list-style:none;padding:0}}
li{{margin:10px 0;padding:14px 16px;background:#fff;border:1px solid #ddd6c8}}
a{{color:#16263D;font-weight:700;text-decoration:none}}
a:hover{{text-decoration:underline}}
</style></head><body>
<h1>Ban tin TTCK — Tat ca ban tin</h1>
<ul>{rows}</ul>
</body></html>""")


WEEKDAYS_VN = ["Thu Hai","Thu Ba","Thu Tu","Thu Nam","Thu Sau","Thu Bay","Chu Nhat"]


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("LOI: thieu ANTHROPIC_API_KEY", file=sys.stderr); sys.exit(1)

    raw_path = "raw_sources.txt"
    if not os.path.exists(raw_path):
        print(f"LOI: khong tim thay {raw_path}", file=sys.stderr); sys.exit(1)

    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data = f.read()

    now_vn     = datetime.now(VN_TZ)
    date_str   = now_vn.strftime("%Y-%m-%d")
    date_human = now_vn.strftime("%d/%m/%Y")
    weekday_vn = WEEKDAYS_VN[now_vn.weekday()]

    print("Dang goi Claude API de lay du lieu JSON...", flush=True)
    data = get_json_data(raw_data, date_human, api_key)
    print(f"JSON OK — tieu de: {data.get('tieu_de','?')}", flush=True)

    html = render_html(data, date_str, date_human, weekday_vn)

    output_dir = "bantin"
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{date_str}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Da luu: {out_path}", flush=True)

    update_index(output_dir, date_str, data.get("tieu_de", date_str))
    print("Da cap nhat index.html", flush=True)


if __name__ == "__main__":
    main()
