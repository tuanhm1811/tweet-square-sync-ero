# Tweet → Binance Square Sync (đa nguồn)

Tự động lấy **tweet mới** từ **một hoặc nhiều** tài khoản X (Twitter) — kèm ảnh — và **đăng lại lên Binance Square**.
Chạy miễn phí trên **GitHub Actions** (cron), không cần server riêng.

Khác với bản gốc:
- **Nhiều nguồn cùng lúc** — khai báo danh sách username, mỗi account có mốc riêng.
- **Lọc ảnh thông minh** — chỉ giữ ảnh **ngang** (biểu đồ TradingView). Tự **bỏ ảnh dọc**
  (QR Telegram / thẻ referral Binance) vì loại này bị Square bóp tương tác.
- **Cách ly lỗi** — một account lỗi (429, khoá nick…) không làm chết các account khác.
- **DRY_RUN** — chạy thử, in ra bài sẽ đăng mà không đăng thật.
- Cashtag/topic tác giả tự viết (`$BTC`, `#Bitcoin`) được **giữ nguyên** → Square tự render thành widget token/topic.

> **Bảo mật:** Toàn bộ key đọc từ **GitHub Secrets** (không nằm trong code).

---

## 0. Repo này KHÔNG ảnh hưởng repo cũ

Đây là repo **riêng biệt**. Nó dùng:
- **Secret riêng** của repo này (không dùng chung với repo cũ).
- **File state riêng** (`state/last_ids.json`) commit vào chính repo này.
- **Cron lệch phút** (`12,42`) so với repo cũ (`5,20,35,50`).

Miễn là bạn **nạp `BINANCE_SQUARE_OPENAPI_KEY` của nick Square MỚI** vào repo này (không phải key nick cũ),
hai flow chạy hoàn toàn độc lập.

---

## 1. Cần chuẩn bị: 5 secret

| Tên secret | Lấy ở đâu | Mô tả |
|---|---|---|
| `TWITTER_API_KEY` | X Developer Portal | API Key (Consumer Key) |
| `TWITTER_API_SECRET` | X Developer Portal | API Key Secret |
| `TWITTER_ACCESS_TOKEN` | X Developer Portal | Access Token |
| `TWITTER_ACCESS_SECRET` | X Developer Portal | Access Token Secret |
| `BINANCE_SQUARE_OPENAPI_KEY` | Binance Square (nick MỚI) | Key OpenAPI của **nick Square bạn muốn đăng lên** |

> **4 key X** có thể **dùng lại y hệt** repo cũ (chỉ đọc tweet). Nhưng quota tính theo **app X**,
> nên hai repo sẽ **ăn chung hạn mức** → dễ dính `429` hơn. Nếu gặp, tạo **app X riêng** cho repo này.
>
> **`BINANCE_SQUARE_OPENAPI_KEY` PHẢI là key của nick Square mới.** Dùng nhầm key cũ thì bài sẽ lên nick cũ.

---

## 2. Tạo repo mới trên GitHub và đẩy code lên

Trong thư mục này (đã `git init` sẵn), tạo repo rỗng trên GitHub rồi:

```bash
git remote add origin https://github.com/<tai-khoan-cua-ban>/tweet-square-sync-ero.git
git branch -M main
git push -u origin main
```

> Đừng fork/clone repo cũ. Đây là repo mới, độc lập.

---

## 3. Nạp 5 secret vào repo mới

Repo trên GitHub → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
Thêm lần lượt **5 secret** ở mục 1 (tên phải khớp chính xác).

---

## 4. Bật và chạy

1. Tab **Actions** → **I understand my workflows, enable them**.
2. Chọn workflow **“Tweet to Binance Square (ero)”** → **Run workflow** để chạy thử tay.

**Lần chạy đầu tiên** của mỗi account chỉ *đặt mốc* ở tweet mới nhất và **không đăng gì** (tránh spam lại tweet cũ).
Từ lần sau, chỉ tweet **mới hơn** thời điểm đó mới được đăng.

