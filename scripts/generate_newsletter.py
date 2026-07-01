"""
generate_newsletter.py — v5 (Hieuinvest)
Claude tra ve JSON -> script nhung vao template HTML co dinh (layout bao quy dau tu).

Thay doi v5:
- Van phong research desk cua quy dau tu, moi luan diem gan voi ma/nganh cu the.
- The chi so day du 2 hang x 6 cot, moi the co dong chu thich ngu canh.
- Ten de muc tieng Viet co dau, KHONG dung gach dai (em dash).
- Thuong hieu: Hieuinvest.
- Bo loc chan gach dai o moi noi dung tao ra.
"""

import os, sys, time, json, re, unicodedata, requests
from datetime import datetime, timezone, timedelta

API_URL     = "https://api.anthropic.com/v1/messages"
MODEL       = "claude-sonnet-4-6"
VN_TZ       = timezone(timedelta(hours=7))
MAX_TOKENS  = 12000
API_TIMEOUT = 600
API_RETRIES = 3
BRAND       = "Hieuinvest"

SYSTEM_PROMPT = """\
Bạn là chuyên viên phân tích thuộc khối Research của một công ty chứng khoán hàng đầu
(chuẩn mực như SSI Research, HSC, VNDirect Research, Dragon Capital, VinaCapital).
Soạn bản tin thị trường phát hành trước giờ giao dịch cho khách hàng tổ chức.

VĂN PHONG BẮT BUỘC (chuẩn báo cáo phân tích chuyên nghiệp):
- Điểm đạm, súc tích, khách quan, dữ liệu dẫn dắt. Không giật gân, không cảm thán, không marketing.
- Câu văn gọn, chuẩn thuật ngữ tài chính (thanh khoản, độ rộng, định giá P/E, dòng tiền, vị thế).
- MỖI ý phải đi theo công thức: SỐ LIỆU/SỰ KIỆN cụ thể, rồi mũi tên "->" chỉ rõ tác động lên
  MÃ cổ phiếu hoặc NHÓM NGÀNH cụ thể (tích cực/tiêu cực). Ví dụ:
  "Dầu Brent lùi về 73 USD (-0,6%). -> Bất lợi biên lợi nhuận GAS, BSR; hỗ trợ nhóm dịch vụ PVS, PVD."
- Ưu tiên quy tin vĩ mô/quốc tế về nhóm ngành Việt Nam hưởng lợi hoặc chịu ảnh hưởng.
- Đây là phân tích tác động khách quan, KHÔNG phải khuyến nghị mua/bán mã cụ thể.

VIẾT TIẾNG VIỆT CÓ DẤU ĐẦY ĐỦ. Đây là yêu cầu bắt buộc. Tất cả nội dung phải có dấu
tiếng Việt chuẩn (ví dụ: "thị trường", "chứng khoán", "ngân hàng", không phải "thi truong").

QUY TẮC TRÌNH BÀY (rất quan trọng):
- TUYỆT ĐỐI KHÔNG dùng dấu gạch dài (em dash "—"). Thay bằng dấu phẩy, hai chấm, ngoặc, hoặc "->".
  Dấu trừ trong số âm (ví dụ -0,90%) vẫn được phép.
- Định dạng số kiểu Việt Nam: 1.854,97 điểm; 12.600 tỷ; 73,47 USD.
- Dùng **text** để in đậm số liệu quan trọng (hệ thống tự chuyển thành chữ đậm, người đọc
  KHÔNG thấy dấu sao). Dùng đậm vừa phải, chỉ cho con số và mã cổ phiếu then chốt.

NHIỆM VỤ: Từ dữ liệu thô bên dưới, trả về MỘT JSON object hợp lệ theo schema.
CHỈ JSON, không markdown, không giải thích, không ```json, bắt đầu bằng { kết thúc bằng }.

CÁCH VIẾT MỖI MỤC (sections):
- "tom_luoc": một cụm RẤT NGẮN 3-7 từ tóm tắt diễn biến chính của mục (như tiêu đề phụ).
  Ví dụ: "Bán tháo trên diện rộng", "Dòng tiền nội xoay trục sang công nghệ", "Vốn ngoại rút ròng".
- "cac_y": MẢNG các chuỗi, MỖI phần tử là MỘT ý hoàn chỉnh, độc lập (một số liệu + tác động ->).
  Mỗi mục thường 3-6 ý. KHÔNG gộp nhiều ý vào một câu dài. Mỗi ý ngắn gọn, đi thẳng vấn đề.

QUAN TRỌNG VỀ SỐ LIỆU (không để trống thẻ chỉ số):
- Trích xuất MỌI con số có trong dữ liệu nguồn. Nếu đầu dữ liệu có mục "DU LIEU GIA THI TRUONG",
  ƯU TIÊN dùng. PHẢI điền đủ CẢ 12 thẻ "chi_so"; nếu thật sự không có số liệu, đặt gia_tri="cập nhật"
  và ghi_chu ngắn, KHÔNG bịa số.
- "ghi_chu": cụm rất ngắn (~6 từ) nêu bối cảnh, ví dụ "phiên 01/07", "xả VHM ~420 tỷ".

BẢNG TÁC ĐỘNG (bang_tac_dong): liệt kê các mã/nhóm ngành chịu tác động từ tin trong ngày.
- Nếu là CẢ MỘT NHÓM NGÀNH thì ghi tên NGÀNH (ví dụ "Ngành dầu khí", "Bất động sản KCN"),
  KHÔNG liệt kê lẻ từng mã. Nếu là mã riêng lẻ thì ghi mã (ví dụ "FPT", "VHM").
- "huong" chỉ nhận 1 trong: "Hưởng lợi" | "Bất lợi" | "Trung tính".
- Sắp xếp các dòng hưởng lợi trước, rồi bất lợi. Tối đa ~8 dòng.

SCHEMA:
{
  "tieu_de": "Tiêu đề ngắn bắt tin nổi bật nhất, văn phong báo tài chính, không em dash",
  "tom_tat": "3-5 câu tổng quan bức tranh thị trường. **In đậm** số liệu. Không em dash.",
  "chi_so": [
    {"ten": "VN-Index",        "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "HNX-Index",       "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Thanh khoản HOSE","gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Khối ngoại ròng", "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Tự doanh CTCK",   "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "USD/VND",         "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "S&P 500",         "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Dow Jones",       "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Nasdaq",          "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Vàng thế giới",   "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Dầu Brent",       "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Bitcoin",         "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."}
  ],
  "toan_cau": "2-4 câu tổng quan thị trường toàn cầu (Mỹ, châu Á, hàng hóa). **In đậm** số liệu. Không em dash.",
  "sections": [
    {"so":"01","tom_luoc":"...","cac_y":["...","..."]},
    {"so":"02","tom_luoc":"...","cac_y":["...","..."]},
    {"so":"03","tom_luoc":"...","cac_y":["...","..."]},
    {"so":"04","tom_luoc":"...","cac_y":["...","..."]},
    {"so":"05","tom_luoc":"...","cac_y":["...","..."]},
    {"so":"06","tom_luoc":"...","cac_y":["...","..."]},
    {"so":"07","tom_luoc":"...","cac_y":["...","..."]},
    {"so":"08","tom_luoc":"...","cac_y":["...","..."]},
    {"so":"09","tom_luoc":"...","cac_y":["sự kiện 1","sự kiện 2","..."]},
    {"so":"10","tom_luoc":"...","cac_y":["Luận điểm tích cực: ...","Luận điểm rủi ro: ...","Vùng hỗ trợ/kháng cự: ...","Không phải khuyến nghị giao dịch hay đầu tư."]}
  ],
  "bang_tac_dong": [
    {"doi_tuong":"FPT","huong":"Hưởng lợi","ly_do":"..."},
    {"doi_tuong":"Ngành dầu khí","huong":"Bất lợi","ly_do":"..."}
  ],
  "nguon": [
    {"ten_nguon":"Vietstock - Tin chứng khoán","cac_bai":[
      {"tieu_de":"Tiêu đề bài 1","url":"https://..."},
      {"tieu_de":"Tiêu đề bài 2","url":"https://..."}
    ]}
  ]
}

NỘI DUNG TỪNG MỤC:
01 Ghi chú thị trường TTCK VN: VN-Index/HNX/UPCOM, thanh khoản, độ rộng, nhóm dẫn dắt, mã đóng góp/cản điểm.
02 Vĩ mô trong nước: GDP/CPI/PMI, lãi suất điều hành, lãi suất liên ngân hàng qua đêm, tỷ giá, FDI, chính sách.
03 Dòng tiền & Vị thế: khối ngoại mua/bán ròng (mã cụ thể), tự doanh, margin, thanh khoản theo nhóm.
04 Thị trường toàn cầu qua đêm: S&P/Nasdaq/Dow, châu Á (Nikkei, Hang Seng, Shanghai). Mỗi ý quy về nhóm ngành VN.
05 Vàng & Hàng hóa: vàng thế giới, vàng SJC, dầu Brent/WTI, hàng hóa khác.
06 Tiền điện tử: Bitcoin, Ethereum, altcoin, dòng vốn ETF, khẩu vị rủi ro.
07 Bất động sản: DN BĐS (VHM, NVL, DIG, KBC...), chính sách đất đai, tín dụng BĐS, dự án.
08 Vĩ mô & Thời sự quốc tế: Fed/ECB/BOJ, thương mại, địa chính trị, sự kiện tác động.
09 Lịch sự kiện & Dữ liệu: 4-6 sự kiện/dữ liệu sắp công bố (mỗi sự kiện 1 phần tử cac_y).
10 Góc nhìn & Chiến lược: luận điểm tích cực, luận điểm rủi ro, đánh giá tổng thể, vùng hỗ trợ/kháng cự.

LƯU Ý NGUỒN:
- Liệt kê TẤT CẢ nguồn đã dùng, gom theo tên nguồn (Vietstock, VnEconomy, CafeF, VnExpress, WSJ, CNBC...).
- Mỗi nguồn liệt kê các bài đã dùng, có tiêu đề bài + URL đầy đủ.
- Nếu URL không rõ, dùng URL gốc của nguồn (vd: https://vietstock.vn).
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
    """Cat gon du lieu tho de tiet kiem token API."""
    if len(raw_data) <= max_chars:
        return raw_data
    cut = raw_data[:max_chars]
    last_nl = cut.rfind('\n')
    if last_nl > max_chars * 0.8:
        cut = cut[:last_nl]
    return cut + "\n\n[... da cat bot de tiet kiem token ...]"


def get_json_data(raw_data, date_human, api_key):
    raw_data = trim_raw_data(raw_data)
    user_msg = (
        f"Hom nay {date_human} (gio VN). Du lieu tin tuc:\n\n{raw_data}\n\n"
        "Tra ve JSON theo schema, CHI JSON, bat dau {{ ket thuc }}. "
        "Dien du 12 the chi_so, khong bo trong. Tuyet doi khong dung gach dai em dash. "
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
        "sections": [{"so":"01","tieu_de":"Thong bao",
                      "noi_dung":"He thong gap su co. Ban tin se cap nhat lai."}],
        "nguon": [],
    }


# ---------- Ten de muc CO DAU co dinh (khong phu thuoc Claude) ----------
SECTION_TITLES = {
    "01": "Ghi chú thị trường (TTCK Việt Nam)",
    "02": "Vĩ mô trong nước",
    "03": "Dòng tiền & Vị thế",
    "04": "Thị trường toàn cầu qua đêm",
    "05": "Vàng & Hàng hóa",
    "06": "Tiền điện tử",
    "07": "Bất động sản",
    "08": "Vĩ mô & Thời sự quốc tế",
    "09": "Lịch sự kiện & Dữ liệu cần chú ý",
    "10": "Góc nhìn & Chiến lược",
    "11": "Góc nhìn & Chiến lược",
}

# ---------- Ten the chi so CO DAU co dinh (chuan hoa theo ten Claude tra ve) ----------
CARD_NAMES = {
    "vn-index": "VN-Index", "vnindex": "VN-Index",
    "hnx-index": "HNX-Index", "hnxindex": "HNX-Index",
    "thanh khoan hose": "Thanh khoản HOSE",
    "khoi ngoai rong": "Khối ngoại ròng", "khoi ngoai": "Khối ngoại ròng",
    "tu doanh ctck": "Tự doanh CTCK", "tu doanh": "Tự doanh CTCK",
    "usd/vnd": "USD/VND", "usdvnd": "USD/VND",
    "s&p 500": "S&P 500", "sp500": "S&P 500", "s&p500": "S&P 500",
    "dow jones": "Dow Jones", "dow": "Dow Jones",
    "nasdaq": "Nasdaq",
    "vang the gioi": "Vàng thế giới", "vang tg": "Vàng thế giới",
    "dau brent": "Dầu Brent", "brent": "Dầu Brent",
    "bitcoin": "Bitcoin", "btc": "Bitcoin",
}


def _deaccent(s):
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).lower().strip()


def canon_card_name(ten):
    return CARD_NAMES.get(_deaccent(ten), ten)


def canon_section_title(so, fallback):
    return SECTION_TITLES.get(str(so).zfill(2), fallback)


# ---------- Bo loc chan gach dai (em dash) o moi noi dung ----------
def no_dash(s):
    """Loai bo gach dai em dash de van phong khong 'giong AI'."""
    if not isinstance(s, str):
        s = str(s)
    s = s.replace(" — ", ", ").replace("— ", ", ").replace(" —", ",").replace("—", ", ")
    s = s.replace(" – ", ", ").replace("–", "-")  # en dash -> gach ngan thuong
    return s


def bold_to_html(s):
    s = no_dash(s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = s.replace('\n', '<br>')
    return s


def render_card(c):
    """The chi so 4 dong: ten, gia tri, thay doi, chu thich. Luon render de day 2 hang."""
    ten     = canon_card_name(no_dash(str(c.get("ten", "")).strip()))
    gia_tri = no_dash(str(c.get("gia_tri", "")).strip())
    if not gia_tri or gia_tri.upper() in ("N/A", "NA", "-", "..."):
        gia_tri = "cập nhật"
    xu  = c.get("xu_huong", "flat")
    clr = "#2f6b3e" if xu == "up" else ("#8b2e2e" if xu == "down" else "#6b5f47")
    bg  = "#e6efdf" if xu == "up" else ("#f3e3df" if xu == "down" else "#efe6cf")
    arr = "▲" if xu == "up" else ("▼" if xu == "down" else "•")
    thay_doi = no_dash(str(c.get("thay_doi", "")).strip())
    chg_html = ""
    if thay_doi and thay_doi.upper() not in ("N/A", "NA", "-"):
        chg_html = f'<div class="card-chg" style="color:{clr};background:{bg}">{arr} {thay_doi}</div>'
    ghi_chu  = no_dash(str(c.get("ghi_chu", "")).strip())
    note_html = f'<div class="card-note">{ghi_chu}</div>' if ghi_chu else ""
    return (
        f'<div class="card">'
        f'<div class="card-name">{ten}</div>'
        f'<div class="card-val">{gia_tri}</div>'
        f'{chg_html}'
        f'{note_html}'
        f'</div>'
    )


def _get_points(s):
    """Lay danh sach cac y tu section. Uu tien 'cac_y' (mang); neu chi co
    'noi_dung' (chuoi cu) thi tach thanh cac y theo xuong dong hoac theo cau."""
    ys = s.get("cac_y")
    if isinstance(ys, list) and ys:
        return [str(y).strip() for y in ys if str(y).strip()]
    nd = str(s.get("noi_dung", "")).strip()
    if not nd:
        return []
    if "\n" in nd:
        return [p.strip() for p in nd.split("\n") if p.strip()]
    # tach theo cau: giu dau cham, tranh tach nham so thap phan
    parts = re.split(r'(?<=[.!?])\s+(?=[A-ZĐÀÁẢÃẠÂẦẤẨẪẬĂẰẮẲẴẶÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ0-9])', nd)
    return [p.strip() for p in parts if p.strip()]


def render_points_html(s):
    pts = _get_points(s)
    if not pts:
        return '<p class="pt">Đang cập nhật.</p>'
    return "\n".join(f'<p class="pt">{bold_to_html(p)}</p>' for p in pts)


def render_head_html(s):
    tieu_de = canon_section_title(s.get("so",""), no_dash(s.get("tieu_de", "")))
    tom_luoc = no_dash(str(s.get("tom_luoc", "")).strip())
    sub = f'<div class="panel-sub">{tom_luoc}</div>' if tom_luoc else ""
    return (
        f'<div class="panel-head">'
        f'<span class="panel-num">§{s.get("so","")}</span>'
        f'<span class="panel-title">{tieu_de}</span>'
        f'</div>'
        f'{sub}'
    )


def render_section(s):
    return (
        f'<div class="panel">'
        f'{render_head_html(s)}'
        f'<div class="panel-body">{render_points_html(s)}</div>'
        f'</div>'
    )


HUONG_STYLE = {
    "huong loi": ("Hưởng lợi", "#2f6b3e", "#e6efdf"),
    "bat loi":   ("Bất lợi",   "#8b2e2e", "#f3e3df"),
    "trung tinh":("Trung tính","#6b5f47", "#efe6cf"),
}


def render_impact_table(rows):
    if not rows:
        return ""
    trs = []
    for r in rows:
        doi_tuong = no_dash(str(r.get("doi_tuong", "")).strip())
        ly_do     = no_dash(str(r.get("ly_do", "")).strip())
        huong_raw = _deaccent(str(r.get("huong", "trung tinh")))
        label, clr, bg = HUONG_STYLE.get(huong_raw, HUONG_STYLE["trung tinh"])
        trs.append(
            f'<tr>'
            f'<td class="imp-obj">{doi_tuong}</td>'
            f'<td class="imp-dir"><span class="imp-tag" style="color:{clr};background:{bg}">{label}</span></td>'
            f'<td class="imp-why">{bold_to_html(ly_do)}</td>'
            f'</tr>'
        )
    return (
        '<div class="impact">'
        '<table class="impact-tbl">'
        '<thead><tr><th>Đối tượng</th><th>Tác động</th><th>Lý do</th></tr></thead>'
        f'<tbody>{"".join(trs)}</tbody>'
        '</table>'
        '<div class="impact-note">Tác động ước tính từ tin tức trong ngày, mang tính tham khảo.</div>'
        '</div>'
    )


def render_impact_full(bang_tac_dong):
    """§10 Bảng tác động: full-width panel riêng."""
    table_html = render_impact_table(bang_tac_dong)
    if not table_html:
        return ""
    return (
        f'<div class="panel-full">'
        f'<div class="panel-head">'
        f'<span class="panel-num">§10</span>'
        f'<span class="panel-title">Mã & Nhóm ngành tác động</span>'
        f'</div>'
        f'<div class="panel-sub">Tổng hợp tác động từ tin tức trong ngày</div>'
        f'{table_html}'
        f'</div>'
    )


def render_strategy_full(s):
    """§11 Góc nhìn & Chiến lược: full-width panel riêng."""
    tieu_de = canon_section_title(s.get("so",""), no_dash(s.get("tieu_de", "")))
    return (
        f'<div class="panel-full">'
        f'{render_head_html({"so":"11","tom_luoc":s.get("tom_luoc","")})}'
        f'<div class="panel-body">{render_points_html(s)}</div>'
        f'</div>'
    )


def render_nguon(nguon_list):
    if not nguon_list:
        return "<li>Không có thông tin nguồn.</li>"
    rows = []
    for src in nguon_list:
        ten  = no_dash(src.get("ten_nguon", "Nguồn"))
        bais = src.get("cac_bai", [])
        if bais:
            links = " &middot; ".join(
                f'<a href="{b.get("url","#")}" target="_blank" rel="noopener">'
                f'{no_dash(b.get("tieu_de","Xem bài"))}</a>'
                for b in bais
            )
            rows.append(f'<li><strong>{ten}:</strong> {links}</li>')
        else:
            rows.append(f'<li><strong>{ten}</strong></li>')
    return "\n".join(rows)


def render_html(d, date_str, date_human, weekday_vn):
    cards_html = "\n".join(render_card(c) for c in d.get("chi_so", []))
    sections   = d.get("sections", [])

    # Sections 01-09 in 3-col grid, section 10 (strategy) rendered after impact table
    grid_sections = sections[:9] if len(sections) >= 9 else sections
    strategy_section = sections[9] if len(sections) >= 10 else None

    rows_html = ""
    for i in range(0, len(grid_sections), 3):
        chunk  = grid_sections[i:i+3]
        panels = "\n".join(render_section(s) for s in chunk)
        rows_html += f'<div class="panel-grid">\n{panels}\n</div>\n'

    # §10: Bang tac dong (full width)
    rows_html += render_impact_full(d.get("bang_tac_dong", []))

    # §11: Goc nhin & Chien luoc (full width)
    if strategy_section:
        rows_html += render_strategy_full(strategy_section)

    nguon_html = render_nguon(d.get("nguon", []))
    tom_tat    = bold_to_html(d.get("tom_tat", ""))
    toan_cau   = bold_to_html(d.get("toan_cau", ""))
    tieu_de    = no_dash(d.get("tieu_de", "Bản tin TTCK"))

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{BRAND} | Bản tin TTCK {date_str} | {tieu_de}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,800&family=Source+Serif+4:wght@400;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--paper:#F1E7D0;--card:#FBF6EA;--ink:#26201A;--navy:#1B2A22;--gold:#A9863F;--gold-soft:#B99A55;--line:#CBBB98;--muted:#8a7c62}}
body{{font-family:'Source Serif 4',Georgia,serif;color:var(--ink);font-size:15px;line-height:1.62;
background-color:var(--paper);
background-image:
 radial-gradient(120% 90% at 50% 0%,rgba(255,251,240,.55),rgba(255,251,240,0) 55%),
 linear-gradient(rgba(38,32,26,.012),rgba(38,32,26,.03)),
 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.045'/%3E%3C/svg%3E");
background-attachment:fixed,fixed,scroll}}
a{{color:var(--navy);text-decoration:none}}a:hover{{text-decoration:underline}}
strong{{font-weight:600;color:var(--ink)}}
.serif{{font-family:'Fraunces',Georgia,serif}}

.masthead{{background:var(--navy);color:var(--line);padding:7px 20px;font-size:11px;letter-spacing:.14em;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px}}
.masthead b{{color:#F5F0E8;letter-spacing:.16em}}
.masthead a{{color:var(--gold)}}

.banner{{background:var(--ink);color:var(--paper);padding:34px 20px 24px;text-align:center;border-bottom:4px solid var(--gold)}}
.banner-brand{{font-family:'Fraunces',Georgia,serif;font-size:14px;font-weight:800;letter-spacing:.28em;text-transform:uppercase;color:var(--gold);margin-bottom:14px}}
.banner-eye{{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:#a09580;margin-bottom:12px}}
.banner h1{{font-family:'Fraunces',Georgia,serif;font-size:clamp(24px,4vw,42px);font-weight:800;line-height:1.1;max-width:760px;margin:0 auto 12px;letter-spacing:-.01em}}
.banner-meta{{font-size:12px;color:#a09580;letter-spacing:.08em;text-transform:uppercase}}

.disclaimer{{background:#E7DBC0;text-align:center;font-size:12px;color:#6b5c44;padding:8px 20px;border-bottom:1px solid #cbbb98;letter-spacing:.02em}}

.wrap{{max-width:900px;margin:0 auto;padding:0 16px}}

.lede-box{{background:var(--card);border:1px solid #D8C9A6;border-left:4px solid var(--navy);padding:18px 22px;margin:20px 0;font-size:15.5px;line-height:1.8;color:#2f2820}}

/* THE CHI SO: 6 cot x 2 hang tren desktop, 3 cot tren mobile */
.card-grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin:0 0 6px}}
.card{{background:var(--card);padding:12px 10px;text-align:center;display:flex;flex-direction:column;align-items:center;justify-content:flex-start}}
.card-name{{font-family:'Source Serif 4',serif;font-size:9.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin-bottom:5px;font-weight:600}}
.card-val{{font-family:'Fraunces',Georgia,serif;font-size:18px;font-weight:800;color:var(--navy);line-height:1.12;margin-bottom:4px}}
.card-chg{{display:inline-block;font-size:10.5px;font-weight:600;padding:2px 6px;border-radius:2px;margin-bottom:4px}}
.card-note{{font-size:9.5px;line-height:1.35;color:#8a7c62;margin-top:auto}}
@media(max-width:640px){{.card-grid{{grid-template-columns:repeat(3,1fr)}}}}

.global-bar{{background:var(--navy);color:var(--paper);padding:16px 24px;margin-bottom:1px}}
.gb-label{{display:block;font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--gold);font-weight:700;margin-bottom:9px;padding-bottom:8px;border-bottom:1px solid rgba(201,162,75,.32)}}
.gb-text{{display:block;font-size:14px;color:#e4dcc8;line-height:1.78;text-align:justify}}
.gb-text strong{{color:#fbf6ea}}

/* PANEL: 3 cot, nhieu hang */
.panel-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin-bottom:1px}}
.panel{{background:var(--card);padding:18px 16px}}
.panel-head{{display:flex;align-items:baseline;gap:9px;margin-bottom:11px;padding-bottom:9px;border-bottom:2px solid var(--ink)}}
.panel-num{{font-family:'Fraunces',Georgia,serif;color:var(--gold);font-size:13px;font-weight:800;flex-shrink:0;font-variant-numeric:tabular-nums}}
.panel-title{{font-family:'Fraunces',Georgia,serif;font-size:15px;font-weight:600;letter-spacing:0;color:var(--ink);line-height:1.2}}
.panel-sub{{font-family:'Fraunces',Georgia,serif;font-style:italic;font-size:12.5px;color:var(--gold);margin:-4px 0 11px;line-height:1.35}}
.panel-body .pt{{font-size:13.5px;line-height:1.66;color:#2f2820;margin:0 0 9px;padding-left:12px;position:relative}}
.panel-body .pt:last-child{{margin-bottom:0}}
.panel-body .pt::before{{content:"";position:absolute;left:0;top:9px;width:4px;height:4px;border-radius:50%;background:var(--gold)}}
@media(max-width:640px){{.panel-grid{{grid-template-columns:1fr}}}}

/* MUC FULL-WIDTH (§10 bang tac dong, §11 goc nhin) */
.panel-full{{background:var(--card);border:1px solid var(--line);border-top:4px solid var(--gold);padding:24px 28px;margin-bottom:1px}}
.panel-full .panel-head{{border-bottom:2px solid var(--navy)}}
.panel-full .panel-title{{font-size:19px;color:var(--navy)}}
.panel-full .panel-num{{font-size:15px}}
.panel-full .panel-body .pt{{font-size:14px;line-height:1.78}}

.impact{{margin-top:6px}}
.impact-tbl{{width:100%;border-collapse:collapse;font-size:13px}}
.impact-tbl th{{text-align:left;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:700;padding:0 12px 8px 0;border-bottom:1px solid var(--line)}}
.impact-tbl td{{padding:10px 12px 10px 0;vertical-align:top;border-bottom:1px solid #ece0c6;line-height:1.6;color:#2f2820}}
.impact-tbl tr:last-child td{{border-bottom:none}}
.imp-obj{{font-weight:700;color:var(--ink);white-space:nowrap;min-width:120px}}
.imp-tag{{display:inline-block;font-size:11px;font-weight:700;padding:3px 10px;border-radius:2px;white-space:nowrap}}
.imp-why{{font-size:13px;line-height:1.65}}
.impact-note{{font-size:10.5px;color:var(--muted);margin-top:12px;font-style:italic}}

/* LIEN HE */
.contact-box{{background:var(--navy);color:var(--paper);padding:24px 26px;margin:4px 0;display:flex;justify-content:space-between;align-items:center;gap:24px;flex-wrap:wrap;border-top:4px solid var(--gold)}}
.contact-info{{flex:1;min-width:240px}}
.contact-head{{font-family:'Fraunces',Georgia,serif;font-size:13px;font-weight:800;letter-spacing:.16em;text-transform:uppercase;color:var(--gold);margin-bottom:12px}}
.contact-phone{{font-size:22px;font-weight:600;margin-bottom:10px;color:var(--paper)}}
.contact-phone a{{color:var(--paper);border-bottom:2px solid var(--gold)}}
.contact-desc{{font-size:13px;line-height:1.65;color:#c8bfa8;max-width:440px}}
.contact-qr{{text-align:center;background:#fff;padding:12px;border-radius:4px}}
.contact-qr img{{display:block}}
.qr-caption{{font-size:10.5px;color:var(--ink);margin-top:6px;font-weight:600;letter-spacing:.02em}}
@media(max-width:600px){{.contact-box{{justify-content:center;text-align:center}}.contact-info{{text-align:center}}.contact-desc{{margin:0 auto}}}}

/* NGUON */
.nguon-box{{background:var(--card);border:1px solid #D8C9A6;padding:18px 22px;margin:4px 0 24px}}
.box-head{{font-family:'Fraunces',Georgia,serif;font-size:13px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--navy);border-bottom:2px solid var(--navy);padding-bottom:8px;margin-bottom:14px}}
.nguon-box ul{{list-style:none;padding:0}}
.nguon-box li{{font-size:13px;line-height:1.8;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #ece0c6;color:#2f2820}}
.nguon-box li:last-child{{border-bottom:none;margin-bottom:0}}
.nguon-box a{{color:var(--navy);border-bottom:1px dotted var(--line);font-size:12.5px}}
.nguon-box a:hover{{border-bottom-style:solid}}

footer{{border-top:3px solid var(--ink);margin-top:8px;padding:16px 0 40px;display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}}
footer .legal{{font-size:11px;color:var(--muted);line-height:1.7;max-width:620px}}
footer .brand{{font-family:'Fraunces',Georgia,serif;font-size:12px;color:var(--muted);font-weight:800;text-align:right;letter-spacing:.06em}}
</style>
</head>
<body>

<div class="masthead">
  <span><b>{BRAND}</b> &middot; Daily Research &middot; {weekday_vn}, {date_str}</span>
  <a href="./index.html">&#8592; Tất cả bản tin</a>
</div>

<div class="banner">
  <div class="banner-brand">{BRAND}</div>
  <div class="banner-eye">Bản tin thị trường chứng khoán &middot; {date_human}</div>
  <h1>{tieu_de}</h1>
  <div class="banner-meta">{weekday_vn} &middot; {date_human} &middot; Giờ Việt Nam</div>
</div>

<div class="disclaimer">&#9888; Tài liệu thông tin tổng hợp &middot; KHÔNG phải khuyến nghị giao dịch hay đầu tư</div>

<div class="wrap">

  <div class="lede-box">{tom_tat}</div>

  <div class="card-grid">
{cards_html}
  </div>

  <div class="global-bar">
    <span class="gb-label">Điểm tin toàn cầu &middot; {date_str}</span>
    <span class="gb-text">{toan_cau}</span>
  </div>

{rows_html}

  <div class="contact-box">
    <div class="contact-info">
      <div class="contact-head">Liên hệ tư vấn đầu tư &middot; {BRAND}</div>
      <p class="contact-phone">&#128222; Hotline: <a href="tel:0981340191">0981340191</a></p>
      <p class="contact-desc">Quét mã QR bên cạnh để tham gia nhóm Zalo tư vấn đầu tư,
      nhận bản tin và cập nhật thị trường hằng ngày.</p>
    </div>
    <div class="contact-qr">
      <img src="../qr%20zalo.jpg" alt="QR Zalo tư vấn đầu tư {BRAND}" width="140" height="140">
      <div class="qr-caption">Quét để tham gia nhóm Zalo</div>
    </div>
  </div>

  <div class="nguon-box">
    <div class="box-head">Nguồn tham khảo</div>
    <ul>
{nguon_html}
    </ul>
  </div>

<footer>
  <div class="legal">
    Dữ liệu tổng hợp từ các nguồn công khai (Vietstock, VnEconomy, CafeF, VnExpress, WSJ, CNBC...)
    và số liệu giá qua Yahoo Finance, VNDIRECT, TCBS. Bản tin mang tính thông tin tham khảo, KHÔNG phải khuyến nghị
    giao dịch hay đầu tư. Mọi quyết định đầu tư cần dựa trên phân tích độc lập và tư vấn từ
    chuyên gia tài chính có chứng chỉ hành nghề.
  </div>
  <div class="brand">{BRAND}<br>{date_str}</div>
</footer>

</div>
</body>
</html>"""


