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

YÊU CẦU KỸ THUẬT (HTML):
- Trả về MỘT file HTML hoàn chỉnh, bắt đầu bằng <!DOCTYPE html>, có <head> với <meta charset="utf-8">,
  <meta name="viewport" content="width=device-width,initial-scale=1">, và <title>.
- CSS nhúng trực tiếp trong <style> ở head (không dùng file ngoài). Thiết kế: nền sáng, font sans-serif
  dễ đọc, các "thẻ chỉ số" (stat cards) dạng lưới responsive, màu xanh lá cho tăng (▲), đỏ cho giảm (▼),
  responsive tốt trên di động.
- Có thanh điều hướng nhỏ ở đầu trang link về trang index (dùng đường dẫn tương đối "./index.html").
- KHÔNG dùng JavaScript ngoài, KHÔNG gọi tài nguyên external ngoài Google Fonts (tùy chọn).
- Output CHỈ là mã HTML, không kèm lời giải thích, không bọc trong ```html.
"""


def call_claude(user_content: str, api_key: str) -> str:
    resp = requests.post(
        API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 16000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_content}],
        },
        timeout=300,
    )
    if resp.status_code != 200:
        print("Lỗi gọi Claude API:", resp.status_code, resp.text[:2000], file=sys.stderr)
        resp.raise_for_status()

    data = resp.json()
    parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    return "\n".join(parts).strip()


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
        f'<li><a href="./{d}.html">{d} — {t}</a></li>' for d, t in entries
    )

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bản tin TTCK — Tất cả bản tin</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; max-width: 720px;
        margin: 40px auto; padding: 0 16px; color: #1a1a1a; background: #fafafa; }}
h1 {{ font-size: 1.4rem; }}
ul {{ list-style: none; padding: 0; }}
li {{ margin: 10px 0; padding: 14px 16px; background: #fff; border: 1px solid #e5e5e5;
      border-radius: 8px; }}
a {{ text-decoration: none; color: #1a4d2e; font-weight: 600; }}
a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>📈 Bản tin TTCK — Tất cả bản tin</h1>
<ul>
{rows}
</ul>
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
