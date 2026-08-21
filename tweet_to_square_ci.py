#!/usr/bin/env python3
"""
tweet_to_square_ci.py  (DA-NGUON / MULTI-ACCOUNT)
-------------------------------------------------
Chay MOT LAN roi thoat — danh cho GitHub Actions (cron).
Moi lan: doc tweet MOI tu NHIEU tai khoan X (kem anh) -> dang len Binance Square
-> cap nhat state/last_ids.json (moc rieng cho tung account).

LOC ANH: chi giu anh NGANG (chart TradingView, ty le rong>cao). Bo anh DOC
(QR Telegram / the referral Binance) vi loai nay bi Square bop tuong tac.
Tweet co video/GIF se chi dang phan chu.
Neu upload anh loi, tu dong dang lai chi voi chu.

Luong dang anh lay tu ma nguon CHINH THUC cua Binance (binance-skills-hub):
  1) POST /image/presignedUrl  (v2)  -> presignedUrl + fileTicket
  2) PUT anh len presignedUrl (S3)
  3) POST /image/imageStatus   (v2)  -> poll den khi status=1, lay imageUrl
  4) POST /content/add         (v1)  -> dang bai voi imageList

BAO MAT: tat ca key doc tu BIEN MOI TRUONG (GitHub Secrets). KHONG hardcode.
"""
import os
import re
import sys
import json
import time
import struct
import requests
from pathlib import Path
from urllib.parse import urlparse
from requests_oauthlib import OAuth1

# ---------- Cau hinh ----------
# Danh sach username, ngan cach bang dau phay. Vi du: "ero_crypto, kol_khac"
# Van chap nhan TWITTER_USERNAME (so it) de tuong thich nguoc.
_raw_users = os.environ.get("TWITTER_USERNAMES") or os.environ.get("TWITTER_USERNAME", "")
USERNAMES   = [u.strip().lstrip("@") for u in _raw_users.split(",") if u.strip()]
EXCLUDE     = os.environ.get("EXCLUDE", "retweets,replies")
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "10"))
X_API_BASE  = os.environ.get("X_API_BASE", "https://api.twitter.com/2")  # loi thi doi sang https://api.x.com/2
STATE_FILE  = Path(os.environ.get("STATE_FILE", "state/last_ids.json"))
DRY_RUN     = os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes")
# Bat/tat loc anh doc. Mac dinh BAT (giu chart, bo QR/referral).
KEEP_ONLY_LANDSCAPE = os.environ.get("KEEP_ONLY_LANDSCAPE", "1").strip().lower() in ("1", "true", "yes")

# Binance Square endpoints
SQ_V1 = "https://www.binance.com/bapi/composite/v1/public/pgc/openApi"
SQ_V2 = "https://www.binance.com/bapi/composite/v2/public/pgc/openApi"
POLL_INTERVAL = 3
MAX_POLL = 10

CT_MAP = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
          "gif": "image/gif", "webp": "image/webp"}
UA = {"User-Agent": "Mozilla/5.0"}

# Bo cac link t.co dinh o CUOI text (link anh/tweet goc do X tu gan).
TRAILING_TCO_RE = re.compile(r"\s*(?:https?://t\.co/\w+\s*)+$")

SQ_ERR = {
    "220009": "Da vuot gioi han 100 bai/ngay.",
    "220014": "Da vuot gioi han upload anh trong ngay.",
    "20013":  "Noi dung qua dai/khong hop le.",
}


def env(n):
    v = os.environ.get(n)
    if not v:
        sys.exit(f"[LOI] Thieu bien moi truong/secret: {n}")
    return v


if not USERNAMES:
    sys.exit("[LOI] Chua dat TWITTER_USERNAMES (sua trong file workflow sync.yml).")

oauth = OAuth1(env("TWITTER_API_KEY"), env("TWITTER_API_SECRET"),
               env("TWITTER_ACCESS_TOKEN"), env("TWITTER_ACCESS_SECRET"))
SQUARE_KEY = env("BINANCE_SQUARE_OPENAPI_KEY")
SQ_HEADERS = {
    "X-Square-OpenAPI-Key": SQUARE_KEY,
    "Content-Type": "application/json",
    "clienttype": "binanceSkill",
}


