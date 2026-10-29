# SRT Cuốn Chiếu v1.1 — ChatGPT Web (không cần API key)

Ứng dụng Python/PySide6 dành cho Windows. Bố cục theo ảnh mẫu: bảng STT, thời gian, tiếng Trung, tiếng Việt; các nút mở file, lưu SRT, prompt, ChatGPT Web, nhật ký và tiến độ.

## Điểm mới v1.1

- **Đã bỏ toàn bộ form OpenAI API key, model và request API.** Không cần mua hay nhập API key.
- Nhấn **⚡ Mở kết nối AI** (hoặc **Kiểm tra kết nối Web**): mở trang `https://chatgpt.com/` ngay trong khung bên phải và kiểm tra ô chat đã sẵn sàng. Ứng dụng không tự gửi lời chào.
- **Hiện thông báo KẾT NỐI THÀNH CÔNG khi trang ChatGPT và ô chat sẵn sàng**; không đọc hoặc thu thập nội dung trả lời.
- Nếu trang yêu cầu đăng nhập, bạn đăng nhập **bằng tay** trong Web. Nếu nhắn tự động không được do trang thay đổi, tool hiển thị thông tin và hướng dẫn thử lại; không tự báo kết nối thành công sai.
- Dịch cuốn chiếu tự động: app tự gửi từng batch lên ChatGPT Web, nhận JSON phản hồi,
  kiểm tra ID/số dòng và điền trực tiếp vào bảng đến khi hết file.
- Prompt được tự động lưu bằng QSettings ngay khi người dùng chỉnh sửa.

## Cài và chạy trên Windows

1. Cài Python 3.10 trở lên từ python.org (khi cài hãy chọn Add Python to PATH).
2. Giải nén toàn bộ thư mục.
3. Nhấn đúp `run_windows.bat`. Lần đầu cần Internet để cài PySide6 có QtWebEngine.
4. Nhấn **⚡ Mở kết nối AI**. Nếu ChatGPT yêu cầu đăng nhập, hoàn tất đăng nhập trong khung bên phải.
5. Khi xuất hiện ô chat, app xác nhận kết nối và hiện hộp thông báo; app không tự gửi tin nhắn.

> Nếu ChatGPT không hỗ trợ đăng nhập trong trình duyệt nhúng QtWebEngine, không thể tự xác minh kết nối bằng chế độ này. Tải lại Web hoặc thử lại. Ứng dụng không làm cách nào để né xác thực hay biện pháp bảo vệ.

## Dịch file SRT Trung → Việt theo từng lô

1. Nhấn **Mở File SRT**, bảng bên trái hiển thị STT, thời gian, tiếng Trung và tiếng Việt.
2. Có thể vào **MỞ BẢNG TẠO PROMPT** để sửa yêu cầu biên dịch. Khóa JSON/ID và số dòng vẫn được bổ sung tự động.
3. Chọn số dòng mỗi lô và thời gian nghỉ giữa lô; nhấn **BẮT ĐẦU DỊCH CUỐN CHIẾU**.
4. Tool tự gửi prompt + JSON lên ChatGPT Web, tự nhận JSON phản hồi và cập nhật bảng.
5. Tool kiểm tra đủ ID, không trùng ID, không mất dòng văn bản, lưu checkpoint `.progress.json`,
   chờ số giây đã chọn và tự gửi lô kế tiếp.
6. **Tạm dừng** ngừng chuẩn bị lô tiếp theo; **Dừng lại** kết thúc phiên mà không mất tiến độ. **Lưu SRT** xuất UTF-8 và giữ nguyên các mốc thời gian.

**Lưu ý quan trọng:** ChatGPT Web *không phải* API chính thức. Tính năng tự động phụ thuộc
vào giao diện Web, trạng thái đăng nhập và các selector có thể thay đổi.

## Bảo mật và giới hạn

- Không có trường API key hoặc mã nguồn gọi API.
- Không đọc, lưu mật khẩu hay can thiệp trang đăng nhập. Hồ sơ trình duyệt nhúng có thể giữ cookie trong thư mục dữ liệu app; khi dùng máy chung cần đăng xuất.
- Kiểm tra kết nối dùng thao tác giao diện ChatGPT đang hiển thị, nên có thể bị ảnh hưởng khi trang thay đổi, yêu cầu xác minh, chặn QtWebEngine hoặc mất mạng. Chưa có xác nhận vận hành thực tế trên tất cả các phiên bản Windows hoặc tài khoản ChatGPT.
- Không sử dụng việc nghỉ giữa lô để lách giới hạn hay biện pháp chống bot; đây chỉ là thời gian chờ giữa các batch.
- `mau_phu_de.srt` là file mẫu để thử nhập và xuất.

## Xây dựng .exe trên Windows

Nhấp đúp `build_exe_windows.bat` để cài PyInstaller và đóng gói vào thư mục `dist/SRT_Cuon_Chieu/`. Đây là bản **mã nguồn**, không phải file `.exe` đã build sẵn. Sử dụng `--onedir` để QtWebEngine có đủ thư viện đi kèm.

## Cấu trúc

- `app.py` — giao diện và quy trình kết nối Web / dịch tự động cuốn chiếu.
- `web_connect.py` — mã JavaScript gửi lời chào, gửi batch và nhận phản hồi JSON.
- `srt_engine.py` — phân tích SRT, giữ ID và timestamp, kiểm tra JSON, xuất file và checkpoint.
- `test_engine.py` / `test_web_connect.py` — kiểm tra mã nguồn.
- `run_windows.bat`, `build_exe_windows.bat`, `requirements.txt` — khởi chạy và đóng gói.

Chạy kiểm thử: `python -m unittest -v test_engine test_web_connect`.
