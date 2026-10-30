# SRT Cuốn Chiếu v1.8.0

Ứng dụng Python/PySide6 dịch phụ đề Trung → Việt, giữ ID và mốc thời gian. Chế độ mặc định mới là **Ollama chạy trên máy**, không cần tài khoản ChatGPT hay API key. ChatGPT Web vẫn có thể chọn trong mục “Chọn bộ dịch”.

## Cài và chạy trên Windows

1. Cài Python 3.12, bản 64-bit, cho launcher hiện có và chế độ Web tùy chọn.
2. Cập nhật repository bằng git pull origin main.
3. Chạy run_windows.bat để cài PySide6 và mở app.
4. Tiêu đề phải hiện v1.8.0. Mục “Chọn bộ dịch” mặc định là Ollama ở lần đầu; app nhớ lựa chọn cho lần sau.

File .exe đã build từ bản cũ vẫn chứa mã và thành phần cũ. Muốn dùng bản mới, chạy run_windows.bat hoặc build lại bằng build_exe_windows.bat. Chỉ dùng module đã kèm trong repository; không bổ sung lại module chính của ứng dụng ngoài.

## Dùng Ollama trên Windows

1. Cài [Ollama cho Windows](https://ollama.com/download/windows), rồi mở Ollama. App SRT cũng có nút mở trang cài này.
2. Trong SRT, chọn “Ollama — chạy trên máy, không đăng nhập”, bấm **Kiểm tra Ollama / Đọc mô hình đã cài**.
3. Để mô hình **qwen3:4b**, bấm **Tải mô hình đã chọn** và chờ hoàn tất. Lần đầu cần Internet và dung lượng vài GB. Có thể dừng rồi tải tiếp. Nếu thích dùng CMD, lệnh tương đương là:

       ollama pull qwen3:4b

4. Mở SRT rồi bấm **Bắt đầu dịch cuốn chiếu**. Kết quả tự điền vào cột tiếng Việt và checkpoint. Bấm **Lưu SRT** khi xong.

Với RAM từ 16 GB và NVIDIA, qwen3:4b là lựa chọn khởi đầu. Ollama tự chọn GPU khi driver và VRAM phù hợp; nếu VRAM thiếu có thể dùng thêm RAM/CPU nên chậm hơn. Có thể nhập qwen3:8b rồi tải nếu máy đủ bộ nhớ, hoặc qwen3:1.7b nếu thiếu bộ nhớ. Chất lượng dịch phụ thuộc mô hình; nên kiểm tra một đoạn ngắn trước khi dịch phim dài.

Mặc định 8 ID/lô, không nghỉ giữa lô, chờ tối đa 600 giây khi không có tiến triển. Mô hình được giữ trong bộ nhớ giữa các lô. Giảm số dòng/lô nếu máy chậm hoặc thiếu bộ nhớ; tăng thời gian chờ nếu lần nạp đầu lâu. App chỉ gửi một yêu cầu dịch tại một thời điểm, không tự gửi lại khi mất kết nối hoặc hết giờ.

Sau khi đã cài Ollama và tải mô hình, có thể dịch khi ngắt Internet. Phụ đề chỉ gửi tới **127.0.0.1:11434**, không qua ChatGPT, không chịu hạn mức tin nhắn của ChatGPT. Chế độ Ollama không nạp module ai_chatgpt.pyd và từ chối mô hình cloud. Không tự chuyển sang Web khi có lỗi. Thời gian chạy, tốc độ và dung lượng vẫn phụ thuộc máy của bạn.

**Tạm dừng** để lô đang xử lý hoàn tất rồi chờ, **Tiếp tục** chuyển sang phần còn thiếu. **Dừng Ollama / Dừng lại** hủy yêu cầu đang chạy và giữ các lô đã lưu. Nếu phản hồi sai ID/số dòng, chỉ những ID chưa hợp lệ được thử lại riêng, tối đa hai lần. Bản dịch đang phát dở chưa được nhập.

Nếu báo không kết nối: kiểm tra Ollama đang mở, chạy ở địa chỉ mặc định. Nếu báo model not found: tải đúng mô hình đã chọn. Nếu Ollama hết bộ nhớ: dùng mô hình nhỏ hơn, đóng ứng dụng chiếm VRAM và giảm số dòng/lô.

## Dịch SRT

- Mở đúng file SRT ở vị trí cũ để khôi phục file .progress.json cùng thư mục.
- Chọn Ollama đã có mô hình, hoặc mở ChatGPT Web và kiểm tra ô nhập sẵn sàng. Phép kiểm tra Web không tự gửi lời chào.
- Chọn số dòng/lô, thời gian chờ và thời gian nghỉ giữa lô, rồi bắt đầu.
- Bản dịch được kiểm tra đúng ID, không trùng ID và đúng số dòng mỗi cue trước khi cập nhật bảng/checkpoint. Timestamp không được gửi cho AI chỉnh sửa.
- Các dòng hợp lệ được giữ lại; dòng thiếu/sai được thử lại riêng có giới hạn.
- Tạm dừng ngừng chuẩn bị lô mới; Dừng kết thúc phiên và giữ các dòng đã nhận.
- Lưu SRT xuất UTF-8. Nếu còn dòng thiếu, app hỏi trước khi giữ nguyên tiếng Trung cho các dòng đó.

## Phục hồi khi dùng ChatGPT Web

Tùy chọn “Tự phục hồi khi Web chậm” bật mặc định, thử phục hồi sau 5 giây, tối đa 3 lần/giai đoạn. Nếu đã gửi lô, phục hồi chỉ đọc lại phản hồi, không gửi trùng prompt. Nút gửi chưa bật thì tiếp tục chờ nút được bật. Giới hạn chờ phản hồi tối đa 15 phút vẫn áp dụng.

Bộ theo dõi DOM giữ JSON đầy đủ của đúng lô nếu nó xuất hiện rồi biến mất giữa hai lần đọc. Python kiểm tra lại trước khi lưu. Không khôi phục được nội dung chưa bao giờ có JSON hoàn chỉnh trong DOM.

Nút “Hiện ô chat” dừng phiên rồi cuộn tới ô nhập còn tồn tại. Nếu trang không có ô nhập, dùng ⟳ để tải lại bằng cùng hồ sơ trình duyệt, rồi bắt đầu lại phần còn thiếu. Tải lại hủy callback cũ và giữ checkpoint.

## ChatGPT Web và giới hạn

ChatGPT Web là dịch vụ bên ngoài; giao diện có thể thay đổi. Có thể dùng chế độ khách khi trang cho phép; khi dịch vụ yêu cầu đăng nhập, xác minh hoặc chờ, ứng dụng không thể bỏ qua. Thông báo “Try again after H:MM AM/PM” được nhận diện để giữ tiến độ, đếm ngược và thử tiếp khi đến giờ.

Dữ liệu đăng nhập vẫn do trang Web xử lý. Hồ sơ QtWebEngine giữ cookie trong thư mục dữ liệu ứng dụng. Không tự xóa hồ sơ/cookie khi cập nhật. Đăng xuất trong Web nếu dùng chung máy.

## Kiểm thử và đóng gói

Từ thư mục SRT_Cuon_Chieu_Web_v1.1:

    python -B -m unittest -v test_engine test_web_connect test_native_chatgpt_bridge test_ollama_backend test_app_ollama test_response_capture test_app_web_bridge

Trên Linux không màn hình, đặt QT_QPA_PLATFORM=offscreen và QT_QUICK_BACKEND=software. Các kiểm thử DOM trong test_web_connect cần Node.js; nếu thiếu sẽ báo skipped. Kiểm thử Ollama dùng máy chủ HTTP cục bộ giả lập API thật: streaming Unicode, tải mô hình, hủy yêu cầu, timeout, retry, checkpoint và xuất SRT. Không cần tải mô hình cho bộ test; kiểm thử này không đánh giá chất lượng dịch hay tốc độ GPU thực tế. Kiểm thử Web dùng HTML cục bộ trên QtWebEngine, không thay thế kiểm tra thực tế với ChatGPT trên Windows.

Chạy build_exe_windows.bat trên Windows để build lại dist/SRT_Cuon_Chieu bằng PyInstaller. Spec thu thập ứng dụng, thư viện PySide6 và duy nhất binary ai_chatgpt đã kèm.

## Module và giới hạn dịch vụ

Chỉ khi kết nối/dịch bằng ChatGPT Web, app mới thử nạp module ai_chatgpt. Nhật ký báo rõ module có được nạp hay đang dùng bộ Web tích hợp. Module này cung cấp JavaScript gửi/đọc giao diện, không cấp tài khoản, hạn mức hay mô hình AI riêng. Dùng chế độ khách chỉ khi trang cho phép. Ứng dụng giữ cơ chế nhận biết thông báo chờ, lưu checkpoint và tiếp tục khi đến hạn; không bảo đảm ChatGPT Web không giới hạn hoặc không yêu cầu đăng nhập.

Bản này không nạp module ZK_API_WEB hoặc khởi chạy ZenKun Loader. Binary ai_chatgpt giữ nguyên SHA-256 e1f884cbed7b0a97d8e2d0f85e5e05016933c00aeb999e0d79842587df1be6a5. Kiểm thử Linux kiểm tra lớp tích hợp với API giả lập trên QtWebEngine; cần xác nhận binary thật trên Windows qua nhật ký khởi động.
