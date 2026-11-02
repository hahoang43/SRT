# SRT Cuốn Chiếu v1.9.2

Ứng dụng Python/PySide6 dịch phụ đề Trung → Việt, giữ ID và mốc thời gian. **ChatGPT Web là bộ dịch mặc định**; có thể chọn **Gemini Web** để đăng nhập Google và dịch trong khung web, hoặc **Gemini API** với key Google AI Studio. Bản này đã bỏ Ollama; thiết lập bộ dịch Ollama cũ tự chuyển về ChatGPT Web, không xóa cookie hay checkpoint.

Hai nút **ChatGPT Web** và **Gemini Web** luôn hiện phía trên, kể cả khi đang chọn Gemini API. Bấm nút tương ứng để mở và kiểm tra Web. Chuyển về ChatGPT hiện lại đúng trang và hồ sơ đã mở, giữ cookie và bản nháp.

## Cài và chạy trên Windows

1. Cài Python 3.12, bản 64-bit, cho launcher hiện có và chế độ Web tùy chọn.
2. Cập nhật repository bằng git pull origin main.
3. Chạy run_windows.bat để cài PySide6 và mở app.
4. Tiêu đề phải hiện v1.9.2. Mục “Chọn bộ dịch” mặc định là ChatGPT Web; app nhớ lựa chọn cho lần sau.

File .exe đã build từ bản cũ vẫn chứa mã và thành phần cũ. Muốn dùng bản mới, chạy run_windows.bat hoặc build lại bằng build_exe_windows.bat. Chỉ dùng module đã kèm trong repository; không bổ sung lại module chính của ứng dụng ngoài.

## Dùng Gemini Web trong app (không cần API key)

1. Chọn **Gemini Web — đăng nhập Google, không cần API key** trong mục Chọn bộ dịch. Khung bên phải tự mở `https://gemini.google.com/app`, giống khung ChatGPT Web.
2. Đăng nhập tài khoản Google trực tiếp trên trang Gemini. Nếu trang mở cửa sổ đăng nhập/xác minh, cửa sổ đó dùng cùng hồ sơ Gemini. App không nhập hộ mật khẩu, đọc thông tin đăng nhập hoặc vượt CAPTCHA. Nếu Google từ chối đăng nhập trong QtWebEngine, tính năng này chưa dùng được với tài khoản đó; đăng nhập trong trình duyệt ngoài không tự chuyển cookie vào app.
3. Bấm **Mở Gemini Web / Kiểm tra kết nối Web**. Kiểm tra chỉ xác nhận đúng trang và ô nhập, không gửi lời chào. Sau khi thấy kết nối thành công, mở file SRT và bấm Bắt đầu dịch cuốn chiếu. Prompt và phản hồi xuất hiện trong khung Gemini; bản dịch hợp lệ tự cập nhật bảng và checkpoint.
4. Tạm dừng, tiếp tục, dừng, hiện ô chat và tải lại hoạt động tương tự ChatGPT. Khi chờ phản hồi, app chỉ đọc lại; không gửi lại lô đã bấm gửi. Mỗi lô được kiểm tra ID và số dòng trước khi nhập; timestamp giữ nguyên.

Gemini Web và Gemini API là **hai lựa chọn riêng**. Gemini Web dùng tài khoản Google, không dùng API key hay mô hình trong danh sách API; lỗi HTTP 404 của lựa chọn API không được xử lý bằng việc giảm số dòng/lô hoặc mở Web. App không tự chuyển giữa hai cách dịch. Hạn mức, mô hình, yêu cầu đăng nhập và xác minh của Gemini Web do Google quyết định.

Nếu Gemini để lại prompt của lô đã gửi trong ô nhập, app nhận diện đúng nội dung đó và thay bằng lô kế tiếp sau khi nhận bản dịch. Bản nháp khác do bạn nhập được giữ nguyên và báo rõ để bạn xử lý. Khi Gemini đang tạo phản hồi hoặc thay ô nhập, app chờ và thử chuẩn bị lại trong thời gian giới hạn; bước chuẩn bị không bấm gửi. Lỗi điền ô chat ghi kèm lý do cụ thể trong nhật ký, tiến độ đã dịch vẫn được lưu.

Khi điền prompt, app chờ QtWebEngine trả kết quả tối đa 30 giây (hoặc thời gian chờ đã chọn nếu ngắn hơn). Nếu callback bị chậm/mất và “Tự phục hồi khi Web chậm” đang bật, app thử kiểm tra lại cùng lô sau 5 giây, tối đa 3 lần. Prompt đã điền đúng được giữ nguyên để tiếp tục; callback cũ trả về muộn không tạo thêm lần gửi. Tắt phục hồi hoặc hết số lần thử thì app dừng và giữ checkpoint.

Nhật ký Gemini phân biệt thao tác bấm gửi với việc prompt xuất hiện trong hội thoại. Chẩn đoán có số lượt hỏi, trạng thái ô nhập và xác nhận prompt của lô, không ghi thêm nội dung prompt. Nếu hết thời gian chờ, thông báo cho biết prompt còn trong ô nhập, ô đã trống nhưng chưa xác nhận gửi, hay prompt đã vào hội thoại nhưng chưa có JSON hợp lệ. App nhận diện cả nút Dừng bằng nhãn tiếng Việt và biểu tượng để chờ Gemini hoàn tất trước khi chuẩn bị lô mới.