---

## 5. ➕ Thêm nguồn X mới (điều bạn hỏi)

Chỉ cần sửa **một dòng** trong [`.github/workflows/sync.yml`](.github/workflows/sync.yml):

```yaml
    env:
      TWITTER_USERNAMES: "ero_crypto, kol_thu_hai, kol_thu_ba"
```

- Ngăn cách bằng **dấu phẩy**, bỏ dấu `@`.
- Commit + push. Lần chạy kế tiếp: account mới sẽ **tự đặt mốc** (không đăng bài cũ), từ đó mới đăng tweet mới.
- **Không cần sửa code, không cần đụng secret.** Tất cả nguồn dùng chung 4 key X và cùng đăng lên 1 nick Square (theo `BINANCE_SQUARE_OPENAPI_KEY` của repo này).

> Bài của tất cả nguồn sẽ **gộp chung** về nick Square này. Muốn tách nguồn sang **nick Square khác** →
> tạo thêm một repo nữa như repo này với `BINANCE_SQUARE_OPENAPI_KEY` của nick đó.

> **Lưu ý quota:** mỗi nguồn tốn thêm ~2 lần gọi X API mỗi lần chạy. Nhiều nguồn + gói Free rất dễ `429`.
> Nếu gặp, **giãn cron** (mục 7) hoặc nâng gói X lên Basic.

---

## 6. (Tùy chọn) Chạy thử trên máy — DRY_RUN

```bash
pip install requests requests-oauthlib

export TWITTER_USERNAMES="ero_crypto"
export TWITTER_API_KEY="..."
export TWITTER_API_SECRET="..."
export TWITTER_ACCESS_TOKEN="..."
export TWITTER_ACCESS_SECRET="..."
export BINANCE_SQUARE_OPENAPI_KEY="..."   # dry-run khong dung den, dat gia tri bat ky
export DRY_RUN=1

python tweet_to_square_ci.py     # in ra bai SE dang, khong dang that, khong doi state
```

Chạy test logic (không cần key): `python3 test_logic.py`

---

## 7. Đổi lịch / tinh chỉnh

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| cron | `12,42 * * * *` | ~30 phút/lần. Muốn mỗi giờ: `13 * * * *` |
| `TWITTER_USERNAMES` | `ero_crypto` | Danh sách nguồn, ngăn cách bằng phẩy |
| `DRY_RUN` | `0` | `1` = chỉ in, không đăng |
| `KEEP_ONLY_LANDSCAPE` | `1` | `1` = bỏ ảnh dọc (QR/ref), giữ chart ngang. `0` = giữ tất cả (≤4) |
| `MAX_RESULTS` | `10` | Số tweet đọc mỗi account/lần |
| `EXCLUDE` | `retweets,replies` | Loại bỏ retweet/reply |

---

## 8. Lỗi thường gặp

| Thông báo | Cách xử lý |
|---|---|
| `Thieu bien moi truong/secret: X` | Chưa thêm secret đó, hoặc gõ sai tên. |
| `khong lay duoc user id (401/403)` | Sai key X, hoặc app chưa cấp quyền Read. |
| `loi doc tweet (429)` | Hết quota X API → giãn cron hoặc nâng gói Basic. Chỉ account đó bị bỏ qua, account khác vẫn chạy. |
| `code=220009` | Vượt giới hạn 100 bài/ngày của Square. |
| `code=220014` | Vượt giới hạn upload ảnh trong ngày của Square. |
| Đăng ảnh lỗi | Script tự đăng lại **chỉ với chữ** — không mất bài. |

> Xem log: tab **Actions** → chọn lần chạy → mở step **“Dong bo tweet → Binance Square”**.

> **Không xoá bài qua API được** — Square OpenAPI chỉ cho **đăng**, không có endpoint xoá/sửa.
> Muốn xoá bài phải làm tay trong app Binance.
