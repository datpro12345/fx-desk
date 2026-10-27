# Roadmap: Soros-Style Macro BI Analyst Layer

Tài liệu này định hình lộ trình phát triển **Lớp Phân Tích (BI Analyst Layer)** dựa trên output của tầng dữ liệu `gold/mart`, kết hợp **Tư duy phản xạ (Reflexivity) của George Soros** và kế thừa có chọn lọc từ **LLM Analyst Playbook** (`docs/llm-analyst-playbook.md`).

---

## 1. Đánh giá Model từ Playbook: Lấy gì, Bỏ gì và Tại sao?

Trong mục 16 của Playbook, quy trình tổng thể được mô hình hóa như sau:

```text
BUSINESS CONTEXT + SEMANTIC CONTRACT + DATA/METADATA
       │
       ▼
   UNDERSTAND
       │
       ├─────────────────────┐
       │                     │
       ▼                     ▼
CONTROL LANE            DISCOVERY LANE
Rubric                   Open exploration
Known KPIs               Generate questions
Known risks              Hypotheses
Expected checks          Segmentation
       │                     │
       └──────────┬──────────┘
                  ▼
             VERIFY (SQL / Python / tools)
                  │
                  ▼
         EVIDENCE CLASSIFY (Observation / Pattern / Hypothesis / Verified)
                  │
                  ▼
             CHALLENGE (Independent reviewer)
                  │
        ┌─────────┴─────────┐
        │                   │
        ▼                   ▼
 normal finding       high stakes / major uncertainty
                            │
                            ▼
                       LLM COUNCIL
                            │
                            ▼
                    MATERIALITY GATE
                            │
                            ▼
                      SYNTHESIS
                            │
                            ▼
                    WEEKLY REPORT
```

### 1.1. Tỷ lệ tiếp thu: Lấy khoảng 65% – 70%, Lược bỏ 30% – 35%

Chúng ta **không copy nguyên xi 100%** mô hình của Playbook vào repo này. Dưới đây là bảng bóc tách chi tiết:

| Khối trong Playbook | Quyết định | % Lấy | Cách chuyển hóa vào Repo này | Lý do không lấy nguyên xi |
|---|:---:|:---:|---|---|
| **Context + Semantic Contract** | **LẤY** | 100% | Định nghĩa từ điển vĩ mô: 8 đồng tiền lớn, ý nghĩa tin Red/Orange, múi giờ VN (`Asia/Ho_Chi_Minh`), 4 nhóm tin "Big 4" (Lãi suất, Lạm phát, Việc làm, Tăng trưởng). | Bắt buộc phải có để model không hiểu sai bản chất dữ liệu. |
| **Control Lane** | **LẤY** | 100% | Khung kiểm tra bắt buộc: Toàn bộ tin Red trong tuần, phân bổ theo đồng tiền, các mốc giờ ra tin phiên Á / Âu / Mỹ. | Đảm bảo không bao giờ bỏ sót rủi ro lớn của tuần. |
| **Discovery Lane** | **LẤY (Tinh chỉnh)** | 70% | Tìm kiếm các điểm dị biệt: Cụm tin va chạm cùng giờ (Clashes), vùng trũng thanh khoản (Liquidity Voids), độ lệch kỳ vọng bất thường. | Không dùng agent chạy loop vô tận; gom thành các thuật toán lọc dữ liệu trước. |
| **Verify (Deterministic)** | **LẤY (Đảo vị trí)** | 100% | **Đẩy lên trước (Upstream Verification):** Python tính toán toàn bộ số lượng, tỷ trọng, lọc cụm từ `gold/mart` tạo thành `Fact Pack` trước khi đưa cho LLM. | Playbook gốc để LLM tạo giả thuyết rồi mới gọi tool verify. Với dữ liệu lịch cố định, tính toán trước bằng code giúp tiết kiệm token, nhanh hơn và triệt tiêu 100% ảo giác số học. |
| **Evidence Hierarchy** | **LẤY** | 100% | Phân định 4 tầng chuẩn mực: **Observation** (dữ liệu lịch) $\to$ **Pattern** (cụm rủi ro) $\to$ **Hypothesis** (kỳ vọng thị trường) $\to$ **Action Rule** (quản trị lệnh swing). | Tránh việc LLM kết luận vội vã hoặc đoán mò giá tăng/giảm. |
| **Challenge Pass** | **LẤY (Tích hợp)** | 50% | Tích hợp trực tiếp vào Prompt thành mục **"Soros Falsification Check"** (Tự phản biện: Điều kiện nào sẽ chứng minh nhận định này là sai?). | Không cần dựng thêm 1 con bot reviewer riêng biệt gây tốn chi phí và chậm thời gian. |
| **LLM Council** | **BỎ** | **0%** | **Lược bỏ hoàn toàn trong giai đoạn này.** | **Quá cồng kềnh (Over-engineering):** Council đòi hỏi 3-5 model chạy song song + bầu chọn ẩn danh + model Chairman tổng hợp. Với bài toán đọc lịch Forex hàng tuần, Council gây nghẽn tốc độ, tốn chi phí / vượt rate-limit API miễn phí, không tạo thêm nhiều giá trị thực chiến. |
| **Materiality Gate** | **LẤY** | 100% | Chỉ đưa vào phân tích các sự kiện `impact = 'red'` (và một số `orange` trọng yếu). Lọc bỏ toàn bộ tin `yellow` rác. | Giúp báo cáo tập trung, trader không bị ngợp thông tin (anti-information overload). |
| **Synthesis $\to$ Report** | **LẤY** | 100% | Định dạng Markdown chuẩn, ngắn gọn, có trích dẫn mã sự kiện/thời gian cụ thể. | Dễ đọc, dễ lưu trữ trên Git, phục vụ thẳng cho việc trade. |

