"""
fetch_market_data.py
Lấy số liệu giá thị trường (index + cổ phiếu chủ chốt) từ nhiều nguồn,
thử lần lượt cho tới khi được, để bản tin không bị N/A.

Nguồn thử theo thứ tự: VCI -> TCBS (qua vnstock). Chỉ số quốc tế qua MSN (vnstock).
Ghi kết quả ra market_data.txt để generate_newsletter.py đọc kèm.

Chạy: python3 fetch_market_data.py > market_data.txt
"""

import sys
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))

# Chỉ số trong nước cần lấy (mã theo vnstock)
VN_INDICES = ["VNINDEX", "HNXINDEX", "UPCOMINDEX"]
# Cổ phiếu vốn hóa lớn để tham chiếu dòng tiền
KEY_STOCKS = ["VIC", "VHM", "VCB", "FPT", "HPG", "VNM", "TCB", "MWG"]
# Chỉ số quốc tế (qua nguồn MSN của vnstock)
WORLD_SYMBOLS = {
    "SPX": "S&P 500", "DJI": "Dow Jones", "COMP": "Nasdaq",
    "GOLD": "Vàng TG", "BTC": "Bitcoin", "CL": "Dầu WTI",
}


def _get_quote_history(symbol, source):
    """Lấy dữ liệu OHLCV gần nhất của 1 mã qua vnstock, trả về (close, pct) hoặc None."""
    try:
        from vnstock import Quote
        q = Quote(symbol=symbol, source=source)
        end   = datetime.now(VN_TZ).strftime("%Y-%m-%d")
        start = (datetime.now(VN_TZ) - timedelta(days=10)).strftime("%Y-%m-%d")
        df = q.history(start=start, end=end, interval="1D")
        if df is None or len(df) < 1:
            return None
        close = float(df["close"].iloc[-1])
        pct = None
        if len(df) >= 2:
            prev = float(df["close"].iloc[-2])
            if prev:
                pct = (close - prev) / prev * 100
        return (close, pct)
    except Exception as e:
        print(f"  [!] {symbol}@{source}: {e}", file=sys.stderr)
        return None


def get_with_fallback(symbol, sources=("VCI", "TCBS")):
    """Thử lấy giá từ nhiều nguồn cho tới khi được."""
    for src in sources:
        result = _get_quote_history(symbol, src)
        if result is not None:
            return result, src
    return None, None


def fmt_pct(pct):
    if pct is None:
        return "?"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def fmt_num(n):
    """Định dạng số kiểu VN: 1.234,56"""
    s = f"{n:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    now = datetime.now(VN_TZ)
    print(f"=== DỮ LIỆU GIÁ THỊ TRƯỜNG (cập nhật {now.strftime('%d/%m/%Y %H:%M')} giờ VN) ===\n")

    print("## CHỈ SỐ TRONG NƯỚC ##")
    for idx in VN_INDICES:
        (data, src) = get_with_fallback(idx)
        if data:
            close, pct = data
            print(f"- {idx}: {fmt_num(close)} điểm | thay đổi {fmt_pct(pct)} | nguồn {src}")
        else:
            print(f"- {idx}: không lấy được (đã thử VCI, TCBS)")

    print("\n## CỔ PHIẾU VỐN HÓA LỚN ##")
    for sym in KEY_STOCKS:
        (data, src) = get_with_fallback(sym)
        if data:
            close, pct = data
            print(f"- {sym}: {fmt_num(close)} | {fmt_pct(pct)} | nguồn {src}")
        else:
            print(f"- {sym}: N/A")

    print("\n## CHỈ SỐ QUỐC TẾ & HÀNG HÓA ##")
    for sym, name in WORLD_SYMBOLS.items():
        (data, src) = get_with_fallback(sym, sources=("MSN",))
        if data:
            close, pct = data
            print(f"- {name} ({sym}): {fmt_num(close)} | {fmt_pct(pct)} | nguồn {src}")
        else:
            print(f"- {name} ({sym}): N/A")

    print("\n[Ghi chú: dữ liệu trích xuất tự động từ nguồn công khai, có thể trễ hoặc sai lệch, "
          "không dùng cho quyết định giao dịch.]")


if __name__ == "__main__":
    main()
