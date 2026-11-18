# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (backend REPLAY: verdict của judge đã lưu sẵn trong CSV, không gọi model).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** cả ba | **Dùng**, có điều kiện (sửa rubric, xem dưới) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Trượt** κ và recall | **Loại** khỏi gate |

Ma trận nhầm lẫn (FAIL là lớp dương, tức việc của judge là *tìm* lỗi):

| | judge FAIL | judge PASS |
|---|---|---|
| tone · người FAIL | tp 24 | fn 6 |
| tone · người PASS | fp 4 | tn 66 |
| helpful · người FAIL | tp 9 | fn 21 |
| helpful · người PASS | fp 0 | tn 70 |

Tỉ lệ lỗi sau hiệu chỉnh Rogan-Gladen: tone quan sát 0.28 → **0.30** (người gán 30/100 FAIL). helpful quan sát **0.09** → **0.30**: judge chỉ thấy 9% trong khi thực tế 30% reply hỏng.

## ≥5 case audit thủ công (tone_ok)
| # | Case | Judge nói | Người nói | Ai đúng? | Hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người: xưng "em"+"nha" quá suồng sã với khách. | Thêm vào rubric: xưng hô cố định "LogiX – anh/chị", cấm "em/nha/nhé" trong câu trả lời cho khách. |
| 2 | H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người: giọng ra lệnh; judge chỉ thấy "Dạ, vui lòng". | Thêm: câu mệnh lệnh phủ định ("không cần…", "đừng…") là FAIL dù có "Dạ". |
| 3 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người: ngắn nhưng đủ ý và lịch sự; judge phạt vì "thiếu xin lỗi". | Sửa: xin lỗi chỉ bắt buộc khi từ chối hoặc khi lỗi do LogiX; thông báo hoàn tiền thành công không cần xin lỗi. |
| 4 | H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người: "refund" nằm trong từ vựng CS cho phép. | Thêm danh sách từ vay được phép (refund, ship, order) vào rubric. |
| 5 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge**: nhãn người sai (đọc nhầm ticket). | **Sửa nhãn người** thành FAIL, không sửa rubric. Sau sửa: P 0.857→0.893, R 0.800→0.806, κ 0.757→0.784. |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người đúng, nhưng lỗi là *cam kết ngoài kết quả hệ thống*, không phải giọng điệu. | Tách tiêu chí: tone_ok không chấm cam kết; chuyển sang grader code/policy ("sẽ hoàn thêm" khi ledger không còn gì). |
| 7 | H-094 "Da, LogiX da hoan 40.000đ cho don O-341, xin loi…" | PASS | FAIL | Người: mất dấu tiếng Việt (dịch máy). | Thêm: bắt buộc tiếng Việt có dấu; chạy kiểm tra Unicode bằng code trước judge. |

Còn lại: H-017 (xưng "bạn" với khách lớn tuổi: người đúng, cùng hướng với #1), H-070 (emoji ở ngữ cảnh khiếu nại: người đúng, thêm "cấm emoji trong khiếu nại"), H-088 ("Dạ, dạ" lỗi gõ: người cho qua, judge hơi khắt khe, thêm "một lỗi gõ nhỏ không trừ").
Trong 10 bất đồng: người đúng 8, judge đúng 1 (H-081), 1 hòa (H-088); 6 trong 10 bất đồng đều là judge **bỏ sót** lỗi giọng (fn), nên rubric cần liệt kê mẫu lỗi cụ thể thay vì "lịch sự, thân thiện".

## Vì sao `helpful` không được làm gate
- Recall 0.30 (21/30 reply hỏng lọt qua) và κ 0.375 < 0.6: một gate dùng judge này sẽ cho qua 70% bản hỏng. Chạy `python -m lab9.judge --csv data/eval/judge_helpful_public.csv` trả exit 1.
- Precision 1.000 không cứu được: judge không bao giờ báo nhầm, nhưng cũng hầu như không báo gì. Judge "lười" trông hoàn hảo nếu chỉ nhìn precision.
- Cột `human_failure` cho thấy gốc: 18/30 lỗi thật là **"sai tiền"** (reply nói số khác ledger, ví dụ HL-015 "55.000đ" trong khi ledger ghi 40.000đ). Judge không có ledger trong prompt nên không thể biết. Cả 18 case này bị bỏ sót. 3 lỗi còn lại bị bỏ sót là "sai xưng hô".
- Quyết định: **"helpful về tiền" chuyển sang code** (`reply_matches_ledger`, FM-08), vì là phép so số. Không cố sửa judge bằng prompt dài hơn.

## Kết luận
- Tiêu chí bị loại: `helpful` (κ 0.375, R 0.30). Tiêu chí được dùng: `tone_ok`, nhưng chỉ sau khi sửa rubric theo bảng trên và sửa nhãn H-081; tone_ok là tín hiệu theo dõi, không phải gate chặn (gate chặn chỉ dùng code: tiền và approval).
- Rủi ro còn lại: (1) judge chỉ được kiểm trên dữ liệu replay đã công khai, chưa có tập held-out mới, nên các con số này có thể lạc quan; (2) n = 100, 30 FAIL: khoảng tin cậy của recall 0.8 rộng (± ~0.15); (3) rubric sửa xong chưa được chạy lại bằng judge thật.