---

## 2. Mental Model & Năng Lực Của Analyst (Tư Duy George Soros)

Lớp Analyst không vận hành như một "cỗ máy điểm tin tức", mà tư duy theo **4 nguyên lý phản xạ của George Soros**:

```text
               +-------------------------------------------------+
               | 1. THE REFLEXIVE GAP (Kỳ vọng vs Thực tế)       |
               |    Forecast_txt vs Previous_txt vs Actual_txt   |
               +------------------------+------------------------+
                                        |
                                        v
               +-------------------------------------------------+
               | 2. FALSIFICATION FIRST (Tìm điều kiện SAI)      |
               |    Xác định mốc dữ liệu sẽ bẻ gãy xu hướng      |
               +------------------------+------------------------+
                                        |
                                        v
               +-------------------------------------------------+
               | 3. RELATIVE DIVERGENCE (Phân kỳ tương đối)      |
               |    Ghép cặp: Đồng tiền mạnh nhất vs Yếu nhất    |
               +------------------------+------------------------+
                                        |
                                        v
               +-------------------------------------------------+
               | 4. TIME & LIQUIDITY WINDOWS (Nhịp sinh học giờ) |
               |    Phiên Á - Âu - Mỹ theo múi giờ Việt Nam      |
               +-------------------------------------------------+
```

### 2.1. Bốn năng lực cốt lõi

1. **Năng lực bóc tách khoảng cách phản xạ (The Reflexive Gap):**
   * Thị trường tài chính không di chuyển theo số liệu thuần túy, mà di chuyển theo **sự chênh lệch giữa Kỳ vọng của đám đông và Thực tế**.
   * Analyst luôn đối chiếu `forecast_txt` (kỳ vọng thị trường đã phản ánh vào giá) với `previous_txt` để xem thị trường đang quá lạc quan hay bi quan ở đâu.
2. **Năng lực phản nghiệm (Falsification First - Tinh thần Karl Popper):**
   * Người bình thường tìm bằng chứng để chứng minh nhận định của mình đúng.
   * **Sorosian Analyst luôn tìm điều kiện chứng minh mình SAI**: *"Luận điểm đồng USD tăng tuần này sẽ chính thức sụp đổ nếu số liệu CPI tối thứ Năm ra thấp hơn X"*.
3. **Năng lực phân kỳ tiền tệ tương đối (Relative Currency Divergence):**
   * Không có đồng tiền nào "tăng giá trong chân không". Forex là tỷ giá chéo.
   * Analyst rà soát lịch tuần để tìm **sự lệch pha**: Khối kinh tế nào đang dồn dập xúc tác tăng trưởng vs Khối nào đang im ắng hoặc đối mặt tin xấu $\to$ Tìm ra cặp tiền swing tối ưu (VD: `GBP/JPY`, `EUR/USD`).
