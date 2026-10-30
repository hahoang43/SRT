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

### Kiểm thử kết nối và nhận phản hồi

- Kiểm tra kết nối chỉ xác nhận tên miền và ô chat sẵn sàng, không gửi lời chào; khi thành công hiển thị thông báo.
- Kết quả JavaScript được truyền qua JSON để QtWebEngine chuyển đầy đủ dữ liệu sang Python.
- Bộ đọc phản hồi đếm nhất quán các tin nhắn assistant và ưu tiên JSON trong khối mã, tránh lấy nhãn ngôn ngữ/nút sao chép làm nội dung dịch.
- Kiểm thử tích hợp cục bộ: `python -B -m unittest -v test_app_web_bridge` (cần PySide6/QtWebEngine). Trên Linux không màn hình, đặt `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software`. Bộ kiểm thử DOM trong `test_web_connect` cần Node.js; nếu thiếu sẽ báo skipped.
- Kiểm thử cục bộ không thay thế xác minh với tài khoản ChatGPT đang đăng nhập; giao diện Web thực tế vẫn có thể thay đổi.

### Chế độ khách và dịch nhiều lô

- Không bắt buộc đăng nhập ở phía ứng dụng: dùng chế độ khách nếu ChatGPT hiển thị ô chat và cho gửi tin nhắn. Nút “Log in” trên trang là của ChatGPT. Khi dịch vụ yêu cầu đăng nhập hoặc giới hạn sử dụng, ứng dụng không thể bỏ qua điều kiện đó.
- Mặc định 20 dòng/lô. Nút gửi được bấm sau khi ô chat cập nhật; không coi phím Enter giả lập là đã gửi thành công.
- Nhận diện phản hồi theo từng lượt hội thoại, kể cả giao diện khách thiếu thuộc tính author-role. Chấp nhận JSON có phần giải thích bao quanh nhưng không tự sửa JSON bị cắt dở.
- Dòng hợp lệ được điền vào bảng và lưu checkpoint ngay khi phản hồi hoàn tất. Dòng thiếu, trùng ID hoặc sai số dòng được thử lại riêng tối đa 2 lần; không xóa bản dịch đã nhận. Sau khi khắc phục, tiếp tục các lô còn lại.
- Thời gian chờ là thời gian không có tiến triển; có ký tự mới sẽ gia hạn. Mỗi lô có giới hạn tổng cộng 15 phút. Lỗi JSON cụ thể được hiển thị thay vì chỉ chờ im lặng.
- Kiểm thử: `python -B -m unittest -v test_engine test_web_connect test_app_web_bridge`. Bộ tích hợp gồm trang khách cục bộ, nút gửi bật trễ, gửi hai lô liên tiếp, cập nhật bảng, thử lại và bỏ qua callback của phiên đã dừng. Chưa xác minh với phiên ChatGPT khách thực tế trên Windows.

### Chẩn đoán v1.2.1

- Kiểm tra tiêu đề cửa sổ có **v1.2.1**. `git pull` không cập nhật file `.exe` đã đóng gói trước đó; dùng `run_windows.bat` hoặc build lại `.exe`.
- Nhật ký ghi số phản hồi, số ký tự, trạng thái đang tạo và lỗi JavaScript; nút **Sao chép nhật ký** giúp gửi thông tin lỗi. Không ghi cookie, mật khẩu hoặc toàn văn phản hồi vào nhật ký chẩn đoán.
- Khi CSS streaming còn sót, chỉ nhận JSON đầy đủ, đúng toàn bộ lô sau 4 lần đọc ổn định và khi nút Stop không còn hiển thị. Không gửi lô mới trong khi nút Stop còn xuất hiện.
- Nếu QtWebEngine không trả callback trong 10 giây, dừng và báo lỗi thay vì đứng vô hạn.
- Những kiểm thử dùng HTML cục bộ không xác nhận đăng nhập hay khả năng dùng ChatGPT khách trên một máy thực tế. Khi lỗi vẫn xảy ra, cần nhật ký và phiên bản đang chạy để chẩn đoán tiếp.

### v1.2.2: Web có JSON nhưng nhật ký báo 0 phản hồi

Bổ sung bộ đọc dự phòng cho vùng hội thoại (`main`, `role=main`, `#thread`, `#conversation`) khi giao diện khách không có role/turn/markdown. Bộ đọc lấy đối tượng JSON dịch hoàn chỉnh, xử lý dấu ngoặc/escape trong chuỗi, loại ô soạn thảo, tin nhắn người dùng và prompt vừa gửi; không nhận JSON cắt dở hoặc ví dụ `vi:"..."`.

Dòng “Cấu trúc Web” trong nhật ký cho biết số role/turn, số ký tự vùng hội thoại và số JSON dịch tìm được, không ghi toàn văn hội thoại. Nếu vẫn thấy 0 phản hồi trong v1.2.2 dù Web có JSON, gửi thêm dòng này để chẩn đoán chính xác. Đây là sửa bộ đọc giao diện, không thay đổi yêu cầu đăng nhập của ChatGPT.
