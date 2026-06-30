"""
generate_newsletter.py
Gọi Claude API để tổng hợp dữ liệu thô (raw_sources.txt) thành một bản tin
HTML hoàn chỉnh, theo đúng cấu trúc/văn phong của file mẫu.

Yêu cầu biến môi trường: ANTHROPIC_API_KEY

Chạy:
    python3 fetch_sources.py > raw_sources.txt
    python3 generate_newsletter.py
"""

import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta

import requests

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"

# Giờ Việt Nam (UTC+7) — vì GitHub Actions chạy theo giờ UTC
VN_TZ = timezone(timedelta(hours=7))


SYSTEM_PROMPT = """Bạn là một agent tổng hợp tin tức tài chính, chuyên viết "Bản tin TTCK" hằng ngày
bằng tiếng Việt, theo đúng văn phong và cấu trúc của một bản tin chuyên nghiệp dạng research note.

NHIỆM VỤ: Từ danh sách tin tức thô được cung cấp (đã gom theo nhóm chủ đề), hãy viết một bản tin
HTML hoàn chỉnh, độc lập (self-contained), đẹp, chuyên nghiệp.

YÊU CẦU NỘI DUNG:
- Văn phong: ngắn gọn, số liệu cụ thể, khách quan, đúng kiểu phân tích thị trường chuyên nghiệp.
  Mỗi nhận định quan trọng nên có một dòng "→ VN: ..." hoặc "→ Tác động: ..." diễn giải ý nghĩa/
  tác động tới nhà đầu tư, KHÔNG đưa khuyến nghị mua/bán cụ thể.
- Cấu trúc gồm các phần (đánh số § 01, § 02...), điều chỉnh linh hoạt theo dữ liệu thực tế có được,
  nhưng nên bao quát các nhóm sau nếu có dữ liệu:
  § Tiêu đề + tóm tắt mở đầu (3-5 câu) + các chỉ số nổi bật dạng thẻ (VN-Index, thanh khoản, khối
    ngoại, S&P 500, vàng, Bitcoin...)
  § Qua đêm — toàn cầu (chứng khoán Mỹ, châu Á)
  § Vàng & Hàng hóa
  § Tiền điện tử (Crypto)
  § Vĩ mô & Thời sự (trong nước + quốc tế)
  § Bất động sản
  § Dòng tiền & vị thế (khối ngoại, tự doanh — nếu có dữ liệu)
  § Trong nước — tín hiệu thị trường chứng khoán VN
  § Lịch sự kiện sắp tới (nếu có thông tin)
  § Góc nhìn & chiến lược — đánh giá ngắn của "desk" theo 2 chiều bull/bear, kết bằng 1 đoạn
    "Đánh giá của desk" cân bằng cả 2 phía, không thiên lệch, không phải khuyến nghị giao dịch.
- LUÔN ghi rõ ràng: "không phải khuyến nghị giao dịch / đầu tư" ở các chỗ liên quan.
- Cuối bài PHẢI có mục "Nguồn" liệt kê toàn bộ các link nguồn đã dùng, có tên nguồn + tiêu đề tin
  + link gốc.
- CHỈ dùng thông tin có trong dữ liệu được cung cấp. KHÔNG bịa số liệu. Nếu một nhóm chủ đề không có
  dữ liệu nào trong nguồn, bỏ qua nhóm đó hoặc ghi "Không có cập nhật đáng chú ý trong khung giờ này".
- Diễn giải/tóm tắt bằng lời văn của bạn, KHÔNG trích dẫn nguyên văn dài từ nguồn (tôn trọng bản quyền).

YÊU CẦU VỀ THẺ CHỈ SỐ (stat cards) — RẤT QUAN TRỌNG:
- Mỗi thẻ chỉ số (VN-Index, S&P 500, Vàng, Bitcoin, DXY, Dầu WTI...) PHẢI hiển thị:
  1. Tên chỉ số
  2. Giá trị/điểm số TUYỆT ĐỐI cụ thể (vd: "1.854,97 điểm", "$3.412,50", "$108.420")
  3. % thay đổi so với phiên/kỳ trước, kèm dấu (+/-) và mũi tên ▲ (xanh, tăng) hoặc ▼ (đỏ, giảm).
     Định dạng ví dụ: "▲ +0,42%" hoặc "▼ -1,18%".
- CHỈ lấy số liệu (giá trị tuyệt đối VÀ % thay đổi) khi dữ liệu nguồn có đề cập trực tiếp.
  KHÔNG được tự tính toán % thay đổi nếu nguồn không cung cấp đủ 2 mốc giá để so sánh, và
  KHÔNG được tự bịa ra một con số % nghe hợp lý — bịa số liệu tài chính là vi phạm nghiêm trọng
  yêu cầu của bản tin này.
- Nếu nguồn có giá trị tuyệt đối nhưng KHÔNG có % thay đổi cụ thể, hiển thị giá trị tuyệt đối kèm
  dòng phụ "chưa rõ % so với phiên trước" thay vì để trống hoàn toàn hoặc bịa số.
- Chỉ khi HOÀN TOÀN không có bất kỳ con số nào cho 1 chỉ số trong dữ liệu nguồn, mới hiển thị "N/A"
  cho riêng chỉ số đó — không vì thiếu 1-2 chỉ số mà để toàn bộ các thẻ khác cũng thành N/A.

YÊU CẦU VỀ ĐỘ DÀI:
- Đây là điều RẤT QUAN TRỌNG: bạn có giới hạn độ dài output. Hãy viết SÚC TÍCH ở từng mục
  (mỗi đoạn phân tích 3-6 câu là đủ, không lan man, không lặp ý) để đảm bảo viết được ĐẦY ĐỦ
  TẤT CẢ các mục đã lên kế hoạch (kể cả §07, §08...) thay vì viết rất dài ở các mục đầu rồi
  bị hụt ở các mục cuối. Ưu tiên sự đầy đủ và hoàn chỉnh của toàn bộ bản tin hơn là độ chi tiết
  của từng mục riêng lẻ.
- Bản tin PHẢI kết thúc đúng bằng thẻ đóng </html>. Tuyệt đối không được dừng giữa chừng một thẻ
  hay một câu văn.

YÊU CẦU KỸ THUẬT (HTML) — THIẾT KẾ "BROADSHEET" CỐ ĐỊNH:
Đây là bản tin có giao diện thương hiệu cố định kiểu trang nhất báo tài chính in (đen-trắng-xám
cổ điển, khung viền rõ, không phải landing page hiện đại). PHẢI dùng CHÍNH XÁC khối <style> dưới
đây (copy nguyên văn, không đổi tên class, không đổi font, không đổi màu), chỉ thay nội dung bên
trong các thẻ HTML cho khớp với dữ liệu hôm nay:

```
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600;700;800;900&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --paper: #F3F1EA; --ink: #1A1A1A; --ink-soft: #4A4A47; --line: #1A1A1A;
    --line-soft: #C9C5B8; --panel: #FFFFFF; --rise: #1F5C3A; --rise-bg: #E5EEE7;
    --fall: #8B2E22; --fall-bg: #F3E5E2; --tag-bg: #1A1A1A;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: #DAD6C8; color: var(--ink); font-family: 'Source Serif 4', Georgia, serif; -webkit-font-smoothing: antialiased; }
  .sheet { max-width: 920px; margin: 28px auto; background: var(--paper); border: 1.5px solid var(--ink); padding: 28px 32px 0; }
  .nav-strip { display: flex; justify-content: space-between; font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-soft); margin-bottom: 14px; }
  .nav-strip a { color: var(--ink); text-decoration: none; border-bottom: 1px solid var(--ink); }
  .eyebrow-row { text-align: center; font-family: 'IBM Plex Mono', monospace; font-size: 11.5px; letter-spacing: 0.22em; color: var(--ink-soft); margin-bottom: 10px; }
  .masthead { text-align: center; border-top: 3px solid var(--ink); border-bottom: 3px solid var(--ink); padding: 18px 0 16px; }
  .masthead-title { font-family: 'Playfair Display', serif; font-weight: 900; font-size: clamp(30px, 5vw, 48px); letter-spacing: -0.01em; line-height: 1; margin: 0 0 6px; }
  .masthead-sub { font-family: 'IBM Plex Mono', monospace; font-size: 12px; letter-spacing: 0.18em; color: var(--ink-soft); }
  .issue-bar { display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; font-family: 'IBM Plex Mono', monospace; font-size: 11.5px; letter-spacing: 0.04em; padding: 10px 0; border-bottom: 1.5px solid var(--ink); margin-bottom: 22px; }
  .issue-bar .tag { background: var(--tag-bg); color: var(--paper); padding: 2px 9px; }
  .panel-grid { display: grid; grid-template-columns: 1.3fr 1fr 1fr; gap: 0; border-top: 1.5px solid var(--ink); }
  .panel { padding: 18px 20px; border-right: 1px solid var(--ink); border-bottom: 1.5px solid var(--ink); }
  .panel:last-child { border-right: none; }
  .panel-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
  .panel-num { background: var(--ink); color: var(--paper); font-family: 'IBM Plex Mono', monospace; font-size: 12px; font-weight: 600; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .panel-title { font-family: 'Playfair Display', serif; font-weight: 700; font-size: 14.5px; letter-spacing: 0.01em; text-transform: uppercase; }
  .panel p { font-size: 14px; line-height: 1.65; color: var(--ink); margin: 0 0 10px; }
  .panel ul { margin: 0 0 6px; padding-left: 16px; }
  .panel li { font-size: 13.5px; line-height: 1.6; margin-bottom: 8px; }
  .panel b { font-weight: 700; }
  .dropcap::first-letter { font-family: 'Playfair Display', serif; font-weight: 900; font-size: 52px; float: left; line-height: 0.78; padding: 4px 6px 0 0; }
  .mini-chart { display: flex; align-items: flex-end; gap: 6px; height: 90px; margin: 14px 0 4px; border-bottom: 1px solid var(--line-soft); padding-bottom: 4px; }
  .mini-bar { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; }
  .mini-bar .bar { width: 100%; }
  .mini-bar .val { font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; margin-bottom: 3px; }
  .mini-chart-labels { display: flex; gap: 6px; font-family: 'IBM Plex Mono', monospace; font-size: 9px; color: var(--ink-soft); text-align: center; }
  .mini-chart-labels span { flex: 1; }
  .stat-mini-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: var(--ink); margin-top: 8px; }
  .stat-mini { background: var(--panel); padding: 10px 12px; }
  .stat-mini .lbl { font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: 0.05em; color: var(--ink-soft); text-transform: uppercase; }
  .stat-mini .val { font-family: 'Playfair Display', serif; font-weight: 700; font-size: 18px; margin: 3px 0 2px; }
  .stat-mini .chg { font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; }
  .stat-mini .chg.up { color: var(--rise); }
  .stat-mini .chg.down { color: var(--fall); }
  .stat-mini .chg.na { color: var(--ink-soft); font-weight: 400; font-size: 10px; }
  .breadth-bar { display: flex; height: 22px; margin: 8px 0; border: 1px solid var(--ink); font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; font-weight: 600; }
  .breadth-bar .up { background: var(--rise); color: #fff; display: flex; align-items: center; justify-content: center; }
  .breadth-bar .flat { background: #BFBBA9; display: flex; align-items: center; justify-content: center; font-size: 9px; color: var(--ink); }
  .breadth-bar .down { background: var(--fall); color: #fff; display: flex; align-items: center; justify-content: center; }
  .full-section { border-top: 1.5px solid var(--ink); padding: 22px 0 26px; }
  .full-head { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
  .full-num { background: var(--ink); color: var(--paper); font-family: 'IBM Plex Mono', monospace; font-size: 13px; font-weight: 600; width: 26px; height: 26px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .full-title { font-family: 'Playfair Display', serif; font-weight: 800; font-size: 21px; }
  .full-sub { font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; letter-spacing: 0.08em; color: var(--ink-soft); text-transform: uppercase; }
  .ticker-strip { display: grid; grid-template-columns: repeat(7, 1fr); gap: 1px; background: var(--ink); border: 1px solid var(--ink); margin-bottom: 16px; }
  .ticker-cell { background: var(--panel); padding: 10px 8px; text-align: center; }
  .ticker-cell .lbl { font-family: 'IBM Plex Mono', monospace; font-size: 9px; letter-spacing: 0.04em; color: var(--ink-soft); text-transform: uppercase; margin-bottom: 4px; }
  .ticker-cell .val { font-family: 'Playfair Display', serif; font-weight: 700; font-size: 15px; }
  .ticker-cell .chg { font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 600; display: block; margin-top: 2px; }
  .ticker-cell .chg.up { color: var(--rise); }
  .ticker-cell .chg.down { color: var(--fall); }
  .ticker-cell .chg.na { color: var(--ink-soft); font-weight: 400; }
  @media (max-width: 700px) { .ticker-strip { grid-template-columns: repeat(3, 1fr); } .panel-grid { grid-template-columns: 1fr; } .panel { border-right: none; } }
  .col2 { columns: 2; column-gap: 28px; }
  .col2 p { margin: 0 0 12px; }
  .full-section p.body { font-size: 14.5px; line-height: 1.75; margin: 0 0 14px; }
  .full-section p.body b { font-weight: 700; }
  .impact { border-left: 3px solid var(--ink); padding: 4px 0 4px 14px; margin: 16px 0; font-size: 13.5px; line-height: 1.6; }
  .impact b { font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.06em; }
  .quote-box { background: var(--panel); border: 1px solid var(--ink); padding: 16px 18px; margin: 16px 0; font-size: 13.5px; line-height: 1.7; }
  .quote-box .tag-label { font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 8px; display: inline-block; border-bottom: 1.5px solid var(--ink); padding-bottom: 2px; }
  .duo-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0; border: 1px solid var(--ink); }
  .duo-col { padding: 18px 20px; }
  .duo-col.bull { border-right: 1px solid var(--ink); }
  .duo-head { font-family: 'IBM Plex Mono', monospace; font-size: 11.5px; letter-spacing: 0.06em; text-transform: uppercase; font-weight: 600; margin-bottom: 12px; }
  .duo-col ul { margin: 0; padding-left: 16px; }
  .duo-col li { font-size: 13.5px; line-height: 1.6; margin-bottom: 8px; }
  .desk-box { border: 1px solid var(--ink); border-top: none; padding: 18px 20px; background: var(--ink); color: var(--paper); }
  .desk-box .duo-head { color: var(--paper); }
  .desk-box p { font-size: 13.5px; line-height: 1.75; margin: 0; color: #DEDBCE; }
  @media (max-width: 700px) { .duo-grid { grid-template-columns: 1fr; } .duo-col.bull { border-right: none; border-bottom: 1px solid var(--ink); } }
  .sources-list { font-size: 12.5px; line-height: 2; color: var(--ink-soft); }
  .sources-list a { color: var(--ink); text-decoration: none; border-bottom: 1px solid var(--line-soft); }
  footer { border-top: 3px solid var(--ink); padding: 16px 0 26px; display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; flex-wrap: wrap; }
  footer .legal { font-family: 'IBM Plex Mono', monospace; font-size: 10px; line-height: 1.7; color: var(--ink-soft); max-width: 600px; }
  footer .brand { font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; text-align: right; color: var(--ink-soft); }
  footer .brand b { color: var(--ink); }
</style>
```

CẤU TRÚC HTML BẮT BUỘC (bọc trong <div class="sheet">...</div> bên trong <body>):

1. `.nav-strip` — bên trái ghi "Phát hành hằng ngày · Thị trường tài chính Việt Nam & Toàn cầu",
   bên phải link `<a href="./index.html">← Tất cả bản tin</a>`.
2. `.eyebrow-row` — dòng chữ nhỏ kiểu "5 PHÚT ĐỌC ĐỂ NẮM BẮT THỊ TRƯỜNG".
3. `.masthead` — `.masthead-title` LUÔN LÀ CHỮ "HIEUINVEST" (tên thương hiệu cố định, không đổi),
   `.masthead-sub` LUÔN LÀ "BẢN TIN TÀI CHÍNH HẰNG NGÀY".
4. `.issue-bar` — 3 mục: "THỨ [X] · [ngày]/[tháng]/[năm]", `<span class="tag">SỐ [ddmmyy]</span>`,
   "CẬP NHẬT PHIÊN [ngày]/[tháng]".
5. `.panel-grid` (3 cột, dùng cho §01 Tổng quan phiên / §02 Vĩ mô & Thời sự / §03 Trong nước —
   TTCK VN dạng tóm tắt số liệu): mỗi `.panel` có `.panel-head` (số + tiêu đề), nội dung là
   `<p class="dropcap">` cho đoạn mở đầu (chỉ dùng dropcap cho panel đầu tiên), `<ul><li>` cho các
   gạch đầu dòng vĩ mô, và với panel chỉ số dùng `.stat-mini-grid` + `.breadth-bar` để thể hiện
   VN-Index/VN30/HNX/thanh khoản và độ rộng phiên (số mã tăng/giảm) nếu có dữ liệu.
   Panel đầu tiên CÓ THỂ thêm `.mini-chart` (biểu đồ cột nhỏ) NẾU dữ liệu nguồn có ít nhất 3-5 mốc
   điểm số gần đây; nếu không đủ dữ liệu lịch sử, BỎ QUA mini-chart, không bịa số liệu lịch sử.
6. `.full-section` chứa `.ticker-strip` (7 ô) cho §04 Điểm tin Kinh tế Toàn cầu — mỗi `.ticker-cell`
   là 1 chỉ số quốc tế (S&P 500, Dow Jones, Nikkei, DXY, Vàng, Dầu, Bitcoin), theo đúng quy định
   "YÊU CẦU VỀ THẺ CHỈ SỐ" ở trên. Theo sau là `.col2` (2 cột text) cho phân tích Mỹ/châu Á, và
   `.impact` cho dòng tác động.
7. `.panel-grid` thứ 2 (3 cột nhỏ) cho §05 Vàng & Hàng hóa / §06 Crypto / §07 Bất động sản — mỗi
   mục chỉ cần 1 đoạn `<p>` ngắn súc tích.
8. `.full-section` với `.quote-box` cho §08 Dòng tiền & Vị thế (đặt phần "phân tích chuyên sâu"
   nếu dữ liệu có, vd review ETF, dòng vốn khối ngoại).
9. `.full-section` chứa `.duo-grid` (2 cột bull/bear) + `.desk-box` (nền đen) cho §09 Góc nhìn &
   Chiến lược — đúng yêu cầu nội dung bull/bear/đánh giá desk đã nêu ở trên.
10. `.full-section` cuối với `.sources-list` cho mục Nguồn tham khảo — liệt kê đầy đủ link nguồn
    đã dùng.
11. Nếu có "Lịch sự kiện sắp tới", chèn thêm 1 `.full-section` riêng trước phần Góc nhìn & Chiến
    lược, dùng `<ul><li>` liệt kê sự kiện.
12. `footer` cuối cùng: `.legal` bên trái (nguyên văn câu miễn trừ trách nhiệm chuẩn), `.brand`
    bên phải ghi "HIEUINVEST — Bản tin Tài chính" + "Cập nhật tự động hằng ngày".

QUY TẮC CHUNG:
- Toàn bộ trang phải nằm trong `<div class="sheet">`, không thêm `<header>`/nav nào khác ngoài
  cấu trúc trên.
- KHÔNG tự sáng tạo thêm class CSS mới hay đổi màu sắc/font ngoài bộ đã cho — đây là bộ nhận
  diện thương hiệu cố định, phải nhất quán giữa các ngày.
- Có thể bỏ qua một panel/section nếu HOÀN TOÀN không có dữ liệu cho mục đó, nhưng KHÔNG được bỏ
  qua cấu trúc masthead/issue-bar/footer.
- Trả về MỘT file HTML hoàn chỉnh, bắt đầu bằng <!DOCTYPE html>, có <head> với
  <meta charset="utf-8">, <meta name="viewport" content="width=device-width,initial-scale=1">,
  <title>, và toàn bộ khối <link>/<style> nêu trên trong <head>.
- KHÔNG dùng JavaScript.
- Output CHỈ là mã HTML, không kèm lời giải thích, không bọc trong ```html.
"""


