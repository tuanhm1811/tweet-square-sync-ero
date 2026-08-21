#!/usr/bin/env python3
"""Test phan logic thuan (khong can API key). Chay: python3 test_logic.py"""
import os
import struct
import zlib

# Dat env gia de import module khong bi sys.exit
os.environ.setdefault("TWITTER_USERNAMES", "test_user")
os.environ.setdefault("TWITTER_API_KEY", "x")
os.environ.setdefault("TWITTER_API_SECRET", "x")
os.environ.setdefault("TWITTER_ACCESS_TOKEN", "x")
os.environ.setdefault("TWITTER_ACCESS_SECRET", "x")
os.environ.setdefault("BINANCE_SQUARE_OPENAPI_KEY", "x")

import tweet_to_square_ci as m

ok = 0
fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail += 1
        print(f"  FAIL  {name}")


# --- strip_trailing_tco ---
check("bo 1 link t.co cuoi",
      m.strip_trailing_tco("hello https://t.co/abc123") == "hello")
check("bo nhieu link t.co cuoi",
      m.strip_trailing_tco("hi https://t.co/aa https://t.co/bb") == "hi")
check("giu link t.co giua cau",
      m.strip_trailing_tco("xem https://t.co/mid roi tiep") == "xem https://t.co/mid roi tiep")
check("khong co link thi giu nguyen",
      m.strip_trailing_tco("$DASH long") == "$DASH long")
check("giu cashtag/topic",
      m.strip_trailing_tco("#USDTD bearish https://t.co/z") == "#USDTD bearish")


# --- username parsing ---
check("tach nhieu username, bo @ va khoang trang",
      [u.strip().lstrip("@") for u in "ero_crypto, @kol2 ,kol3".split(",") if u.strip()]
      == ["ero_crypto", "kol2", "kol3"])


# --- image_size / is_landscape ---
def make_png(w, h):
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00"
    chunk = b"IHDR" + ihdr
    return sig + struct.pack(">I", len(ihdr)) + chunk + struct.pack(">I", zlib.crc32(chunk))


def make_gif(w, h):
    return b"GIF89a" + struct.pack("<HH", w, h) + b"\x00" * 4


def make_jpeg(w, h):
    # SOI + APP0(JFIF) + SOF0 voi w,h + EOI
    soi = b"\xff\xd8"
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", h, w) + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    return soi + app0 + sof0 + b"\xff\xd9"


check("png size doc dung", m.image_size(make_png(1200, 675)) == (1200, 675))
check("gif size doc dung", m.image_size(make_gif(800, 600)) == (800, 600))
check("jpeg size doc dung", m.image_size(make_jpeg(1200, 675)) == (1200, 675))

check("chart NGANG (1200x675) -> landscape", m.is_landscape(make_png(1200, 675)) is True)
check("QR DOC (625x1199) -> not landscape", m.is_landscape(make_png(625, 1199)) is False)
check("ref card DOC (876x1200) -> not landscape", m.is_landscape(make_png(876, 1200)) is False)
check("jpeg chart NGANG -> landscape", m.is_landscape(make_jpeg(1200, 675)) is True)
check("khong doc duoc kich thuoc -> GIU (landscape=True)", m.is_landscape(b"not-an-image") is True)


print(f"\n{ok} pass, {fail} fail")
raise SystemExit(1 if fail else 0)
