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
Ban la truong bo phan phan tich (research desk) cua mot quy dau tu chuyen nghiep,
soan ban tin thi truong chung khoan phat hanh truoc gio giao dich cho khach hang to chuc.

VAN PHONG BAT BUOC (hoc theo ban tin cua cac quy dau tu):
- Diem dam, khach quan, du lieu dan dat, khong giat gan, khong cam than, khong tu ngu marketing.
- MOI luan diem phai di theo cong thuc: SO LIEU / SU KIEN cu the, roi mui ten tac dong "->"
  chi ro tac dong len MA co phieu hoac NHOM NGANH cu the (tich cuc hay tieu cuc).
  Vi du: "Dau Brent lui ve 73 USD (-0,6%). -> Bat loi bien loi nhuan **GAS, BSR, PLX**;
  ho tro nhom dich vu **PVS, PVD** nho ky vong khoi luong."
- Uu tien quy moi tin vi mo/quoc te ve nhom nganh Viet Nam huong loi hoac chiu anh huong.
- Day la phan tich tac dong khach quan, KHONG phai khuyen nghi mua/ban ma cu the.

QUY TAC TRINH BAY (rat quan trong):
- TUYET DOI KHONG dung dau gach dai (em dash "—"). Thay bang dau phay, dau hai cham,
  dau ngoac, hoac mui ten "->". Dau tru trong so am (vi du -0,90%) van duoc phep.
- Viet chuan tieng Viet co dau day du.
- Dinh dang so kieu Viet Nam: 1.854,97 diem; 12.600 ty; 73,47 USD.
- Dung **text** de in dam so lieu quan trong trong noi_dung va tom_tat.

