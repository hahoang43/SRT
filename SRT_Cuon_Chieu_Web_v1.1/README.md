# SRT Cuốn Chiếu v1.6.0

Ứng dụng Python/PySide6 dịch phụ đề Trung → Việt qua ChatGPT Web, giữ ID và mốc thời gian. Bản này chạy bằng mã Python trong repository; đã gỡ hai module đóng bên ngoài cùng bộ nạp và cấu hình đóng gói liên quan.

## Cài và chạy trên Windows

1. Cài Python 3.10 trở lên, bản 64-bit; Python 3.12 hiện có vẫn dùng được.
2. Cập nhật repository bằng git pull origin main.
3. Chạy run_windows.bat để cài PySide6 và mở app.
4. Tiêu đề phải hiện v1.6.0. Nhật ký khởi động ghi “Đang dùng bộ Web Python/PySide6 tích hợp của ứng dụng SRT.”

File .exe đã build từ bản cũ vẫn chứa mã và thành phần cũ. Muốn dùng bản mới, chạy run_windows.bat hoặc build lại bằng build_exe_windows.bat. Không sao chép thành phần đóng cũ trở lại thư mục ứng dụng.

## Dịch SRT

- Mở đúng file SRT ở vị trí cũ để khôi phục file .progress.json cùng thư mục.
- Mở ChatGPT Web và kiểm tra ô nhập sẵn sàng. Phép kiểm tra kết nối không tự gửi lời chào.
- Chọn số dòng/lô, thời gian chờ và thời gian nghỉ giữa lô, rồi bắt đầu.
- Bản dịch được kiểm tra đúng ID, không trùng ID và đúng số dòng mỗi cue trước khi cập nhật bảng/checkpoint. Timestamp không được gửi cho AI chỉnh sửa.
- Các dòng hợp lệ được giữ lại; dòng thiếu/sai được thử lại riêng có giới hạn.
- Tạm dừng ngừng chuẩn bị lô mới; Dừng kết thúc phiên và giữ các dòng đã nhận.
- Lưu SRT xuất UTF-8. Nếu còn dòng thiếu, app hỏi trước khi giữ nguyên tiếng Trung cho các dòng đó.

## Phục hồi khi Web chậm

Tùy chọn “Tự phục hồi khi Web chậm” bật mặc định, thử phục hồi sau 5 giây, tối đa 3 lần/giai đoạn. Nếu đã gửi lô, phục hồi chỉ đọc lại phản hồi, không gửi trùng prompt. Nút gửi chưa bật thì tiếp tục chờ nút được bật. Giới hạn chờ phản hồi tối đa 15 phút vẫn áp dụng.

Bộ theo dõi DOM giữ JSON đầy đủ của đúng lô nếu nó xuất hiện rồi biến mất giữa hai lần đọc. Python kiểm tra lại trước khi lưu. Không khôi phục được nội dung chưa bao giờ có JSON hoàn chỉnh trong DOM.

Nút “Hiện ô chat” dừng phiên rồi cuộn tới ô nhập còn tồn tại. Nếu trang không có ô nhập, dùng ⟳ để tải lại bằng cùng hồ sơ trình duyệt, rồi bắt đầu lại phần còn thiếu. Tải lại hủy callback cũ và giữ checkpoint.

## ChatGPT Web và giới hạn

ChatGPT Web là dịch vụ bên ngoài; giao diện có thể thay đổi. Có thể dùng chế độ khách khi trang cho phép; khi dịch vụ yêu cầu đăng nhập, xác minh hoặc chờ, ứng dụng không thể bỏ qua. Thông báo “Try again after H:MM AM/PM” được nhận diện để giữ tiến độ, đếm ngược và thử tiếp khi đến giờ.

Dữ liệu đăng nhập vẫn do trang Web xử lý. Hồ sơ QtWebEngine giữ cookie trong thư mục dữ liệu ứng dụng. Không tự xóa hồ sơ/cookie khi cập nhật. Đăng xuất trong Web nếu dùng chung máy.

## Kiểm thử và đóng gói

Từ thư mục SRT_Cuon_Chieu_Web_v1.1:

    python -B -m unittest -v test_engine test_web_connect test_response_capture test_app_web_bridge

Trên Linux không màn hình, đặt QT_QPA_PLATFORM=offscreen và QT_QUICK_BACKEND=software. Các kiểm thử DOM trong test_web_connect cần Node.js; nếu thiếu sẽ báo skipped. Kiểm thử tích hợp dùng trang HTML cục bộ trên QtWebEngine, không thay thế kiểm tra thực tế với ChatGPT trên Windows.

Chạy build_exe_windows.bat trên Windows để build lại dist/SRT_Cuon_Chieu bằng PyInstaller. Spec chỉ thu thập ứng dụng và thư viện PySide6.