MAX_TOKENS = 28000
MAX_CONTINUATIONS = 4  # số lần tối đa cho phép "viết tiếp" nếu bị cắt giữa chừng


def _request_claude(messages, api_key):
    resp = requests.post(
        API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM_PROMPT,
            "messages": messages,
        },
        timeout=300,
    )
    if resp.status_code != 200:
        print("Lỗi gọi Claude API:", resp.status_code, resp.text[:2000], file=sys.stderr)
        resp.raise_for_status()
    return resp.json()


def call_claude(user_content: str, api_key: str) -> str:
    """Gọi Claude API để sinh HTML. Nếu output bị cắt giữa chừng do hết
    max_tokens (stop_reason == 'max_tokens'), tự động gọi tiếp để Claude
    viết nối phần còn thiếu, ghép lại thành 1 file HTML hoàn chỉnh."""

    messages = [{"role": "user", "content": user_content}]
    full_text = ""

    for attempt in range(1 + MAX_CONTINUATIONS):
        data = _request_claude(messages, api_key)
        parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        chunk = "\n".join(parts)
        full_text += chunk

        stop_reason = data.get("stop_reason")
        if stop_reason != "max_tokens":
            break  # viết xong bình thường (hoặc lỗi khác không phải do thiếu chỗ)

        print(f"[CẢNH BÁO] Output bị cắt do hết max_tokens (lần {attempt + 1}), "
              f"đang yêu cầu Claude viết tiếp...", flush=True)

        # Thêm phần đã viết vào lịch sử hội thoại, yêu cầu viết tiếp đúng từ chỗ dừng
        messages.append({"role": "assistant", "content": chunk})
        messages.append({
            "role": "user",
            "content": (
                "Nội dung bị cắt giữa chừng vì hết giới hạn độ dài. "
                "Hãy viết tiếp CHÍNH XÁC từ chỗ bị dừng (không lặp lại phần đã viết, "
                "không thêm lời mở đầu/giải thích) cho đến khi hoàn chỉnh toàn bộ file HTML, "
                "kết thúc bằng </html>."
            ),
        })
    else:
        print("[CẢNH BÁO] Đã thử viết tiếp nhiều lần nhưng vẫn chưa hoàn chỉnh.", file=sys.stderr)

    return full_text.strip()


