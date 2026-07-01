"""
fetch_market_data.py
Lay so lieu gia thi truong tu NHIEU nguon HTTP cong khai, thu lan luot cho toi
khi lay duoc, de bang chi so khong bi bo trong.

Ly do doi cach lay: tren GitHub Actions (may chu o My), thu vien vnstock hay bi
chan/khong on dinh. Nen o day uu tien cac API HTTP cong khai chay tot tu nuoc ngoai:
  - Quoc te & hang hoa & USD/VND: Yahoo Finance chart API.
  - Chi so & co phieu VN: VNDIRECT dchart -> TCBS -> vnstock (du phong cuoi).

Ghi ket qua ra stdout de workflow noi vao raw_sources.txt.
Chay: python3 fetch_market_data.py >> raw_sources.txt
"""

import sys, json, time
from datetime import datetime, timedelta, timezone

try:
    import requests
except Exception:
    requests = None

VN_TZ = timezone(timedelta(hours=7))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
TIMEOUT = 20

# ---- Danh muc ----
# Quoc te (Yahoo symbol, ten hien thi)
YAHOO = [
    ("^GSPC",  "S&P 500"),
    ("^DJI",   "Dow Jones"),
    ("^IXIC",  "Nasdaq"),
    ("^N225",  "Nikkei 225"),
    ("^HSI",   "Hang Seng"),
    ("GC=F",   "Vang the gioi"),
    ("BZ=F",   "Dau Brent"),
    ("CL=F",   "Dau WTI"),
    ("BTC-USD","Bitcoin"),
    ("ETH-USD","Ethereum"),
    ("VND=X",  "USD/VND"),
]
# Chi so VN (ma, ten)
VN_INDICES = [("VNINDEX","VN-Index"), ("HNXINDEX","HNX-Index"), ("UPCOMINDEX","UPCOM-Index")]
# Co phieu von hoa lon
KEY_STOCKS = ["VIC","VHM","VCB","FPT","HPG","VNM","TCB","MWG"]


def _get(url):
    if requests is None:
        return None
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  [!] loi tai {url[:60]}...: {e}", file=sys.stderr)
        return None


def fmt_num(n):
    try:
        s = f"{float(n):,.2f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(n)


def fmt_pct(p):
    if p is None:
        return "?"
    sign = "+" if p >= 0 else ""
    return f"{sign}{p:.2f}%"


# ---------- Nguon quoc te: Yahoo Finance ----------
def yahoo_quote(symbol):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?interval=1d&range=5d")
    r = _get(url)
    if not r:
        return None
    try:
        res = r.json()["chart"]["result"][0]
        meta = res["meta"]
        price = meta.get("regularMarketPrice")
        prev  = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is None:
            closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
            if closes:
                price = closes[-1]
                prev = closes[-2] if len(closes) >= 2 else prev
        pct = None
        if price is not None and prev:
            pct = (price - prev) / prev * 100
        return (price, pct) if price is not None else None
    except Exception as e:
        print(f"  [!] parse Yahoo {symbol}: {e}", file=sys.stderr)
        return None


# ---------- Nguon VN: VNDIRECT dchart ----------
def vndirect_quote(symbol):
    to_ts = int(time.time())
    from_ts = to_ts - 20 * 24 * 3600
    url = (f"https://dchart-api.vndirect.com.vn/dchart/history"
           f"?resolution=D&symbol={symbol}&from={from_ts}&to={to_ts}")
    r = _get(url)
    if not r:
        return None
    try:
        j = r.json()
        c = j.get("c") or []
        if not c:
            return None
        price = float(c[-1])
        prev = float(c[-2]) if len(c) >= 2 else None
        pct = (price - prev) / prev * 100 if prev else None
        return (price, pct)
    except Exception as e:
        print(f"  [!] parse VNDIRECT {symbol}: {e}", file=sys.stderr)
        return None


# ---------- Nguon VN: TCBS ----------
def tcbs_quote(symbol, is_index=False):
    to_ts = int(time.time())
    from_ts = to_ts - 20 * 24 * 3600
    typ = "index" if is_index else "stock"
    url = (f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/"
           f"bars-long-term?ticker={symbol}&type={typ}&resolution=D"
           f"&from={from_ts}&to={to_ts}")
    r = _get(url)
    if not r:
        return None
    try:
        data = r.json().get("data") or []
        if not data:
            return None
        closes = [float(d["close"]) for d in data if d.get("close") is not None]
        if not closes:
            return None
        price = closes[-1]
        prev = closes[-2] if len(closes) >= 2 else None
        pct = (price - prev) / prev * 100 if prev else None
        return (price, pct)
    except Exception as e:
        print(f"  [!] parse TCBS {symbol}: {e}", file=sys.stderr)
        return None


# ---------- Du phong cuoi: vnstock ----------
def vnstock_quote(symbol):
    try:
        from vnstock import Quote
        for src in ("VCI", "TCBS"):
            try:
                q = Quote(symbol=symbol, source=src)
                end = datetime.now(VN_TZ).strftime("%Y-%m-%d")
                start = (datetime.now(VN_TZ) - timedelta(days=15)).strftime("%Y-%m-%d")
                df = q.history(start=start, end=end, interval="1D")
                if df is not None and len(df) >= 1:
                    price = float(df["close"].iloc[-1])
                    prev = float(df["close"].iloc[-2]) if len(df) >= 2 else None
                    pct = (price - prev) / prev * 100 if prev else None
                    return (price, pct, src)
            except Exception:
                continue
    except Exception:
        pass
    return None


def emit(label, code, price, pct, src):
    if price is None:
        print(f"- {label} ({code}): N/A")
    else:
        print(f"- {label} ({code}): {fmt_num(price)} | thay doi {fmt_pct(pct)} | nguon {src}")


def get_vn(symbol, is_index=False):
    r = vndirect_quote(symbol)
    if r:
        return r[0], r[1], "VNDIRECT"
    r = tcbs_quote(symbol, is_index=is_index)
    if r:
        return r[0], r[1], "TCBS"
    r = vnstock_quote(symbol)
    if r:
        return r[0], r[1], r[2]
    return None, None, None


def main():
    now = datetime.now(VN_TZ)
    print(f"\n=== DU LIEU GIA THI TRUONG (cap nhat {now.strftime('%d/%m/%Y %H:%M')} gio VN) ===")
    print("[Nguon: Yahoo Finance (quoc te/USD-VND), VNDIRECT & TCBS (VN). Tham khao, co the tre.]\n")

    print("## CHI SO TRONG NUOC ##")
    for code, label in VN_INDICES:
        price, pct, src = get_vn(code, is_index=True)
        emit(label, code, price, pct, src)

    print("\n## CO PHIEU VON HOA LON ##")
    for sym in KEY_STOCKS:
        price, pct, src = get_vn(sym, is_index=False)
        emit(sym, sym, price, pct, src)

    print("\n## QUOC TE, HANG HOA & TY GIA ##")
    for sym, label in YAHOO:
        r = yahoo_quote(sym)
        if r:
            emit(label, sym, r[0], r[1], "Yahoo")
        else:
            emit(label, sym, None, None, None)


if __name__ == "__main__":
    main()