# ---------- State (JSON: { "<username>": {"last_id": "..", "user_id": ".."} }) ----------
def read_state():
    try:
        data = json.loads(STATE_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def write_state(state):
    if DRY_RUN:
        return
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


# ---------- Twitter ----------
def get_user_id(u):
    r = requests.get(f"{X_API_BASE}/users/by/username/{u}", auth=oauth, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"khong lay duoc user id ({r.status_code}): {r.text[:200]}")
    return r.json()["data"]["id"]


def get_new_tweets(uid, since):
    params = {
        "max_results": MAX_RESULTS,
        "tweet.fields": "created_at,attachments",
        "expansions": "attachments.media_keys",
        "media.fields": "url,type",
    }
    if EXCLUDE:
        params["exclude"] = EXCLUDE
    if since:
        params["since_id"] = since
    r = requests.get(f"{X_API_BASE}/users/{uid}/tweets", params=params, auth=oauth, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"loi doc tweet ({r.status_code}): {r.text[:200]}")
    j = r.json()
    media_map = {m["media_key"]: m for m in j.get("includes", {}).get("media", [])}
    out = []
    for tw in j.get("data", []):
        keys = (tw.get("attachments") or {}).get("media_keys", [])
        photos, has_other = [], False
        for k in keys:
            m = media_map.get(k, {})
            if m.get("type") == "photo" and m.get("url"):
                photos.append(m["url"])
            elif m.get("type") in ("video", "animated_gif"):
                has_other = True
        tw["_photos"] = photos
        tw["_has_other_media"] = has_other
        out.append(tw)
    return list(reversed(out))  # cu -> moi


def strip_trailing_tco(text):
    return TRAILING_TCO_RE.sub("", text).strip()


# ---------- Loc anh theo ty le (chart ngang giu, QR/ref doc bo) ----------
def image_size(data):
    """Doc (rong, cao) tu bytes anh PNG/JPEG/GIF. None neu khong doc duoc."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    if data[:6] in (b"GIF87a", b"GIF89a"):
        w, h = struct.unpack("<HH", data[6:10])
        return w, h
    if data[:2] == b"\xff\xd8":  # JPEG
        i, n = 2, len(data)
        while i < n - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            m = data[i + 1]
            if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                     0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                i += 2
                continue
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg
    return None


def is_landscape(data):
    """True neu anh ngang (chart). Khong doc duoc kich thuoc -> GIU (True)
    de tranh vo tinh bo mat noi dung that."""
    wh = image_size(data)
    if not wh:
        return True
    return wh[0] > wh[1]


# ---------- Binance Square ----------
def sq_api(base, endpoint, body, timeout=60):
    r = requests.post(f"{base}{endpoint}", headers=SQ_HEADERS, json=body, timeout=timeout)
    if endpoint == "/content/add" and r.status_code == 504:
        return {"id": None, "shareLink": None}  # 504 sau submit = coi nhu da dang
    try:
        j = r.json()
    except ValueError:
        raise RuntimeError(f"Square tra ve non-JSON ({r.status_code})")
    if j.get("code") != "000000":
        code = j.get("code")
        hint = SQ_ERR.get(code, "")
        raise RuntimeError(f"code={code} msg={j.get('message')} {hint}".strip())
    return j.get("data")


def ext_from_url(url):
    p = urlparse(url).path
    ext = p.rsplit(".", 1)[-1].lower() if "." in p else "jpg"
    return ext if ext in CT_MAP else "jpg"


def upload_one_image(img_url, blob):
    ext = ext_from_url(img_url)
    d = sq_api(SQ_V2, "/image/presignedUrl", {"imageName": f"image.{ext}"})
    presigned, ticket = d["presignedUrl"], d["fileTicket"]
    put = requests.put(presigned, headers={"Content-Type": CT_MAP[ext]},
                       data=blob, timeout=120)
    if not put.ok:
        raise RuntimeError(f"Upload S3 that bai: {put.status_code}")
    for _ in range(MAX_POLL):
        s = sq_api(SQ_V2, "/image/imageStatus", {"fileTicket": ticket})
        if s.get("status") == 1:
            return s["imageUrl"]
        if s.get("status") == 2:
            raise RuntimeError(f"Xu ly anh that bai: {s.get('failedReason')}")
        time.sleep(POLL_INTERVAL)
    raise RuntimeError("Cho xu ly anh qua lau (timeout).")


def select_photos(photo_urls):
    """Tai anh, loc bo anh doc (QR/referral), gioi han 4. Tra ve [(url, blob)]."""
    kept = []
    for u in photo_urls:
        if len(kept) >= 4:
            break
        try:
            blob = requests.get(u, headers=UA, timeout=60).content
        except Exception as e:
            print(f"     [!] tai anh loi, bo qua: {e}")
            continue
        if KEEP_ONLY_LANDSCAPE and not is_landscape(blob):
            print("     - bo 1 anh doc (QR/referral)")
            continue
        kept.append((u, blob))
    return kept


def post_to_square(text, photos):
    """photos: list [(url, blob)]."""
    if DRY_RUN:
        print(f"     [DRY_RUN] se dang: {text[:80]!r}  (+{len(photos)} anh)")
        return
    body = {"contentType": 1, "bodyTextOnly": text}
    if photos:
        body["imageList"] = [upload_one_image(u, b) for (u, b) in photos]
    data = sq_api(SQ_V1, "/content/add", body)
    pid = (data or {}).get("id")
    print(f"     [OK] https://www.binance.com/square/post/{pid}" if pid
          else "     [OK] da dang (504 - khong co link tra ve).")


# ---------- Xu ly 1 account ----------
def process_account(username, state):
    print(f"\n=== @{username} ===")
    entry = state.get(username, {})
    uid = entry.get("user_id") or get_user_id(username)
    last = entry.get("last_id")

    # Lan dau voi account nay: dat moc, khong dang.
    if not last:
        base = get_new_tweets(uid, None)
        newest = base[-1]["id"] if base else None
        state[username] = {"user_id": uid, "last_id": newest}
        write_state(state)
        if newest:
            print(f"[i] Lan dau: dat moc tu tweet moi nhat (id={newest}). Tu gio chi dang tweet MOI hon.")
        else:
            print("[i] Lan dau: chua thay tweet nao.")
        return

    tweets = get_new_tweets(uid, last)
    if not tweets:
        print("[i] Khong co tweet moi.")
        state[username] = {"user_id": uid, "last_id": last}  # luu cache user_id
        write_state(state)
        return

    for tw in tweets:
        text = strip_trailing_tco(tw.get("text", ""))
        photo_urls = tw.get("_photos", [])
        photos = select_photos(photo_urls)
        if photos:
            note = f" (+{len(photos)}/{len(photo_urls)} anh)"
        elif tw.get("_has_other_media"):
            note = " (co video/gif -> chi dang chu)"
        else:
            note = ""
        print(f"  -> Tweet moi{note}: {text[:70]}")

        try:
            post_to_square(text, photos)
        except Exception as e:
            print(f"     [!] Loi khi dang kem anh: {e}")
            if photos:
                print("     -> Thu dang lai chi voi chu...")
                try:
                    post_to_square(text, [])
                except Exception as e2:
                    print(f"     [!] Van loi: {e2} -> giu moc, lan sau thu lai.")
                    return  # khong cap nhat state -> lan sau chay lai tweet nay
            else:
                print("     -> Giu moc, lan sau thu lai.")
                return

        state[username] = {"user_id": uid, "last_id": tw["id"]}
        write_state(state)
        time.sleep(1)


# ---------- Main ----------
def main():
    if DRY_RUN:
        print("[i] DRY_RUN: chi in ra, KHONG dang len Square, KHONG cap nhat state.")
    state = read_state()
    for username in USERNAMES:
        try:
            process_account(username, state)
        except Exception as e:
            # Loi 1 account (429, khoa nick, doi ten...) KHONG lam chet cac account con lai.
            print(f"[!] Bo qua @{username} do loi: {e}")
            continue


if __name__ == "__main__":
    main()