def clean_html(text: str) -> str:
    """Phòng trường hợp model lỡ bọc trong ```html ... ```"""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
    return t.strip()


def update_index(output_dir: str, date_str: str, title: str):
    """Cập nhật/tạo file index.html liệt kê tất cả bản tin theo ngày, mới nhất lên đầu."""
    index_path = os.path.join(output_dir, "index.html")
    entries = []

    # Đọc danh sách entries hiện có (nếu index.html đã có, parse đơn giản qua file .csv riêng)
    list_path = os.path.join(output_dir, "_entries.tsv")
    if os.path.exists(list_path):
        with open(list_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    d, t = line.split("\t", 1)
                    if d != date_str:  # tránh trùng nếu chạy lại cùng ngày
                        entries.append((d, t))

    entries.append((date_str, title))
    entries.sort(key=lambda x: x[0], reverse=True)

    with open(list_path, "w", encoding="utf-8") as f:
        for d, t in entries:
            f.write(f"{d}\t{t}\n")

    rows = "\n".join(
        f'    <li><a href="./{d}.html"><span>{t}</span><span class="date">{d}</span></a></li>'
        for d, t in entries
    )

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hieuinvest — Bản tin Tài chính — Tất cả bản tin</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Source+Serif+4:opsz,wght@8..60,400&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  body {{ margin: 0; background: #DAD6C8; color: #1A1A1A; font-family: 'Source Serif 4', Georgia, serif; }}
  .sheet {{ max-width: 720px; margin: 28px auto; background: #F3F1EA; border: 1.5px solid #1A1A1A; padding: 28px 32px 36px; }}
  .eyebrow {{ text-align: center; font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.2em; color: #4A4A47; margin-bottom: 8px; }}
  h1 {{ font-family: 'Playfair Display', serif; font-weight: 900; font-size: 34px; text-align: center;
        border-top: 3px solid #1A1A1A; border-bottom: 3px solid #1A1A1A; padding: 16px 0; margin: 0 0 24px; }}
  ul {{ list-style: none; padding: 0; margin: 0; }}
  li {{ border-bottom: 1px solid #C9C5B8; }}
  li a {{ display: flex; justify-content: space-between; gap: 16px; padding: 14px 4px; text-decoration: none; color: #1A1A1A; font-size: 14.5px; }}
  li a:hover {{ background: #FFFFFF; }}
  li a .date {{ font-family: 'IBM Plex Mono', monospace; font-size: 11.5px; color: #4A4A47; white-space: nowrap; }}
</style>
</head>
<body>
<div class="sheet">
  <div class="eyebrow">HIEUINVEST</div>
  <h1>Bản tin Tài chính</h1>
  <ul>
{rows}
  </ul>
</div>
</body>
</html>
"""
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("LỖI: thiếu biến môi trường ANTHROPIC_API_KEY", file=sys.stderr)
        sys.exit(1)

    raw_path = "raw_sources.txt"
    if not os.path.exists(raw_path):
        print(f"LỖI: không tìm thấy {raw_path}. Hãy chạy fetch_sources.py trước.", file=sys.stderr)
        sys.exit(1)

    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data = f.read()

    now_vn = datetime.now(VN_TZ)
    date_str = now_vn.strftime("%Y-%m-%d")
    date_human = now_vn.strftime("%d.%m.%Y")

    user_content = f"""Hôm nay là {date_human} (giờ Việt Nam). Dưới đây là dữ liệu tin tức thô đã
gom theo nhóm chủ đề (chứng khoán VN, thế giới, vàng & hàng hóa, crypto, vĩ mô & thời sự,
bất động sản). Hãy viết bản tin HTML hoàn chỉnh theo đúng hướng dẫn trong system prompt.

Tiêu đề bản tin nên là một câu ngắn bắt thời sự nhất trong ngày (giống kiểu
"Vingroup đè chỉ số, thế giới lập kỷ lục mới"), tự đặt dựa trên tin nổi bật nhất.

=== DỮ LIỆU THÔ ===
{raw_data}
"""

    print("Đang gọi Claude API để tổng hợp bản tin...", flush=True)
    html = call_claude(user_content, api_key)
    html = clean_html(html)

    output_dir = "bantin"
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{date_str}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Đã lưu bản tin: {out_path}", flush=True)

    # cố gắng lấy <title> để hiển thị trong index
    title = date_str
    if "<title>" in html:
        try:
            title = html.split("<title>", 1)[1].split("</title>", 1)[0].strip()
        except Exception:
            pass

    update_index(output_dir, date_str, title)
    print("Đã cập nhật index.html", flush=True)


if __name__ == "__main__":
    main()
