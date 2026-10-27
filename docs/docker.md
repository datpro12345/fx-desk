# Docker — deploy weekly ABCD

Image này chạy đúng pipeline đã test: **A fetch this-week (không WARP)** → **B silver/mart** → **C Fact Pack** → **D outlook + lint**.

Phù hợp **Docker Desktop trên Windows** và **Oracle Cloud Always Free VM**. Không cần Playwright, không cần Cloudflare WARP cho đường weekly.

Lịch sử tháng (HTML Forex Factory) **không** nằm trong lệnh mặc định — IP VN/Oracle thường bị TLS-reset; xem `docs/scrape_strategy.md`.

---

## 1. Điền trước khi chạy (bắt buộc)

Trên máy Windows hoặc VM:

```bash
cp .env.template .env
```

Mở `.env` và điền:

| Biến | Bắt buộc? | Giá trị |
|---|---|---|
| `OPENROUTER_API_KEY` | **Có** (nếu viết báo cáo) | Key tại [openrouter.ai/keys](https://openrouter.ai/keys) |
| `LLM_PROVIDER` | Có | `openrouter` (mặc định) |
| `OPENROUTER_MODEL` | Không | Để trống. Nếu điền, model này được thử sau danh sách dự phòng. Docker dùng danh sách dự phòng trong `scripts/analyst/llm_client.py`, trừ khi `FM_OPENROUTER_TOOLS` trỏ tới bản router đã mount |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Chỉ khi `LLM_PROVIDER=google` | Key tại [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `REPORT_LANG` | Không | `en` (mặc định trên Docker) hoặc `vi`. CLI: `--lang en` |
| `TZ` | Không | `Asia/Ho_Chi_Minh` (compose đã set) |
| `FF_HTTP_PROXY` | Không | Chỉ khi cần proxy residential. Weekly export **không** cần |

Không commit file `.env`. Không dán key vào image.

Kiểm tra nhanh (chưa gọi LLM):

```bash
docker compose run --rm -e REPORT_LANG=en weekly python scripts/run_weekly_abcd.py --fmt csv --skip-report
```

---

## 2. Windows — Docker Desktop

1. Cài [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/). Bật **Linux containers**.
2. Clone repo (Git Bash, PowerShell, hoặc Windows Terminal):

   ```powershell
   git clone <url-repo> ff-transform-data
   cd ff-transform-data
   copy .env.template .env
   notepad .env
   ```

3. Build một lần:

   ```powershell
   docker compose build
   ```

4. Chạy tuần này (fetch + báo cáo):

   ```powershell
   docker compose run --rm -e REPORT_LANG=en weekly
   ```

5. Kết quả trên máy host:

   - `data/bronze/weekly/thisweek.csv` — raw tuần
   - `data/silver/calendar_events/YYYY_Www.csv`
   - `data/gold/mart/` — Kimball
   - `reports/weekly/YYYY-Www-macro-outlook.md`
   - `reports/weekly/YYYY-Www-macro-outlook.lint.txt` — phải `PASS`

PowerShell cũng dùng `docker compose` (có dấu cách), không phải `docker-compose`.

Nếu volume báo permission denied: Docker Desktop → Settings → Resources → File Sharing, cho phép thư mục repo.

---

## 3. Oracle Cloud Always Free VM

Chọn shape:

| Shape | Architecture | Compose |
|---|---|---|
| `VM.Standard.A1.Flex` (Ampere) | **arm64** | Build native, không cần `--platform` |
| `VM.Standard.E2.1.Micro` | **amd64** | Build native |

Mở **egress HTTPS 443** (Security List / NSG). Không cần inbound trừ khi bạn SSH (22).

### Cài Docker (Ubuntu 22.04/24.04)

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
# đăng nhập lại SSH cho group docker có hiệu lực
```

### Đưa code lên VM

**Cách A — git clone** (repo đã có `data/` silver/gold YTD):

```bash
git clone <url-repo> ~/ff-transform-data
cd ~/ff-transform-data
cp .env.template .env
nano .env   # dán OPENROUTER_API_KEY
```

**Cách B — copy từ máy local** (nếu repo private):

```bash
# trên máy bạn
rsync -av --exclude .venv --exclude .git ./ ubuntu@<vm-ip>:~/ff-transform-data/
```

### Build và chạy

```bash
cd ~/ff-transform-data
docker compose build
docker compose run --rm -e REPORT_LANG=en weekly
```

1 GB RAM Always Free đủ cho weekly (mart ~3k rows). Nếu `pip`/`compose build` bị OOM trên Micro: thêm swap 2G rồi build lại.

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### Cron — chạy mỗi Chủ nhật 07:00 giờ VN (00:00 UTC)

```bash
crontab -e
```

```cron
0 0 * * 0 cd /home/ubuntu/ff-transform-data && docker compose run --rm -e REPORT_LANG=en weekly >> /home/ubuntu/ff-transform-data/logs/abcd.log 2>&1
```

Tạo thư mục log một lần: `mkdir -p ~/ff-transform-data/logs`.

---

## 4. Lệnh thường dùng

```bash
# Full ABCD (A fetch → D outlook). Feed ~2 request / 5 phút — chỉ CSV một lần.
docker compose run --rm -e REPORT_LANG=en weekly

# Chỉ ingest lại bronze đã có, không đụng mạng FF
docker compose run --rm -e REPORT_LANG=en weekly python scripts/run_weekly_abcd.py --skip-fetch

# Fact Pack + prompt, không gọi LLM
docker compose run --rm -e REPORT_LANG=en weekly python scripts/run_weekly_abcd.py --skip-fetch --dry-run

# Đổi model / ngôn ngữ (không sửa .env)
docker compose run --rm weekly python scripts/run_weekly_abcd.py --lang vi --model 'google/gemma-4-31b-it:free'

# Shell trong container
docker compose run --rm --entrypoint bash weekly
```

Volume `./data` và `./reports` ghi thẳng ra host — xóa container không mất file.

---

## 5. Việc image làm / không làm

**Làm:** fetch `nfs.faireconomy.media` (`curl_cffi` + firefox135), timezone `Asia/Ho_Chi_Minh`, Control Lane + prompt trong `docs/analyst/`.

**Không làm:** cài WARP trong container; scrape HTML `www.forexfactory.com` (tháng lịch sử). Muốn YTD mới: bật WARP trên máy có IP sạch, chạy `scripts/extract/fetch_bronze_months.py` ngoài Docker (hoặc trên host), rồi copy `data/` vào VM.

---

## 6. Sự cố thường gặp

| Hiện tượng | Cách xử |
|---|---|
| `OPENROUTER_API_KEY is missing` | `.env` chưa có, hoặc compose không thấy file (chạy đúng thư mục repo) |
| OpenRouter HTTP 404 model | Slug `:free` chết. Xoá `OPENROUTER_MODEL` trong `.env`, hoặc sửa `PREFERRED_OPENROUTER_MODELS` trong `scripts/analyst/llm_client.py` |
| Fetch weekly 429 | Đợi 5 phút. Đừng thêm `--fallback-formats` |
| Fetch weekly TLS / timeout | Oracle egress OK thì thử lại; không bật WARP cho đường này |
| `no such file .env` | `cp .env.template .env` trước `compose run` |
| Windows CRLF làm `entrypoint` lỗi | Repo nên giữ LF. `git config core.autocrlf input` |
| Image build chậm trên ARM | Bình thường lần đầu; lần sau dùng cache |

---

## 7. File liên quan

- `Dockerfile` — Python 3.12 slim, user `app`
- `docker-compose.yml` — service `weekly`
- `requirements.txt` — runtime + pytest (không Playwright)
- `.env.template` — copy thành `.env`
- `scripts/run_weekly_abcd.py` — entry mặc định