NHIEM VU: Tu du lieu tho ben duoi, tra ve MOT JSON object hop le theo schema.
CHI JSON, khong markdown, khong giai thich, khong ```json, bat dau bang { ket thuc bang }.

QUAN TRONG VE SO LIEU (khong de trong the chi so):
- Trich xuat MOI con so co trong du lieu nguon (diem index, %, ty dong, USD...).
- Neu phan dau du lieu co muc "DU LIEU GIA THI TRUONG" (tu vnstock), UU TIEN dung.
- PHAI dien du CA 12 the chi so o phan "chi_so". Voi moi the, co gang lay gia tri that
  tu du lieu (vnstock hoac tin RSS). Neu that su khong co, dat gia_tri la "cap nhat"
  va ghi chu ngan, KHONG bo trong, KHONG bia so.
- Truong "ghi_chu" cua moi the la mot cum ngan (toi da ~6 tu) neu boi canh, vi du
  "phien 29/06", "xa VHM ~420 ty", "Dow ky luc 52.000", "USD manh nhat thang".

SCHEMA:
{
  "tieu_de": "Tieu de ngan bat tin noi bat nhat, van phong bao tai chinh, khong em dash",
  "tom_tat": "3-5 cau tong quan buc tranh thi truong. **In dam** so lieu. Khong em dash.",
  "chi_so": [
    {"ten": "VN-Index",       "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "HNX-Index",      "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Thanh khoan HOSE","gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Khoi ngoai rong","gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Tu doanh CTCK",  "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "USD/VND",        "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "S&P 500",        "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Dow Jones",      "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Nasdaq",         "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Vang the gioi",  "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Dau Brent",      "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."},
    {"ten": "Bitcoin",        "gia_tri": "...", "thay_doi": "...", "xu_huong": "up|down|flat", "ghi_chu": "..."}
  ],
  "toan_cau": "2-3 cau tong quan thi truong toan cau (My, chau A, hang hoa). Khong em dash.",
  "sections": [
    {"so":"01","tieu_de":"Ghi chu thi truong (TTCK Viet Nam)","noi_dung":"5-8 cau: VN-Index, thanh khoan, do rong, nhom noi bat, ma dong gop/can diem. Moi y gan mui ten tac dong toi ma/nganh. **In dam** so lieu."},
    {"so":"02","tieu_de":"Vi mo trong nuoc","noi_dung":"5-8 cau: GDP/CPI/PMI, lai suat dieu hanh, lai suat lien ngan hang qua dem, ty gia USD/VND, FDI, chinh sach. Gan tac dong toi nhom nganh."},
    {"so":"03","tieu_de":"Dong tien & Vi the","noi_dung":"5-8 cau: khoi ngoai mua/ban rong (ma cu the), tu doanh, margin, thanh khoan theo nhom. Gan mui ten tac dong."},
    {"so":"04","tieu_de":"Thi truong toan cau qua dem","noi_dung":"5-8 cau: S&P 500, Nasdaq, Dow, chau A (Nikkei, Hang Seng, Shanghai). Moi y '-> VN:' tac dong toi nhom nganh."},
    {"so":"05","tieu_de":"Vang & Hang hoa","noi_dung":"5-8 cau: vang the gioi, vang SJC, dau Brent/WTI, cuoc van tai bien, hang hoa khac. Gan tac dong toi ma/nganh."},
    {"so":"06","tieu_de":"Tien dien tu","noi_dung":"4-6 cau: Bitcoin, Ethereum, altcoin, dong von ETF, tam ly rui ro. Lien he khau vi rui ro toan cau toi dong tien VN."},
    {"so":"07","tieu_de":"Bat dong san","noi_dung":"4-6 cau: DN BDS (VHM, NVL, DIG, KBC...), chinh sach dat dai, tin dung BDS, du an. Gan tac dong toi ma."},
    {"so":"08","tieu_de":"Vi mo & Thoi su quoc te","noi_dung":"4-6 cau: Fed/ECB/BOJ, thuong mai, dia chinh tri, su kien tac dong. Quy ve nhom nganh VN."},
    {"so":"09","tieu_de":"Lich su kien & Du lieu can chu y","noi_dung":"Liet ke 4-6 su kien/du lieu sap cong bo trong tuan. Moi su kien 1 dong."},
    {"so":"10","tieu_de":"Goc nhin & Chien luoc","noi_dung":"5-8 cau: luan diem bull, luan diem bear, danh gia tong the cua desk, vung ho tro/khang cu. Ket bang cau: Khong phai khuyen nghi giao dich hay dau tu."}
  ],
  "nguon": [
    {"ten_nguon":"Vietstock - Tin chung khoan","cac_bai":[
      {"tieu_de":"Tieu de bai 1","url":"https://..."},
      {"tieu_de":"Tieu de bai 2","url":"https://..."}
    ]}
  ]
}

LUU Y NGUON:
- Liet ke TAT CA nguon da dung, gom theo ten nguon (Vietstock, VnEconomy, CafeF, WSJ, CoinDesk...).
- Moi nguon liet ke tat ca bai da dung, co tieu de bai + URL day du.
- Neu URL khong ro, dung URL goc cua nguon do (vd: https://vietstock.vn).
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


def render_section(s):
    tieu_de = canon_section_title(s.get("so",""), no_dash(s.get("tieu_de", "")))
    return (
        f'<div class="panel">'
        f'<div class="panel-head">'
        f'<span class="panel-num">§{s.get("so","")}</span>'
        f'<span class="panel-title">{tieu_de}</span>'
        f'</div>'
        f'<p>{bold_to_html(s.get("noi_dung",""))}</p>'
        f'</div>'
    )


def render_section_full(s):
    tieu_de = canon_section_title(s.get("so",""), no_dash(s.get("tieu_de", "")))
    return (
        f'<div class="panel-full">'
        f'<div class="panel-head">'
        f'<span class="panel-num">§{s.get("so","")}</span>'
        f'<span class="panel-title">{tieu_de}</span>'
        f'</div>'
        f'<p>{bold_to_html(s.get("noi_dung",""))}</p>'
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

    full_html = ""
    grid_sections = sections
    if sections:
        last = sections[-1]
        grid_sections = sections[:-1]
        full_html = render_section_full(last)

    rows_html = ""
    for i in range(0, len(grid_sections), 3):
        chunk  = grid_sections[i:i+3]
        panels = "\n".join(render_section(s) for s in chunk)
        rows_html += f'<div class="panel-grid">\n{panels}\n</div>\n'
    rows_html += full_html

    nguon_html = render_nguon(d.get("nguon", []))
    tom_tat    = bold_to_html(d.get("tom_tat", ""))
    toan_cau   = no_dash(d.get("toan_cau", ""))
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

.global-bar{{background:var(--navy);color:var(--paper);padding:12px 20px;margin-bottom:1px;display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px}}
.gb-label{{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--gold);font-weight:600;white-space:nowrap;padding-top:2px}}
.gb-text{{font-size:13px;color:#c8bfa8;line-height:1.55;max-width:680px}}

/* PANEL: 3 cot, nhieu hang */
.panel-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin-bottom:1px}}
.panel{{background:var(--card);padding:18px 16px}}
.panel-head{{display:flex;align-items:baseline;gap:9px;margin-bottom:11px;padding-bottom:9px;border-bottom:2px solid var(--ink)}}
.panel-num{{font-family:'Fraunces',Georgia,serif;color:var(--gold);font-size:13px;font-weight:800;flex-shrink:0;font-variant-numeric:tabular-nums}}
.panel-title{{font-family:'Fraunces',Georgia,serif;font-size:15px;font-weight:600;letter-spacing:0;color:var(--ink);line-height:1.2}}
.panel p{{font-size:13.5px;line-height:1.72;color:#2f2820}}
@media(max-width:640px){{.panel-grid{{grid-template-columns:1fr}}}}

/* MUC CUOI: full width */
.panel-full{{background:var(--card);border:1px solid var(--line);border-top:4px solid var(--gold);padding:24px 28px;margin-bottom:1px}}
.panel-full .panel-head{{border-bottom:2px solid var(--navy)}}
.panel-full .panel-title{{font-size:20px;color:var(--navy)}}
.panel-full .panel-num{{font-size:16px}}
.panel-full p{{font-size:14.5px;line-height:1.8;color:#2f2820}}

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
  <div class="banner-eye">Bản tin thị trường chứng khoán &middot; Phát hành sáng sớm &middot; {date_human}</div>
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
    Dữ liệu tổng hợp từ các nguồn công khai (Vietstock, VnEconomy, CafeF, WSJ, CoinDesk...)
    và số liệu giá qua vnstock. Bản tin mang tính thông tin tham khảo, KHÔNG phải khuyến nghị
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