4. **Năng lực nhận diện cửa sổ thanh khoản (Session & Liquidity Windows):**
   * Nhìn lịch kinh tế dưới góc nhìn của một người điều khiển dòng vốn tại múi giờ Việt Nam:
     * **Phiên Á (06:00 - 12:00 HCM):** Thanh khoản thấp, tin AUD/NZD/JPY dễ giật râu.
     * **Phiên Âu (14:00 - 18:00 HCM):** Bắt đầu có thanh khoản lớn cho EUR/GBP.
     * **Phiên Mỹ (19:30 - 23:00 HCM):** Vùng bão tố lớn nhất với tin USD/CAD.

---

## 3. Roadmap Triển Khai: Đánh Giá & Phân Kỳ 4 Loại Output

Dựa trên dữ liệu thực tế đang có trong `data/gold/mart/` (`fact_calendar_release`, `dim_date`, `dim_currency`, `dim_impact`, `dim_event`), lộ trình được chia làm 3 giai đoạn:

```text
[DỮ LIỆU HIỆN CÓ TRONG GOLD/MART]
├── Lịch sự kiện, ngày giờ chuẩn HCM
├── Phân loại: Currency, Impact (Red/Orange/Yellow)
└── Text thô: Forecast, Previous, Actual
        │
        ├───► [PHASE 1: TRIỂN KHAI NGAY - 100% ĐỦ DỮ LIỆU]
        │     ├── Output 1: Weekly Macro & Reflexivity Outlook (Xương sống)
        │     └── Output 3: Daily Risk Flash & Action Checklist (Tác chiến)
        │
        ├───► [PHASE 2: TRUNG HẠN - CẦN BỔ SUNG METADATA]
        │     └── Output 2: Monthly Regional Macro Scorecard (La bàn vĩ mô)
        │           (Cần: Numeric Parser + Central Bank Baseline)
        │
        └───► [PHASE 3: DÀI HẠN - CẦN CƠ CHẾ FETCH REAL-TIME]
              └── Output 4: Event Deconstruct Flash (Bóc tách độ lệch tức thì)
                    (Cần: Event-driven Scrape 5 phút sau Big 4)
```

---

### Phase 1: Triển khai ngay (Ready Now - Đủ 100% dữ liệu)

Phase 1 **chỉ ship Weekly Outlook**. Daily Risk Flash **không làm**: Google Calendar gold export (`data/gold/google_calendar/`) đã cảnh báo red USD/GBP/EUR theo giờ HCM. Daily AI report trùng chức năng và nhiễu swing trader.

#### 1. Output 1: `Weekly Macro & Reflexivity Outlook` (Báo cáo tuần - Giá trị cốt lõi)
* **Tần suất:** 1 lần / tuần (Chủ Nhật hoặc sáng Thứ Hai).
* **Trạng thái dữ liệu:** **Đủ 100%**. Lịch tuần tới, mốc giờ, currency, impact, forecast và previous đều đã có sẵn.
* **Cấu trúc nội dung:**
  1. *Weekly Exposure Matrix:* Tách **Chính (USD/EUR/GBP/JPY)** và **Phụ (AUD/NZD/CAD/CHF/CNY)**.
  2. *Tier-1 Catalyst Schedule (HCM Time):* Lịch các mốc giờ Big 4 trong 3 phiên Á - Âu - Mỹ.
  3. *Clash & Volatility Alerts:* Cảnh báo các mốc giờ trùng tin (VD: NFP Mỹ trùng giờ thất nghiệp Canada $\to$ bão quét 2 đầu `USD/CAD`).
  4. *Soros Falsification Criteria:* Tách điều kiện hủy bias — Chính trước, Phụ sau.
  5. *Swing Watchlist:* 2 cặp chính trong nhóm 4 đồng; 0–1 cặp phụ nếu lịch material.
  6. *Next week look-ahead:* Snapshot tuần ISO kế từ mart (không viết báo cáo tuần thứ hai).
  7. *Gợi ý swing (Soros):* Không đặt lệnh chính lúc tin red; red là bài test giả thuyết.
  8. *Lint:* `scripts/analyst/report_lint.py` đối chiếu số/`fact_id` với Fact Pack sau khi sinh báo cáo.

