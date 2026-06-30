import feedparser
import requests
from bs4 import BeautifulSoup
import re

def clean_html(html_content):
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text(separator=" ")
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def fetch_rss_sources():
    feeds = {
        "ChungKhoanVN": [
            "https://vietstock.vn/rss/thi-truong-chung-khoan.rss",
            "https://vneconomy.vn/chung-khoan.rss"
        ],
        "ChungKhoanTheGioi": [
            "https://vietstock.vn/rss/tai-chinh-quoc-te.rss",
            "https://vneconomy.vn/the-gioi.rss"
        ],
        "VangHangHoa": [
            "https://vneconomy.vn/hang-hoa.rss",
            "https://vietstock.vn/rss/hang-hoa.rss"
        ],
        "Crypto": [
            "https://vnexpress.net/rss/so-hoa.rss"
        ],
        "ViMoThoiSu": [
            "https://vneconomy.vn/thoi-su.rss",
            "https://vietstock.vn/rss/kinh-te-vi-mo.rss"
        ],
        "BatDongSan": [
            "https://vneconomy.vn/bat-dong-san.rss",
            "https://vietstock.vn/rss/bat-dong-san.rss"
        ]
    }
    
    aggregated_data = {}
    
    for category, url_list in feeds.items():
        aggregated_data[category] = []
        for url in url_list:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:6]:
                    title = entry.get("title", "")
                    summary = clean_html(entry.get("summary", ""))
                    link = entry.get("link", "")
                    aggregated_data[category].append({
                        "title": title,
                        "summary": summary,
                        "source_url": link
                    })
            except Exception as e:
                print(f"Lỗi khi lấy dữ liệu từ nguồn {url}: {e}")
                
    return aggregated_data
