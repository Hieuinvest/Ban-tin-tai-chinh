"""
generate_newsletter.py
Gọi Claude API để tổng hợp dữ liệu thô (raw_sources.txt) thành bản tin HTML.
Tự động viết tiếp nếu bị cắt giữa chừng (stop_reason == max_tokens).
Yêu cầu: biến môi trường ANTHROPIC_API_KEY
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta

API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = "claude-sonnet-4-6"
VN_TZ   = timezone(timedelta(hours=7))

MAX_TOKENS       = 16000
MAX_CONTINUATIONS = 3
API_TIMEOUT       = 600   # 10 phút — tránh bị đứt kết nối
API_RETRIES       = 3     # thử lại tối đa 3 lần nếu bị ConnectionError

SYSTEM_PROMPT = """\
Bạn là một agent tổng hợp tin tức tài chính, chuyên viết "Bản tin TTCK" hằng ngày
bằng tiếng Việt, theo đúng văn phong và cấu trúc của một bản tin chuyên nghiệp dạng research note.

NHIỆM VỤ: Từ danh sách tin tức thô được cung cấp (đã gom theo nhóm chủ đề), hãy viết một bản tin
HTML hoàn chỉnh, độc lập (self-contained), đẹp, chuyên nghiệp.

YÊU CẦU NỘI DUNG:
- Văn phong: ngắn gọn, số liệu cụ thể, khách quan, đúng kiểu phân tích thị trường chuyên nghiệp.
  Mỗi nhận định quan trọng nên có một dòng "→ VN: ..." hoặc "→ Tác động: ..." diễn giải ý nghĩa
  tác động tới nhà đầu tư. KHÔNG đưa khuyến nghị mua/bán cụ thể.
- Cấu trúc gồm các phần (đánh số § 01, § 02...) bao quát các nhóm sau nếu có dữ liệu:
  § 01: Tiêu đề + tóm tắt mở đầu (3-5 câu) + các thẻ chỉ số nổi bật
  § 02: Qua đêm — toàn cầu (chứng khoán Mỹ, châu Á)
  § 03: Vàng & Hàng hóa
  § 04: Tiền điện tử (Crypto)
  § 05: Vĩ mô & Thời sự (trong nước + quốc tế)
  § 06: Bất động sản
  § 07: Dòng tiền & vị thế (khối ngoại, tự doanh)
  § 08: Trong nước — tín hiệu thị trường chứng khoán VN
  § 09: Góc nhìn & chiến lược (bull/bear + đánh giá desk)
  § 10: Nguồn tham khảo
- LUÔN ghi rõ: "không phải khuyến nghị giao dịch / đầu tư".
- CHỈ dùng thông tin có trong dữ liệu được cung cấp. KHÔNG bịa số liệu.
- Diễn giải bằng lời văn của bạn, KHÔNG trích dẫn nguyên văn dài từ nguồn.

YÊU CẦU VỀ THẺ CHỈ SỐ (stat cards):
- Mỗi thẻ PHẢI hiển thị: (1) Tên chỉ số, (2) Giá trị tuyệt đối cụ thể,
  (3) % thay đổi so với phiên trước kèm mũi tên ▲ (tăng, màu xanh) hoặc ▼ (giảm, màu đỏ).
- CHỈ lấy số liệu khi nguồn có đề cập trực tiếp. KHÔNG tự bịa % thay đổi.
- Nếu có giá trị tuyệt đối nhưng không có %, ghi "chưa rõ % so phiên trước".
- Chỉ khi HOÀN TOÀN không có số liệu mới ghi N/A.

YÊU CẦU VỀ ĐỘ DÀI — RẤT QUAN TRỌNG:
- Viết SÚC TÍCH (3-5 câu/mục). Ưu tiên viết ĐỦ TẤT CẢ các mục hơn là viết dài 1 mục.
- Bản tin PHẢI kết thúc bằng thẻ đóng </html>. KHÔNG được dừng giữa chừng.