#### Daily Risk Flash — không implement
* Google Calendar đã là operational alarm. Analyst layer chỉ làm strategic weekly brief.

---

### Phase 2: Trung hạn (Next Phase - Cần bổ sung dữ liệu)

#### 3. Output 2: `Monthly Regional Macro Scorecard` (La bàn chu kỳ các vùng)
* **Tần suất:** 1 lần / tháng (Đầu tháng).
* **Tại sao hiện tại chưa đủ dữ liệu?**
  * Cột `actual_txt`, `forecast_txt` hiện vẫn là chuỗi string (`"3.2%"`, `"50K"`). Chưa tính toán được chuỗi thời gian (trend lạm phát 3 tháng dốc lên hay dốc xuống).
  * Repo chưa có bảng lưu trữ **Lãi suất điều hành hiện tại** của 8 NHTW (FED: 5.25-5.5%, ECB: 3.75%...). Nếu chạy ngay, LLM sẽ phải tự bịa số.
* **Cần bổ sung gì để triển khai?**
  1. Thêm một hàm parse giá trị text thành float (`numeric_cleaner.py`).
  2. Tạo 1 file metadata nhỏ: `data/reference/central_bank_rates.csv` (lưu mức lãi suất hiện tại và stance Hawkish/Dovish).

---

### Phase 3: Dài hạn (Advanced - Cần hạ tầng Real-time)

#### 4. Output 4: `Event Deconstruct Flash` (Phản ứng tức thì sau tin Big 4)
* **Tần suất:** Đột xuất (5-10 phút sau khi có kết quả FOMC, NFP, CPI).
* **Tại sao hiện tại chưa đủ dữ liệu?**
  * Pipeline hiện tại chạy theo cơ chế **Batch** (chạy thủ công hoặc hàng tuần qua WARP chống Cloudflare). Không thể có số liệu `actual` ngay lập tức sau 5 phút tin ra.
* **Cần bổ sung gì để triển khai?**
  1. Kịch bản cào tự động siêu nhỏ (micro-fetch) kích hoạt theo lịch giờ sự kiện.
  2. Bộ tính toán độ lệch tức thì $\Delta = \text{Actual} - \text{Forecast}$ để prompt model đánh giá cú sốc.

---

## 4. Kế Hoạch Thực Hiện Cho Phase 1

1. **Bước 1 — Fact Pack Builder (`scripts/analyst/fact_pack.py`):**
   * Script Python đọc `data/gold/mart/fact_calendar_release.csv` và các dim liên quan.
   * Tính toán sẵn: Đếm tin Red/Orange, gom nhóm theo Currency, phát hiện các tin cùng giờ (Clash), quy đổi giờ HCM.
   * Xuất ra payload JSON hoặc Markdown gọn gàng.
2. **Bước 2 — Prompt Template Sorosian (`docs/analyst/prompts/weekly_soros_prompt.md`):**
   * Xây dựng prompt chứa đầy đủ Semantic Contract, Mental Model Soros, quy tắc Falsification và format báo cáo chuẩn.
3. **Bước 3 — Lightweight Runner (`scripts/analyst/run_weekly_report.py`):**
   * Đọc cấu hình từ `.env` (Google AI Studio hoặc OpenRouter API key).
   * Ghép `Fact Pack` vào prompt, gửi tới model được chọn (miễn phí), ghi kết quả vào thư mục `reports/weekly/`.
4. **Bước 4 — Chạy thử nghiệm & Kiểm thử (Validation):**
   * Chạy báo cáo cho tuần thực tế của năm 2026 trong dataset để đánh giá độ sắc bén của nhận định.
5. **Bước 5 — Orchestrator ABCD (`scripts/run_weekly_abcd.py`):**
   * A: `fetch_weekly` (nfs.faireconomy.media, không WARP, `strategy=http`, firefox135). Fail-stop nếu A/B lỗi — không gọi LLM.
   * B: bronze this-week → landing → silver `YYYY_Www.csv` → rebuild Kimball (weekly thắng overlap).
   * C+D: Fact Pack + outlook + lint. Tuần báo cáo lấy từ dữ liệu vừa fetch, không hard-code.
   * Deploy: macOS venv + `scripts/run_weekly_abcd.py` (scheduled via Firstmate `fx-weekly` job).
