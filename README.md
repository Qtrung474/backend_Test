# Backend Service - Multi-vendor Marketplace API
Thư mục này dành cho việc phát triển API và dịch vụ phía Backend cho mô hình **Sàn TMĐT trung gian (như Shopee / Lazada)**.

### Các nhóm API cần thiết cho Admin Sàn:
1. **Tổng quan & Thống kê Sàn (Marketplace Analytics):**
   - `GET /api/v1/admin/metrics` — Lấy Tổng GMV, Doanh thu hoa hồng sàn, Tổng số Shop, Số vụ tranh chấp.
   - `GET /api/v1/admin/charts/gmv-commission` — Dữ liệu biểu đồ GMV vs Phí hoa hồng 12 tháng.
   - `GET /api/v1/admin/charts/shop-tiers` — Tỷ trọng GMV theo phân hạng Shop (Mall, Yêu thích+, Tiêu chuẩn).

2. **Quản lý Cửa hàng / Sellers & Kiểm duyệt (Moderation):**
   - `GET /api/v1/admin/shops/pending` — Danh sách hồ sơ đăng ký mở Shop chờ duyệt KYC.
   - `POST /api/v1/admin/shops/:id/approve` — Phê duyệt hoặc từ chối mở Shop, gắn nhãn `MALL` / `FAVORITE`.
   - `GET /api/v1/admin/products/moderation` — Danh sách sản phẩm do các Shop đăng chờ duyệt hoặc bị báo cáo vi phạm.

3. **Giao dịch Trung gian, Đối soát & Giải ngân (Escrow & Payouts):**
   - `GET /api/v1/admin/orders` — Danh sách đơn hàng toàn sàn kèm thông tin Shop, Người mua, Phí sàn (7%) và trạng thái giữ tiền (Escrow).
   - `POST /api/v1/admin/orders/:id/release-escrow` — Giải ngân tiền từ quỹ giữ hộ của Sàn về Ví của Shop sau khi trừ hoa hồng.
   - `POST /api/v1/admin/payouts/:id/approve` — Duyệt lệnh rút tiền từ Ví Shop về tài khoản ngân hàng.

4. **Phân xử Tranh chấp & Chiến dịch Toàn sàn:**
   - `POST /api/v1/admin/disputes/:id/resolve` — Phán quyết hoàn tiền 100% cho Người mua hoặc bác bỏ khiếu nại để trả tiền cho Shop.
   - `POST /api/v1/admin/campaigns` — Tạo chiến dịch Flash Sale, mã Freeship toàn sàn và cấu hình % phí hoa hồng.
