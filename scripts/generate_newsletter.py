import os
import sys
from datetime import datetime
from anthropic import Anthropic
from fetch_sources import fetch_rss_sources

def build_prompt(data):
    prompt = "Bạn là một chuyên gia phân tích tài chính và là một AI Data Journalist chuyên nghiệp.\n"
    prompt += "Nhiệm vụ của bạn là tổng hợp dữ liệu tin tức thô dưới đây thành một bản tin HTML hoàn chỉnh, chuyên nghiệp, sắc sảo giống văn phong tòa soạn lớn.\n\n"
    prompt += "DỮ LIỆU TIN TỨC THÔ TRONG NGÀY:\n"
    
    for category, articles in data.items():
        prompt += f"\n--- CHỦ ĐỀ: {category} ---\n"
        for idx, art in enumerate(articles):
            prompt += f"{idx+1}. Tiêu đề: {art['title']}\n"
            prompt += f"   Tóm tắt: {art['summary']}\n"
            prompt += f"   Nguồn link: {art['source_url']}\n"
            
    prompt += "\nCÁC YÊU CẦU BẮT BUỘC VỀ ĐỊNH DẠNG VÀ CẤU TRÚC HTML:\n"
    prompt += "1. Bản tin PHẢI viết bằng tiếng Việt, ngôn từ súc tích, phân tích sâu.\n"
    prompt += "2. Chỉ trả về mã HTML nằm trong thẻ `<div>...</div>` bao bọc toàn bộ bản tin. TUYỆT ĐỐI không bao gồm các ký tự đánh dấu mã nguồn như ```html.\n"
    prompt += "3. Cấu trúc bản tin phải bao gồm:\n"
    prompt += "   - Tiêu đề chính ấn tượng dạng h1.\n"
    prompt += "   - Khung Thẻ Chỉ Số nhanh (VN-Index, S&P 500, Giá Vàng, Bitcoin, tỷ giá USD/VND... thiết kế hộp CSS bo góc gọn gàng).\n"
    prompt += "   - Các mục nội dung phân tách rõ ràng sử dụng ký hiệu §01, §02... tương ứng với các chủ đề: Chứng khoán Việt Nam, Toàn cầu, Vàng & Hàng hóa, Tiền điện tử (Crypto), Kinh tế vĩ mô & Thời sự, và Bất động sản.\n"
    prompt += "   - Cuối bài phải có mục 'Nguồn trích dẫn chính trong ngày' liệt kê danh sách các link nguồn.\n"
    prompt += "4. Định dạng CSS inline sạch đẹp, font chữ hiện đại (Arial/Helvetica).\n"
    return prompt

def update_index(new_date):
    index_path = "bantin/index.html"
    dates = set()
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
            found_dates = [m.split(".html")[0] for m in content.split('href="') if ".html" in m and "index.html" not in m]
            for d in found_dates:
                clean_d = d.split("/")[-1].strip()
                if len(clean_d) == 10:
                    dates.add(clean_d)
                    
    dates.add(new_date)
    sorted_dates = sorted(list(dates), reverse=True)
    
    html = "<!DOCTYPE html>\n<html>\n<head>\n<meta charset='utf-8'>\n<title>Trang tổng hợp Bản tin Tự động</title>\n"
    html += "<style>body{font-family:Arial,sans-serif;max-width:600px;margin:40px auto;padding:0 20px;line-height:1.6;} h1{color:#333;border-bottom:2px solid #eee;padding-bottom:10px;} ul{list-style-type:none;padding:0;} li{margin:15px 0;padding:10px;background:#f9f9f9;border-left:4px solid #0066cc;border-radius:0 4px 4px 0;} a{text-decoration:none;color:#0066cc;font-weight:bold;}</style>\n"
    html += "</head>\n<body>\n<h1>📰 Danh sách Bản tin Đã phát hành</h1>\n<ul>\n"
    for d in sorted_dates:
        html += f"  <li>Bản tin ngày: <a href='{d}.html'>{d}</a></li>\n"
    html += "</ul>\n</body>\n</html>"
    
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Lỗi: Không tìm thấy ANTHROPIC_API_KEY trong cấu hình Secret!")
        sys.exit(1)
        
    print("Bước 1: Đang thu thập dữ liệu từ các nguồn RSS...")
    raw_data = fetch_rss_sources()
    
    # Kiểm tra xem có dữ liệu không, tránh lỗi rỗng
    has_data = any(len(articles) > 0 for articles in raw_data.values())
    if not has_data:
        print("Cảnh báo: Không lấy được dữ liệu từ bất kỳ nguồn RSS nào. Sử dụng dữ liệu trống để tránh lỗi sập hệ thống.")
    
    print("Bước 2: Đang chuẩn bị cấu trúc prompt cho Claude...")
    prompt = build_prompt(raw_data)
    
    print("Bước 3: Đang gửi yêu cầu tới Claude API...")
    try:
        client = Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            temperature=0.3,
            system="You are an expert AI data journalist. Output raw HTML format inside a single <div> wrapper only.",
            messages=[{"role": "user", "content": prompt}]
        )
        
        newsletter_html = message.content[0].text.strip()
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # ĐẢM BẢO TẠO THƯ MỤC TRƯỚC KHI GHI FILE
        os.makedirs("bantin", exist_ok=True)
        file_path = f"bantin/{today_str}.html"
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html>\n<html>\n<head>\n<meta charset='utf-8'>\n<title>Bản tin " + today_str + "</title>\n")
            f.write("<style>body{font-family:Arial,sans-serif;background-color:#f4f6f9;padding:20px;} .container{max-width:700px;margin:0 auto;background:#fff;padding:30px;border-radius:8px;box-shadow:0 4px 6px rgba(0,0,0,0.05);}</style>\n")
            f.write("</head>\n<body>\n<div class='container'>\n")
            f.write(newsletter_html)
            f.write("\n</div>\n</body>\n</html>")
            
        print(f"Thành công: Đã tạo xong bản tin lưu tại {file_path}")
        update_index(today_str)
        print("Thành công: Đã cập nhật lại trang mục lục index.html")
        
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tương tác với API hoặc ghi file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