def update_index(output_dir, date_str, title):
    title = no_dash(title)
    list_path  = os.path.join(output_dir, "_entries.tsv")
    index_path = os.path.join(output_dir, "index.html")
    entries = []
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
        f'<li><a href="./{d}.html"><span class="d">{d}</span>{no_dash(t)}</a></li>'
        for d, t in entries
    )
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
<html lang="vi"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{BRAND} | Bản tin TTCK</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,800&family=Source+Serif+4:wght@400;600&display=swap" rel="stylesheet">
<style>
body{{font-family:'Source Serif 4',Georgia,serif;max-width:720px;margin:40px auto;
padding:0 16px;background:#F1E7D0;color:#26201A}}
h1{{font-family:'Fraunces',Georgia,serif;font-size:1.6rem;margin-bottom:6px;letter-spacing:-.01em}}
.sub{{color:#7a7060;font-size:13px;margin-bottom:20px;border-bottom:3px solid #1a1714;padding-bottom:14px;letter-spacing:.04em;text-transform:uppercase}}
ul{{list-style:none;padding:0}}
li{{margin:8px 0;padding:14px 18px;background:#FBF6EA;border:1px solid #D8C9A6;border-left:3px solid #1B2A22}}
a{{color:#1B2A22;font-weight:600;text-decoration:none;display:block}}
a:hover{{text-decoration:underline}}
.d{{display:inline-block;font-family:'Fraunces',Georgia,serif;font-weight:800;color:#A9863F;margin-right:10px}}
</style></head><body>
<h1>{BRAND}</h1>
<div class="sub">Bản tin thị trường chứng khoán &middot; Tất cả bản tin</div>
<ul>{rows}</ul>
</body></html>""")


WEEKDAYS_VN = ["Thứ Hai","Thứ Ba","Thứ Tư","Thứ Năm","Thứ Sáu","Thứ Bảy","Chủ Nhật"]


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