YÊU CẦU KỸ THUẬT HTML:
- Trả về MỘT file HTML hoàn chỉnh bắt đầu bằng <!DOCTYPE html>.
- CSS nhúng trong <style> ở head. Thiết kế: nền giấy kem (#FAF7F0), font chữ chuyên nghiệp,
  thẻ chỉ số dạng lưới responsive, màu xanh cho tăng ▲, đỏ cho giảm ▼.
- Có link về trang index: <a href="./index.html">← Tất cả bản tin</a>.
- KHÔNG dùng JavaScript ngoài. Output CHỈ là mã HTML, không kèm lời giải thích, không bọc trong ```html.
"""


def _call_api_once(messages: list, api_key: str) -> dict:
    """Gọi API 1 lần, retry nếu bị lỗi kết nối (ConnectionError/Timeout)."""
    last_err = None
    for attempt in range(1, API_RETRIES + 1):
        try:
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
                timeout=API_TIMEOUT,
            )
            if resp.status_code != 200:
                print(f"[LỖI API] HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
                resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_err = e
            wait = 15 * attempt
            print(f"[CẢNH BÁO] Lỗi kết nối lần {attempt}/{API_RETRIES}: {e}. "
                  f"Thử lại sau {wait}s...", flush=True)
            time.sleep(wait)
    raise last_err


def call_claude(user_content: str, api_key: str) -> str:
    """Gọi Claude, tự động viết tiếp nếu bị cắt do max_tokens."""
    messages   = [{"role": "user", "content": user_content}]
    full_text  = ""

    for attempt in range(1 + MAX_CONTINUATIONS):
        data  = _call_api_once(messages, api_key)
        parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        chunk = "\n".join(parts)
        full_text += chunk

        if data.get("stop_reason") != "max_tokens":
            break

        print(f"[CẢNH BÁO] Bị cắt do max_tokens (lần {attempt+1}), đang viết tiếp...", flush=True)
        messages.append({"role": "assistant", "content": chunk})
        messages.append({
            "role": "user",
            "content": (
                "Nội dung bị cắt do hết giới hạn. Hãy viết tiếp CHÍNH XÁC từ chỗ dừng "
                "(không lặp lại phần đã viết, không thêm lời giải thích) đến khi hoàn chỉnh "
                "file HTML, kết thúc bằng </html>."
            ),
        })
    else:
        print("[CẢNH BÁO] Đã viết tiếp nhiều lần nhưng vẫn chưa hoàn chỉnh.", file=sys.stderr)

    return full_text.strip()


def clean_html(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
    return t.strip()


def update_index(output_dir: str, date_str: str, title: str):
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
    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bản tin TTCK — Tất cả bản tin</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:720px;
margin:40px auto;padding:0 16px;color:#1a1a1a;background:#FAF7F0;}}
h1{{font-size:1.4rem;}}
ul{{list-style:none;padding:0;}}
li{{margin:10px 0;padding:14px 16px;background:#fff;border:1px solid #e5e5e5;border-radius:8px;}}
a{{text-decoration:none;color:#16263D;font-weight:600;}}
a:hover{{text-decoration:underline;}}
</style>
</head>
<body>
<h1>📈 Bản tin TTCK — Tất cả bản tin</h1>
<ul>
{rows}
</ul>
</body>
</html>"""
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

    now_vn     = datetime.now(VN_TZ)
    date_str   = now_vn.strftime("%Y-%m-%d")
    date_human = now_vn.strftime("%d.%m.%Y")

    user_content = (
        f"Hôm nay là {date_human} (giờ Việt Nam). Dưới đây là dữ liệu tin tức thô đã gom "
        f"theo nhóm chủ đề. Hãy viết bản tin HTML hoàn chỉnh theo đúng hướng dẫn trong "
        f"system prompt. Tiêu đề bản tin nên là một câu ngắn bắt đúng tin nổi bật nhất "
        f"(giống kiểu 'Vingroup đè chỉ số, thế giới lập kỷ lục mới').\n\n"
        f"=== DỮ LIỆU THÔ ===\n{raw_data}"
    )

    print("Đang gọi Claude API để tổng hợp bản tin...", flush=True)
    html = call_claude(user_content, api_key)
    html = clean_html(html)

    output_dir = "bantin"
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{date_str}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Đã lưu bản tin: {out_path}", flush=True)

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
