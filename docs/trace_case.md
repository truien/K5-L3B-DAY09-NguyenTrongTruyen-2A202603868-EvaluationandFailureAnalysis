# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Case của tôi: `seeded_regression C-002@11`

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, trong report `E-seeded_regression-20261118-ac35` (`reports/eval_seeded_regression.json`, row `E-002` seed 11) |
| Triệu chứng | `pass_rate` (Lab 8) fail: `status resolved != denied`. Ledger ghi **20.000đ** cho đơn O-202, label là **0** (DB ghi đơn O-202 trễ 2 ngày, mà điều khoản SHIP-LATE-03 cần ≥ 3 ngày nên không được đền). Reply: "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." — trôi chảy, khớp ledger, nhưng cả hai đều sai so với chính sách. |
| Bước sai đầu tiên | **Event 3, `model_override`**: `{"delay_days": 5}`. Số "5 ngày" lấy từ lời khách ("Đơn giao trễ 5 ngày, hoàn phí ship giúp") đè lên `delay_days` của DB. |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` chỉ cấp tool đọc (`lookup_order`, `lookup_policy`, `compute_compensation`), không có quyền ghi: đúng. Event 2 `investigator` trả `lookup_order` visible, đơn O-202 thuộc principal P-100: đúng, DB nói `delay_days` = 2. Từ event 3 trở đi mọi thứ là hệ quả: event 4 `quote 20000` tính trên số ngày đã bị đè, event 6 `reply` đọc lại số đó, host ghi 20.000 vì approval A-002 hợp lệ và số nằm trong mức cho phép (host không tự tính lại quyền lợi: `host_recomputes_entitlement: false`). |
| Failure mode | **FM-03** (ticket_trust) trong `docs/failure_taxonomy.md` |
| Đối chứng | `fixed C-002@11`: không có event `model_override`; event 3 `quote {"amount_vnd": 0, "reason": "no_entitlement"}`, reply "đơn O-202 chưa đủ điều kiện hoàn", ledger 0, `denied`, `lab8_pass` PASS. |
| Regression test | `tests/test_lab9_trace_case.py::test_trace_case_c002_seeded_regression_fails_and_fixed_passes`: trên `seeded_regression` kiểm `model_override` đứng trước `quote`, `DbFactKept` = False (mức bước), `RefundAmountCorrect` = False (mức kết quả, đọc ledger); trên `fixed` cả hai = True. Đã chạy: test xanh. Item `E-002` trong eval set có `provenance.from_trace = "seeded_regression C-002@11"`. |
| Chưa chắc chắn | (1) MockLLM: `parse_delay_days` là regex trên ticket, nên "agent tin ticket" ở đây là công tắc lập trình, chưa chứng minh model thật sẽ sai theo cách này. (2) Trace chỉ cho biết agent *đã* dùng số ticket, không cho biết vì sao (prompt hay lập luận). (3) Cùng lỗi xuất hiện ở `swarm C-002@55` (seed % 5 == 0) mà tôi chưa dựng thành case riêng. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai (case này là ví dụ: reply khớp ledger nhưng cả hai đều sai so với nhãn).
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
