"""
generate_newsletter.py — v4
Claude trả về JSON → script nhúng vào template HTML cố định (layout báo, 10 mục, 2 hàng x 3 cột panel).
"""

import os, sys, time, json, re, unicodedata, requests
from datetime import datetime, timezone, timedelta

API_URL     = "https://api.anthropic.com/v1/messages"
MODEL       = "claude-sonnet-4-6"
VN_TZ       = timezone(timedelta(hours=7))
MAX_TOKENS  = 12000
API_TIMEOUT = 600
API_RETRIES = 3

SYSTEM_PROMPT = """\
Bạn là chuyên gia phân tích tài chính, tổng hợp tin tức thành bản tin TTCK chuyên nghiệp.
Phong cách: súc tích, số liệu cụ thể, khách quan. KHÔNG khuyến nghị mua/bán cụ thể.

NHIỆM VỤ: Từ dữ liệu tin tức thô, trả về MỘT JSON object hợp lệ theo schema dưới đây.
CHỈ JSON, không markdown, không giải thích, không ```json, bắt đầu bằng { kết thúc bằng }.

QUAN TRỌNG VỀ SỐ LIỆU:
- Trích xuất MỌI con số có trong dữ liệu nguồn (điểm index, %, tỷ đồng, USD...)
- Nếu nguồn nêu biến động % → dùng ngay, nếu nêu 2 mức giá → tính % nếu được
- Nếu thực sự không có số liệu → dùng "N/A", không bịa
- Dùng **text** để in đậm số liệu quan trọng trong noi_dung
- Nếu phần đầu dữ liệu có mục "DỮ LIỆU GIÁ THỊ TRƯỜNG" (từ vnstock), ƯU TIÊN dùng
  các con số đó cho thẻ chỉ số (VN-Index, HNX, cổ phiếu...) thay vì để N/A.

QUAN TRỌNG VỀ TÁC ĐỘNG (bắt buộc):
- Khi đưa mỗi tin quan trọng, PHẢI nêu rõ tin đó tác động đến CỔ PHIẾU cụ thể (mã) hoặc
  NGÀNH nào, theo hướng tích cực hay tiêu cực. Ví dụ: "giá dầu Brent tăng → tích cực cho
  nhóm dầu khí (**GAS, PVD, PVS, BSR**), tiêu cực cho vận tải/hàng không (**HVN, VJC**)".
- Ưu tiên nêu mã cổ phiếu Việt Nam liên quan trực tiếp. Nếu tin vĩ mô/quốc tế, quy về
  nhóm ngành VN hưởng lợi hoặc chịu ảnh hưởng.
- Đây là phân tích tác động khách quan, KHÔNG phải khuyến nghị mua/bán mã cụ thể.

SCHEMA:
{
  "tieu_de": "Tiêu đề ngắn bắt tin nổi bật nhất kiểu báo tài chính",
  "tom_tat": "3-5 câu tóm tắt toàn bộ bức tranh thị trường. Dùng **in đậm** cho số liệu.",
  "chi_so": [
    {"ten": "VN-Index",       "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat"},
    {"ten": "HNX-Index",      "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat"},
    {"ten": "UPCOM",          "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat"},
    {"ten": "S&P 500",        "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat"},
    {"ten": "Nasdaq",         "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat"},
    {"ten": "Dow Jones",      "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat"},
    {"ten": "Vang TG (XAU)",  "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat"},
    {"ten": "Vang SJC",       "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat"},
    {"ten": "Bitcoin",        "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat"},
    {"ten": "Dau Brent",      "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat"},
    {"ten": "USD/VND",        "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat"},
    {"ten": "LS lien NH qd",  "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat"}
  ],
  "toan_cau": "2-3 câu tóm tắt thị trường toàn cầu (Mỹ, châu Á, hàng hóa).",
  "sections": [
    {
      "so": "01",
      "tieu_de": "Market Note — TTCK Viet Nam",
      "icon": "📊",
      "noi_dung": "5-8 câu: VN-Index, thanh khoản, độ rộng, nhóm cổ phiếu nổi bật, cổ phiếu đóng góp/cản điểm. **In đậm** số liệu."
    },
    {
      "so": "02",
      "tieu_de": "Vi mo trong nuoc",
      "icon": "🏛",
      "noi_dung": "5-8 câu: GDP/CPI/PMI, lãi suất điều hành, lãi suất liên ngân hàng qua đêm, tỷ giá USD/VND, FDI, chính sách mới. **In đậm** số liệu."
    },
    {
      "so": "03",
      "tieu_de": "Dong tien & Vi the",
      "icon": "💰",
      "noi_dung": "5-8 câu: khối ngoại mua/bán ròng (cổ phiếu cụ thể), tự doanh, margin, thanh khoản theo nhóm. **In đậm** số liệu."
    },
    {
      "so": "04",
      "tieu_de": "Qua dem — Thi truong toan cau",
      "icon": "🌐",
      "noi_dung": "5-8 câu: S&P 500, Nasdaq, Dow Jones, châu Á (Nikkei, Hang Seng, Shanghai). Tác động tới VN. **In đậm** số liệu."
    },
    {
      "so": "05",
      "tieu_de": "Vang & Hang hoa",
      "icon": "🥇",
      "noi_dung": "5-8 câu: giá vàng thế giới, vàng SJC, dầu Brent/WTI, vận tải biển, các hàng hóa khác. **In đậm** số liệu."
    },
    {
      "so": "06",
      "tieu_de": "Tien dien tu (Crypto)",
      "icon": "₿",
      "noi_dung": "4-6 câu: Bitcoin, Ethereum, altcoin nổi bật, dòng vốn ETF, tâm lý thị trường. **In đậm** số liệu."
    },
    {
      "so": "07",
      "tieu_de": "Bat dong san",
      "icon": "🏢",
      "noi_dung": "4-6 câu: tin DN BĐS (VHM, NVL, DIG...), chính sách đất đai, tín dụng BĐS, dự án nổi bật. **In đậm** số liệu."
    },
    {
      "so": "08",
      "tieu_de": "Vi mo & Thoi su quoc te",
      "icon": "🌍",
      "noi_dung": "4-6 câu: Fed/ECB/BOJ, thương mại quốc tế, địa chính trị, sự kiện tác động thị trường. **In đậm** số liệu."
    },
    {
      "so": "09",
      "tieu_de": "Lich su kien & Du lieu can chu y",
      "icon": "📅",
      "noi_dung": "Liệt kê 4-6 sự kiện/dữ liệu kinh tế sắp công bố hoặc cần theo dõi trong tuần. Mỗi sự kiện 1 dòng."
    },
    {
      "so": "10",
      "tieu_de": "Goc nhin & Chien luoc",
      "icon": "🎯",
      "noi_dung": "5-8 câu: luận điểm bull, luận điểm bear, đánh giá tổng thể của desk. Kết bằng: KHONG phai khuyen nghi giao dich/dau tu."
    }
  ],
  "nguon": [
    {
      "ten_nguon": "Vietstock - Tin chung khoan",
      "cac_bai": [
        {"tieu_de": "Tiêu đề bài 1", "url": "https://..."},
        {"tieu_de": "Tiêu đề bài 2", "url": "https://..."}
      ]
    }
  ]
}

LƯU Ý NGUỒN:
- Liệt kê TẤT CẢ các nguồn đã dùng, gom theo tên nguồn (Vietstock, VnEconomy, CafeF, WSJ, CoinDesk...)
- Mỗi nguồn liệt kê TẤT CẢ bài đã dùng, có tiêu đề bài + URL đầy đủ
- Nếu URL không rõ, dùng URL gốc của nguồn đó (vd: https://vietstock.vn)
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
            print(f"[RETRY {attempt}/{API_RETRIES}] {e} — cho {wait}s...", flush=True)
            time.sleep(wait)
        except requests.exceptions.HTTPError as e:
            print(f"[LOI HTTP] {e}", file=sys.stderr)
            raise
    raise last_err


def _clean_json_text(text):
    text = unicodedata.normalize("NFC", text.strip())
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    text = text.strip()
    start = text.find('{')
    end   = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        text = text[start:end+1]
    return text


def trim_raw_data(raw_data, max_chars=14000):
    """Cắt gọn dữ liệu thô để tiết kiệm token API.
    Giữ nguyên cấu trúc nhóm, chỉ lấy phần đầu nếu quá dài."""
    if len(raw_data) <= max_chars:
        return raw_data
    # Cắt tại ranh giới dòng gần nhất để không đứt giữa 1 tin
    cut = raw_data[:max_chars]
    last_nl = cut.rfind('\n')
    if last_nl > max_chars * 0.8:
        cut = cut[:last_nl]
    return cut + "\n\n[... da cat bot de tiet kiem token ...]"


def get_json_data(raw_data, date_human, api_key):
    raw_data = trim_raw_data(raw_data)
    user_msg = (
        f"Hom nay {date_human} (gio VN). Du lieu tin tuc:\n\n{raw_data}\n\n"
        "Tra ve JSON theo schema, CHI JSON, bat dau { ket thuc }. "
        "Escape dau ngoac kep trong string bang \\\". Khong newline that trong string."
    )
    messages = [{"role": "user", "content": user_msg}]
    for attempt in range(1, 4):
        resp_data = call_api(messages, api_key)
        raw_text  = "".join(
            b["text"] for b in resp_data.get("content", []) if b.get("type") == "text"
        )
        text = _clean_json_text(raw_text)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"[LOI JSON lan {attempt}] {e}", flush=True)
            if attempt < 3:
                messages.append({"role": "assistant", "content": raw_text})
                messages.append({
                    "role": "user",
                    "content": (
                        f"JSON bi loi: {e}. Sua lai, tra ve JSON hop le hoan toan, "
                        "CHI JSON, bat dau {{ ket thuc }}."
                    )
                })
    print("[CANH BAO] Fallback JSON.", file=sys.stderr)
    return {
        "tieu_de": f"Ban tin TTCK {date_human}",
        "tom_tat": "He thong gap su co khi xu ly du lieu JSON.",
        "toan_cau": "",
        "chi_so": [],
        "sections": [{"so":"01","tieu_de":"Thong bao","icon":"⚠",
                       "noi_dung":"He thong gap su co. Ban tin se cap nhat lai."}],
        "nguon": [],
    }


def bold_to_html(s):
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = s.replace('\n', '<br>')
    return s


def render_card(c):
    gia_tri = str(c.get("gia_tri", "")).strip()
    # Bỏ qua thẻ không có dữ liệu (N/A) để không hiện một loạt thẻ trống xấu
    if not gia_tri or gia_tri.upper() in ("N/A", "NA", "-", "..."):
        return ""
    xu  = c.get("xu_huong", "flat")
    clr = "#1e6b3e" if xu=="up" else ("#8b1a1a" if xu=="down" else "#5a5248")
    bg  = "#e8f4ec" if xu=="up" else ("#faeaea" if xu=="down" else "#f0ede6")
    arr = "▲" if xu=="up" else ("▼" if xu=="down" else "≈")
    thay_doi = str(c.get("thay_doi", "")).strip()
    chg_html = ""
    if thay_doi and thay_doi.upper() not in ("N/A", "NA", "-"):
        chg_html = f'<div class="card-chg" style="color:{clr};background:{bg}">{arr} {thay_doi}</div>'
    return (
        f'<div class="card">'
        f'<div class="card-name">{c["ten"]}</div>'
        f'<div class="card-val">{gia_tri}</div>'
        f'{chg_html}'
        f'</div>'
    )


def render_section(s):
    return (
        f'<div class="panel">'
        f'<div class="panel-head">'
        f'<span class="panel-num">{s["so"]}</span>'
        f'<span class="panel-icon">{s.get("icon","")}</span>'
        f'<span class="panel-title">{s["tieu_de"].upper()}</span>'
        f'</div>'
        f'<p>{bold_to_html(s["noi_dung"])}</p>'
        f'</div>'
    )


def render_nguon(nguon_list):
    if not nguon_list:
        return "<li>Khong co thong tin nguon.</li>"
    rows = []
    for src in nguon_list:
        ten = src.get("ten_nguon", "Nguon")
        bais = src.get("cac_bai", [])
        if bais:
            links = " &middot; ".join(
                f'<a href="{b.get("url","#")}" target="_blank">{b.get("tieu_de","Xem bai")}</a>'
                for b in bais
            )
            rows.append(f'<li><strong>{ten}:</strong> {links}</li>')
        else:
            rows.append(f'<li><strong>{ten}</strong></li>')
    return "\n".join(rows)


def render_section_full(s):
    """Render mục cuối dạng vùng riêng full-width (không chia cột)."""
    return (
        f'<div class="panel-full">'
        f'<div class="panel-head">'
        f'<span class="panel-num">{s["so"]}</span>'
        f'<span class="panel-icon">{s.get("icon","")}</span>'
        f'<span class="panel-title">{s["tieu_de"].upper()}</span>'
        f'</div>'
        f'<p>{bold_to_html(s["noi_dung"])}</p>'
        f'</div>'
    )


def render_html(d, date_str, date_human, weekday_vn):
    cards_html    = "\n".join(render_card(c) for c in d.get("chi_so", []))
    sections      = d.get("sections", [])

    # Tách mục cuối ra vùng riêng full-width; các mục còn lại chia 3 cột
    full_html = ""
    grid_sections = sections
    if sections:
        last = sections[-1]
        grid_sections = sections[:-1]
        full_html = render_section_full(last)

    rows_html = ""
    for i in range(0, len(grid_sections), 3):
        chunk = grid_sections[i:i+3]
        panels = "\n".join(render_section(s) for s in chunk)
        rows_html += f'<div class="panel-grid">\n{panels}\n</div>\n'
    # Ghép vùng full-width của mục cuối vào sau lưới
    rows_html += full_html

    nguon_html  = render_nguon(d.get("nguon", []))
    tom_tat     = bold_to_html(d.get("tom_tat", ""))
    toan_cau    = d.get("toan_cau", "")

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ban tin TTCK | {date_str} — {d.get('tieu_de','')}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,'Segoe UI',Arial,sans-serif;background:#F5F0E8;color:#1a1714;font-size:15px;line-height:1.6}}
a{{color:#16263D;text-decoration:none}}a:hover{{text-decoration:underline}}
strong{{font-weight:700;color:#1a1714}}

.masthead{{background:#16263D;color:#c8bfa8;padding:7px 20px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px}}
.masthead a{{color:#c9a24b}}

.banner{{background:#1a1714;color:#F5F0E8;padding:32px 20px 22px;text-align:center;border-bottom:4px solid #c9a24b}}
.banner-eye{{font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:#c9a24b;margin-bottom:14px}}
.banner h1{{font-size:clamp(22px,3.8vw,40px);font-weight:900;line-height:1.12;max-width:720px;margin:0 auto 12px;letter-spacing:-.02em}}
.banner-meta{{font-size:12px;color:#a09580;letter-spacing:.06em;text-transform:uppercase}}

.disclaimer{{background:#eae4d8;text-align:center;font-size:12px;color:#6b6050;padding:8px 20px;border-bottom:1px solid #d4cabb}}

.wrap{{max-width:840px;margin:0 auto;padding:0 16px}}

.lede-box{{background:#fff;border:1px solid #ddd6c8;border-left:4px solid #16263D;padding:18px 22px;margin:20px 0;font-size:15.5px;line-height:1.8;color:#2a2520}}

/* CARDS — 6 trên 1 hàng desktop, 3 trên mobile */
.card-grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:#c8bfa8;border:1px solid #c8bfa8;margin:0 0 6px}}
.card{{background:#fff;padding:12px 10px;text-align:center}}
.card-name{{font-size:9.5px;letter-spacing:.09em;text-transform:uppercase;color:#7a7060;margin-bottom:5px}}
.card-val{{font-size:18px;font-weight:800;color:#16263D;line-height:1.15;margin-bottom:4px}}
.card-chg{{display:inline-block;font-size:10.5px;font-weight:700;padding:2px 6px;border-radius:2px}}
@media(max-width:640px){{.card-grid{{grid-template-columns:repeat(3,1fr)}}}}

.global-bar{{background:#16263D;color:#F5F0E8;padding:12px 20px;margin-bottom:1px;display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px}}
.gb-label{{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:#c9a24b;font-weight:700;white-space:nowrap;padding-top:2px}}
.gb-text{{font-size:13px;color:#c8bfa8;line-height:1.55;max-width:640px}}

/* PANELS — 3 cột, nhiều hàng */
.panel-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#c8bfa8;border:1px solid #c8bfa8;margin-bottom:1px}}
.panel{{background:#fff;padding:18px 16px}}
.panel-head{{display:flex;align-items:center;gap:7px;margin-bottom:11px;padding-bottom:9px;border-bottom:2px solid #1a1714}}
.panel-num{{background:#1a1714;color:#F5F0E8;font-size:11px;font-weight:800;width:22px;height:22px;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-variant-numeric:tabular-nums}}
.panel-icon{{font-size:15px;line-height:1}}
.panel-title{{font-size:12px;font-weight:800;letter-spacing:.03em;color:#1a1714;text-transform:uppercase}}
.panel p{{font-size:13.5px;line-height:1.72;color:#2a2520}}
@media(max-width:640px){{.panel-grid{{grid-template-columns:1fr}}}}

/* MỤC CUỐI — full width, nổi bật */
.panel-full{{background:#fff;border:1px solid #c8bfa8;border-top:4px solid #c9a24b;padding:24px 28px;margin-bottom:1px}}
.panel-full .panel-head{{border-bottom:2px solid #16263D}}
.panel-full .panel-title{{font-size:15px;color:#16263D}}
.panel-full p{{font-size:14.5px;line-height:1.8;color:#2a2520}}

/* LIÊN HỆ */
.contact-box{{background:#16263D;color:#F5F0E8;padding:24px 26px;margin:4px 0 4px;display:flex;justify-content:space-between;align-items:center;gap:24px;flex-wrap:wrap;border-top:4px solid #c9a24b}}
.contact-info{{flex:1;min-width:240px}}
.contact-head{{font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#c9a24b;margin-bottom:12px}}
.contact-phone{{font-size:22px;font-weight:800;margin-bottom:10px;color:#F5F0E8}}
.contact-phone a{{color:#F5F0E8;border-bottom:2px solid #c9a24b}}
.contact-desc{{font-size:13px;line-height:1.65;color:#c8bfa8;max-width:420px}}
.contact-qr{{text-align:center;background:#fff;padding:12px;border-radius:4px}}
.contact-qr img{{display:block}}
.qr-caption{{font-size:10.5px;color:#1a1714;margin-top:6px;font-weight:600;letter-spacing:.02em}}
@media(max-width:600px){{.contact-box{{justify-content:center;text-align:center}}.contact-info{{text-align:center}}.contact-desc{{margin:0 auto}}}}

/* NGUỒN */
.nguon-box{{background:#fff;border:1px solid #ddd6c8;padding:18px 22px;margin:4px 0 24px}}
.box-head{{font-size:11.5px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#16263D;border-bottom:2px solid #16263D;padding-bottom:8px;margin-bottom:14px}}
.nguon-box ul{{list-style:none;padding:0}}
.nguon-box li{{font-size:13px;line-height:1.8;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #f0ede6;color:#2a2520}}
.nguon-box li:last-child{{border-bottom:none;margin-bottom:0}}
.nguon-box a{{color:#16263D;border-bottom:1px dotted #c8bfa8;font-size:12.5px}}
.nguon-box a:hover{{border-bottom-style:solid}}

footer{{border-top:3px solid #1a1714;margin-top:8px;padding:16px 0 40px;display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}}
footer .legal{{font-size:11px;color:#7a7060;line-height:1.7;max-width:600px}}
footer .brand{{font-size:11px;color:#7a7060;font-weight:700;text-align:right}}
</style>
</head>
<body>

<div class="masthead">
  <span>Ban tin TTCK &middot; Research Note &middot; {weekday_vn}, {date_str}</span>
  <a href="./index.html">&#8592; Tat ca ban tin</a>
</div>

<div class="banner">
  <div class="banner-eye">Ban tin TTCK &mdash; Phat hanh sang som &mdash; {date_human}</div>
  <h1>{d.get('tieu_de', 'Ban tin TTCK')}</h1>
  <div class="banner-meta">{weekday_vn} &middot; {date_human} &middot; Gio Viet Nam</div>
</div>

<div class="disclaimer">&#9888; Tai lieu thong tin tong hop &mdash; KHONG phai khuyen nghi giao dich / dau tu</div>

<div class="wrap">

  <div class="lede-box">{tom_tat}</div>

  <div class="card-grid">
{cards_html}
  </div>

  <div class="global-bar">
    <span class="gb-label">Diem tin toan cau &middot; {date_str}</span>
    <span class="gb-text">{toan_cau}</span>
  </div>

{rows_html}

  <div class="contact-box">
    <div class="contact-info">
      <div class="contact-head">Lien he tu van dau tu</div>
      <p class="contact-phone">&#128222; Hotline: <a href="tel:0981340191">0981340191</a></p>
      <p class="contact-desc">Quet ma QR ben canh de tham gia nhom Zalo tu van dau tu,
      nhan ban tin va cap nhat thi truong hang ngay.</p>
    </div>
    <div class="contact-qr">
      <img src="./assets/zalo-qr.png" alt="QR Zalo tu van dau tu" width="140" height="140">
      <div class="qr-caption">Quet de tham gia nhom Zalo</div>
    </div>
  </div>

  <div class="nguon-box">
    <div class="box-head">Nguon tham khao</div>
    <ul>
{nguon_html}
    </ul>
  </div>

<footer>
  <div class="legal">
    Du lieu tong hop tu cac nguon cong khai (Vietstock, VnEconomy, CafeF, WSJ, CoinDesk...).
    Ban tin mang tinh thong tin tham khao, KHONG phai khuyen nghi giao dich / dau tu.
    Moi quyet dinh dau tu can dua tren phan tich doc lap va tu van chuyen gia tai chinh co chung chi.
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
                    parts = line.split("\t", 1)
                    if len(parts) == 2 and parts[0] != date_str:
                        entries.append((parts[0], parts[1]))
    entries.append((date_str, title))
    entries.sort(key=lambda x: x[0], reverse=True)
    with open(list_path, "w", encoding="utf-8") as f:
        for d, t in entries:
            f.write(f"{d}\t{t}\n")
    rows = "\n".join(
        f'<li><a href="./{d}.html">{d} &mdash; {t}</a></li>' for d, t in entries
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
h1{{font-size:1.5rem;margin-bottom:20px;border-bottom:3px solid #1a1714;padding-bottom:10px}}
ul{{list-style:none;padding:0}}
li{{margin:8px 0;padding:14px 18px;background:#fff;border:1px solid #ddd6c8;border-left:3px solid #16263D}}
a{{color:#16263D;font-weight:700;text-decoration:none}}
a:hover{{text-decoration:underline}}
</style></head><body>
<h1>Ban tin TTCK &mdash; Tat ca ban tin</h1>
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

    print("Dang goi Claude API lay JSON...", flush=True)
    data = get_json_data(raw_data, date_human, api_key)
    print(f"JSON OK — {data.get('tieu_de','?')}", flush=True)

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
