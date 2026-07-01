"""
fetch_market_data.py
Lấy số liệu giá thị trường (chỉ số + cổ phiếu chủ chốt + quốc tế) từ NHIỀU nguồn
qua vnstock, thử lần lượt cho tới khi lấy được, để bản tin không bị bỏ trống thẻ.

Nguyên tắc: mỗi mã đều thử qua nhiều nhà cung cấp (VCI, TCBS, MSN) chứ không phụ
thuộc một nguồn duy nhất. Chỉ số quốc tế và hàng hóa lấy qua MSN.

Ghi kết quả ra market_data.txt để generate_newsletter.py đọc kèm.
Chạy: python3 fetch_market_data.py > market_data.txt
"""

import sys
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))

# Chỉ số trong nước (mã theo vnstock) — thử nhiều nguồn
VN_INDICES = [
    ("VNINDEX",   "VN-Index"),
    ("HNXINDEX",  "HNX-Index"),
    ("UPCOMINDEX", "UPCOM-Index"),
]

# Cổ phiếu vốn hóa lớn để tham chiếu dòng tiền theo trụ
KEY_STOCKS = ["VIC", "VHM", "VCB", "FPT", "HPG", "VNM", "TCB", "MWG"]

# Chỉ số quốc tế & hàng hóa (qua nguồn MSN của vnstock)
WORLD_SYMBOLS = [
    ("SPX",  "S&P 500"),
    ("DJI",  "Dow Jones"),
    ("COMP", "Nasdaq"),
    ("N225", "Nikkei 225"),
    ("HSI",  "Hang Seng"),
    ("GOLD", "Vàng thế giới"),
    ("CL",   "Dầu WTI"),
    ("BTC",  "Bitcoin"),
    ("ETH",  "Ethereum"),
]

# Tỷ giá (thử qua MSN; nếu không có sẽ để RSS bổ sung)
FX_SYMBOLS = [
    ("USDVND", "USD/VND"),
]

# Thứ tự nhà cung cấp thử cho từng nhóm
VN_SOURCES    = ("VCI", "TCBS", "MSN")
WORLD_SOURCES = ("MSN",)
FX_SOURCES    = ("MSN",)


def _get_quote_history(symbol, source):
    """Lấy OHLCV gần nhất của 1 mã qua vnstock, trả về (close, pct) hoặc None."""
    try:
        from vnstock import Quote
        q = Quote(symbol=symbol, source=source)
        end   = datetime.now(VN_TZ).strftime("%Y-%m-%d")
        start = (datetime.now(VN_TZ) - timedelta(days=12)).strftime("%Y-%m-%d")
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


def get_with_fallback(symbol, sources):
    """Thử lấy giá từ nhiều nguồn cho tới khi được. Trả về ((close, pct), src)."""
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


def _emit(label, code, data, src):
    if data:
        close, pct = data
        print(f"- {label} ({code}): {fmt_num(close)} | thay doi {fmt_pct(pct)} | nguon {src}")
    else:
        tried = "" if not src else f" (da thu {src})"
        print(f"- {label} ({code}): N/A{tried}")


def main():
    now = datetime.now(VN_TZ)
    print(f"=== DU LIEU GIA THI TRUONG (cap nhat {now.strftime('%d/%m/%Y %H:%M')} gio VN) ===\n")

    print("## CHI SO TRONG NUOC ##")
    for code, label in VN_INDICES:
        data, src = get_with_fallback(code, VN_SOURCES)
        _emit(label, code, data, src or ", ".join(VN_SOURCES))

    print("\n## CO PHIEU VON HOA LON ##")
    for sym in KEY_STOCKS:
        data, src = get_with_fallback(sym, VN_SOURCES)
        _emit(sym, sym, data, src or ", ".join(VN_SOURCES))

    print("\n## CHI SO QUOC TE & HANG HOA ##")
    for code, label in WORLD_SYMBOLS:
        data, src = get_with_fallback(code, WORLD_SOURCES)
        _emit(label, code, data, src or ", ".join(WORLD_SOURCES))

    print("\n## TY GIA ##")
    for code, label in FX_SYMBOLS:
        data, src = get_with_fallback(code, FX_SOURCES)
        _emit(label, code, data, src or ", ".join(FX_SOURCES))

    print("\n[Ghi chu: du lieu trich xuat tu dong tu nguon cong khai qua vnstock, "
          "co the tre hoac sai lech, khong dung cho quyet dinh giao dich.]")


if __name__ == "__main__":
    main()