Cookie Gemini lưu trong `gemini_profile`, tách khỏi `chatgpt_profile`; chuyển bộ dịch giữ nguyên hồ sơ và tiến độ. Không dùng module `ai_chatgpt.pyd` cho Gemini Web. Gemini Web cần truy cập `gemini.google.com` và các trang đăng nhập/tài nguyên Google liên quan nếu mạng có giới hạn. DOM của Gemini có thể thay đổi; kiểm thử HTML cục bộ không thay thế kiểm tra đăng nhập/dịch thực tế trên Windows.

## Dùng Gemini API với Google AI Studio

1. Mở [Google AI Studio](https://aistudio.google.com/apikey), tạo API key cho dự án của bạn. Kiểm tra free tier, mô hình được hỗ trợ và hạn mức tại [trang giá](https://ai.google.dev/gemini-api/docs/pricing) và [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). Có key không đồng nghĩa mọi mô hình đều miễn phí hoặc không giới hạn. Với dự án bật thanh toán, yêu cầu có thể tính phí theo cấu hình của Google; ứng dụng không tự bật thanh toán.
2. Trong app, chọn **Gemini API — key Google AI Studio**, dán key vào ô được che. Key chỉ giữ trong phiên, không được lưu vào QSettings, checkpoint hay nhật ký. Có thể cung cấp qua biến môi trường `GEMINI_API_KEY` trước khi mở app; không đưa key vào repository hoặc chia sẻ trong chat.
3. Bấm **Kiểm tra key / Đọc mô hình Gemini**. Bước này đọc danh sách mô hình, không gửi phụ đề hay yêu cầu sinh nội dung. Danh sách được lọc theo khả năng `generateContent` và không xác nhận mô hình còn quota miễn phí. Mặc định gợi ý `gemini-2.5-flash`; nếu Google đã đổi hoặc ngừng hỗ trợ, chọn tên mô hình khả dụng trong danh sách hoặc nhập tên khác rồi kiểm tra quota trong AI Studio.
4. Mở file SRT rồi bấm **Bắt đầu dịch cuốn chiếu**. Mặc định 20 ID/lô, chờ tối đa 120 giây/yêu cầu, nghỉ 6 giây giữa lô. Giảm số dòng/lô khi đầu ra bị cắt. Mỗi lần chỉ gửi một yêu cầu dịch; thời gian nghỉ không bảo đảm tránh mọi giới hạn RPM/TPM/RPD của Google.
5. **Tạm dừng** chờ lô hiện tại xong rồi ngừng chuẩn bị lô mới; **Tiếp tục** dịch phần còn thiếu. **Dừng Gemini / Dừng lại** hủy chờ phản hồi và giữ các lô đã lưu. Google vẫn có thể xử lý yêu cầu đã nhận dù phía ứng dụng đã hủy.

Gemini dùng REST qua HTTPS tới `generativelanguage.googleapis.com`, gửi key trong header `x-goog-api-key`, không đưa key vào URL và không chuyển hướng yêu cầu. Cần Internet và quyền truy cập domain này qua firewall/proxy. Chỉ phụ đề và prompt được gửi; timestamp được giữ ở máy. Không cần cài SDK Gemini hoặc tải mô hình. Chế độ Gemini không nạp binary ChatGPT và không tự chuyển bộ dịch khi có lỗi.

Nếu sai key/quyền, hết quota (HTTP 429), mất mạng, hết thời gian hoặc nội dung bị chặn: phiên dừng, giữ checkpoint và báo lỗi; **không tự gửi lại yêu cầu API lỗi**. Kiểm tra key/quota/mô hình, chờ nếu cần rồi bấm Bắt đầu để tiếp tục phần còn thiếu. Riêng phản hồi HTTP thành công có `finishReason=MAX_TOKENS` được bỏ và thử lại với lô nhỏ hơn theo cơ chế bên dưới. Với phản hồi hoàn tất nhưng sai JSON/ID/số dòng, các ID hợp lệ được giữ và chỉ ID chưa hợp lệ được thử lại riêng tối đa hai lần; các lần này cũng tiêu thụ quota. Bản dịch bị cắt giữa chừng không được nhập.

## Dịch SRT

- Mở đúng file SRT ở vị trí cũ để khôi phục file .progress.json cùng thư mục.
- Chọn ChatGPT Web hoặc Gemini Web rồi kiểm tra ô nhập sẵn sàng; nếu dùng Gemini API, nhập key và chọn mô hình phù hợp. Phép kiểm tra Web không tự gửi lời chào.
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

### Xác minh truy cập và tự giảm lô

- ChatGPT Web và Gemini Web kiểm tra trạng thái DOM trước khi chuẩn bị/gửi/đọc phản hồi; nút gửi bị vô hiệu hóa hoặc nút Stop còn hiện thì tiếp tục chờ bằng timer, không gửi lô mới. Phiên Web cũng theo dõi chuyển trang, HTTP 403 và challenge xuất hiện trong lúc chờ.
- Khi phát hiện Cloudflare/CAPTCHA, HTTP 403 hoặc thông báo hết hạn mức không có giờ chờ được nhận diện, ứng dụng ngừng phiên, hủy thao tác gửi đang chờ và lưu checkpoint. Cookie, cache, hồ sơ và địa chỉ IP được giữ nguyên. Xử lý thông báo/xác minh trực tiếp trên Web, kiểm tra kết nối rồi bấm **Bắt đầu** để tiếp tục các ID còn thiếu. Ứng dụng không giả mạo fingerprint, xoay proxy hoặc xóa phiên để vượt giới hạn.
- Khi Web đã ngừng tạo và JSON dịch vẫn bị cắt ở cuối, hoặc Gemini API báo `MAX_TOKENS`, ứng dụng bỏ đầu ra dở, giảm số ID/lô còn một nửa (làm tròn xuống, tối thiểu 1) và thử lại phần chưa dịch sau thời gian nghỉ đã chọn. Giới hạn lô nhỏ hơn áp dụng đến hết phiên; giá trị “Dòng / lần” là mức trần người dùng đặt. Nếu lô 1 ID vẫn bị cắt thì dừng, giữ tiến độ và báo lỗi. Các lần thử lại API có thể tiêu thụ quota.
- Không chia nhỏ/thử lại để xử lý CAPTCHA, 403, 429, lỗi mạng, timeout hoặc phản hồi bị chặn. Phát hiện DOM là best effort và không thay thế kiểm tra dịch vụ thật; thông báo/HTML mới có thể cần cập nhật bộ nhận diện.

ChatGPT Web là dịch vụ bên ngoài; giao diện có thể thay đổi. Có thể dùng chế độ khách khi trang cho phép; khi dịch vụ yêu cầu đăng nhập, xác minh hoặc chờ, ứng dụng không thể bỏ qua. Thông báo “Try again after H:MM AM/PM” được nhận diện để giữ tiến độ, đếm ngược và thử tiếp khi đến giờ.

Dữ liệu đăng nhập vẫn do trang Web xử lý. Hồ sơ QtWebEngine giữ cookie trong thư mục dữ liệu ứng dụng. Không tự xóa hồ sơ/cookie khi cập nhật. Đăng xuất trong Web nếu dùng chung máy.

## Kiểm thử và đóng gói

Từ thư mục SRT_Cuon_Chieu_Web_v1.1:

    python -B -m unittest -v test_engine test_web_connect test_native_chatgpt_bridge test_gemini_backend test_app_gemini test_gemini_web test_response_capture test_app_web_bridge test_web_state

Trên Linux không màn hình, đặt QT_QPA_PLATFORM=offscreen và QT_QUICK_BACKEND=software. Các kiểm thử DOM trong test_web_connect cần Node.js; nếu thiếu sẽ báo skipped. Kiểm thử Gemini dùng máy chủ HTTP cục bộ giả lập REST API: Unicode, header key, phân trang mô hình, lỗi key/quota, hủy yêu cầu, timeout, phản hồi bị chặn/cắt, thử lại ID sai, checkpoint và xuất SRT. Không cần API key thật và không phát sinh yêu cầu tới Google; các test này không xác nhận quota, chất lượng dịch hoặc quyền gọi mô hình của một tài khoản thật. Kiểm thử Web dùng HTML cục bộ trên QtWebEngine: Gemini có kiểm tra gửi một lần, không gửi bản nháp bị sửa, chỉ đọc model-response, tách hồ sơ/cửa sổ đăng nhập và dịch nhiều lô vào checkpoint. Chưa thay thế kiểm tra đăng nhập và dịch thực tế với ChatGPT/Gemini trên Windows.

Chạy build_exe_windows.bat trên Windows để build lại dist/SRT_Cuon_Chieu bằng PyInstaller. Spec thu thập ứng dụng, thư viện PySide6 và duy nhất binary ai_chatgpt đã kèm.

## Module và giới hạn dịch vụ

Chỉ khi kết nối/dịch bằng ChatGPT Web, app mới thử nạp module ai_chatgpt. Nhật ký báo rõ module có được nạp hay đang dùng bộ Web tích hợp. Module này cung cấp JavaScript gửi/đọc giao diện, không cấp tài khoản, hạn mức hay mô hình AI riêng. Dùng chế độ khách chỉ khi trang cho phép. Ứng dụng giữ cơ chế nhận biết thông báo chờ, lưu checkpoint và tiếp tục khi đến hạn; không bảo đảm ChatGPT Web không giới hạn hoặc không yêu cầu đăng nhập.

Bản này không nạp module ZK_API_WEB hoặc khởi chạy ZenKun Loader. Binary ai_chatgpt giữ nguyên SHA-256 e1f884cbed7b0a97d8e2d0f85e5e05016933c00aeb999e0d79842587df1be6a5. Kiểm thử Linux kiểm tra lớp tích hợp với API giả lập trên QtWebEngine; cần xác nhận binary thật trên Windows qua nhật ký khởi động.
