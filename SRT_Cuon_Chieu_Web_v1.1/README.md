# SRT Cuốn Chiếu v1.7.0

Ứng dụng Python/PySide6 dịch phụ đề Trung → Việt qua ChatGPT Web, giữ ID và mốc thời gian. Bản này dùng mã SRT hiện có và duy nhất module ai_chatgpt.cp312-win_amd64.pyd do người dùng cung cấp. Các thành phần của ứng dụng bên ngoài khác vẫn được gỡ.

## Cài và chạy trên Windows

1. Cài Python 3.12, bản 64-bit, để nạp đúng ABI của module.
2. Cập nhật repository bằng git pull origin main.
3. Chạy run_windows.bat để cài PySide6 và mở app.
4. Tiêu đề phải hiện v1.7.0. Nhật ký khởi động phải ghi “Đang dùng module ai_chatgpt.pyd do người dùng cung cấp.” Nếu không nạp được, nhật ký báo rõ lý do và dùng bộ Web tích hợp.

File .exe đã build từ bản cũ vẫn chứa mã và thành phần cũ. Muốn dùng bản mới, chạy run_windows.bat hoặc build lại bằng build_exe_windows.bat. Chỉ dùng module đã kèm trong repository; không bổ sung lại module chính của ứng dụng ngoài.

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

    python -B -m unittest -v test_engine test_web_connect test_native_chatgpt_bridge test_response_capture test_app_web_bridge

Trên Linux không màn hình, đặt QT_QPA_PLATFORM=offscreen và QT_QUICK_BACKEND=software. Các kiểm thử DOM trong test_web_connect cần Node.js; nếu thiếu sẽ báo skipped. Kiểm thử tích hợp dùng trang HTML cục bộ trên QtWebEngine, không thay thế kiểm tra thực tế với ChatGPT trên Windows.

Chạy build_exe_windows.bat trên Windows để build lại dist/SRT_Cuon_Chieu bằng PyInstaller. Spec thu thập ứng dụng, thư viện PySide6 và duy nhất binary ai_chatgpt đã kèm.

## Module và giới hạn dịch vụ

Module ai_chatgpt cung cấp JavaScript gửi/đọc giao diện, không cấp tài khoản, hạn mức hay mô hình AI riêng. Dùng chế độ khách chỉ khi trang cho phép. Ứng dụng giữ cơ chế nhận biết thông báo chờ, lưu checkpoint và tiếp tục khi đến hạn; không bảo đảm ChatGPT Web không giới hạn hoặc không yêu cầu đăng nhập.

Bản này không nạp module ZK_API_WEB hoặc khởi chạy ZenKun Loader. Binary ai_chatgpt giữ nguyên SHA-256 e1f884cbed7b0a97d8e2d0f85e5e05016933c00aeb999e0d79842587df1be6a5. Kiểm thử Linux kiểm tra lớp tích hợp với API giả lập trên QtWebEngine; cần xác nhận binary thật trên Windows qua nhật ký khởi động.
