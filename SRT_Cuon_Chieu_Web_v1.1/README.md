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

### v1.2.3: Nút gửi chưa sẵn sàng sau nhiều lô

Trước đây ứng dụng chỉ kiểm tra nút gửi một lần, 350 ms sau khi điền prompt. Bản này chờ nút gửi tối đa 30 giây (hoặc thời gian chờ Web nếu thấp hơn), kiểm tra lại mỗi 500 ms và chỉ bấm một lần khi nút được bật. Không điền lại prompt hoặc gửi lại khi đã bấm gửi. Thay đổi nội dung ô chat sẽ dừng để tránh gửi nhầm; nút submit ngoài form soạn chat không được dùng thay nút gửi.

Nhật ký phân biệt “nút bị vô hiệu hóa”, “chưa tìm thấy nút” và “đang tạo câu trả lời trước”, không tự kết luận là thiếu đăng nhập. Hết thời gian chờ thì dừng, giữ checkpoint. Sau cập nhật, mở lại cùng file SRT để phục hồi tiến độ rồi bắt đầu dịch phần còn thiếu. Thời gian chờ nút gửi này độc lập với thời gian nghỉ giữa các lô và không bỏ qua giới hạn của ChatGPT.

### v1.2.4: Giữ phản hồi hợp lệ trước khi giao diện thay đổi

Nhật ký thực tế có trường hợp JSON chỉ xuất hiện trong một lần đọc khi Web còn đang tạo, rồi biến mất ở lần đọc kế tiếp. Trước đây ứng dụng chờ phản hồi ổn định/hết streaming mới kiểm tra nên có thể mất phản hồi này.

Bản này kiểm tra JSON ngay khi nhìn thấy: phải đủ đúng ID của toàn bộ lô, không trùng/thừa ID, đúng kiểu dữ liệu và số dòng từng cue. Khi đạt, ứng dụng điền bảng và ghi checkpoint ngay, nhưng chưa gửi lô sau cho đến khi Web hết tạo câu trả lời. Nếu DOM mất phản hồi sau đó, tiếp tục bằng bản dịch hợp lệ đã giữ. Nút Stop đang hiển thị vẫn ngăn gửi lô mới. Dừng phiên giữ bản dịch đã lưu và xóa dữ liệu lô chờ để không dùng nhầm cho lần chạy sau.

Không khôi phục từ JSON cắt dở, thiếu ID hoặc sai số dòng. Bản sửa không bảo đảm ChatGPT luôn trả lời và không thay đổi giới hạn/đăng nhập của dịch vụ. Kiểm thử tái hiện chuỗi một phản hồi đang tạo → không còn phản hồi, xác minh file checkpoint và việc tiếp tục đúng các ID chưa dịch.

### v1.2.5: Đã đăng nhập nhưng báo không thấy ô chat

Các bước kiểm tra kết nối, điền prompt và gửi dùng chung một bộ nhận diện editor: textarea hoặc contenteditable thực sự có thể nhập, kể cả editor không có ID hoặc nằm trong wrapper. Loại editor ẩn, disabled, readOnly và contenteditable=false. Đối chiếu nội dung bỏ qua khác biệt xuống dòng trống do trình soạn thảo HTML tạo ra, không thay đổi JSON phụ đề gửi đi.

Trước mỗi lô, chờ editor theo thời gian chờ Web đã đặt, kiểm tra lại mỗi 750 ms thay vì dừng sau lần dò đầu tiên. Hết hạn thì báo chưa thấy ô chat có thể nhập, không tự suy luận cần đăng nhập. Không tự tải lại trang, mở hội thoại mới hay gửi lại lô trong lúc chờ. Bấm Dừng hủy các lượt dò còn chờ; checkpoint được giữ nguyên.

### v1.2.6: Nhận biết thông báo yêu cầu chờ của ChatGPT

Ứng dụng nhận diện thông báo “We're doing a quick check to keep ChatGPT reliable. Try again after H:MM AM/PM” trước khi nhập/gửi và trong khi nhận phản hồi. Khi đọc được giờ chờ hợp lệ, giữ checkpoint, hiển thị đếm ngược và không gửi thêm cho đến thời điểm đó. Giờ được tính theo múi giờ trình duyệt/máy Windows; cần để đồng hồ hệ thống chính xác.

Để ứng dụng mở nếu muốn tự tiếp tục. Đến hạn, kiểm tra lại ô chat và chỉ dịch các ID còn thiếu. Nếu dịch vụ vẫn chưa cho gửi hoặc đưa ra giờ chờ mới, ứng dụng tiếp tục xử lý theo thông báo thực tế; đến giờ không bảo đảm dịch vụ đã sẵn sàng. Bấm Dừng hoặc đóng ứng dụng sẽ hủy tự tiếp tục. Nếu không đọc được giờ, ứng dụng dừng và yêu cầu xem thông báo thay vì đoán thời gian.

Đây là cơ chế chờ theo điều kiện dịch vụ, không phải dùng ChatGPT không giới hạn. Không đổi IP, tài khoản hoặc phiên để né giới hạn, không tự vượt xác minh. Kiểm thử cục bộ gồm giờ AM/PM, thông báo đã hết hạn, qua nửa đêm, nhận diện DOM thật, không nhầm lời người dùng/khối mã, không gửi trong lúc chờ và tiếp tục khi đến hạn.

Thông báo yêu cầu chờ có thể nằm bên trong form soạn chat. Bộ nhận diện vẫn đọc phần thông báo này, đồng thời loại nội dung textarea/contenteditable để không nhầm văn bản đang nhập với yêu cầu của dịch vụ.

### v1.3.0: Dùng module ai_chatgpt do người dùng cung cấp

Đã kèm `ai_chatgpt.cp312-win_amd64.pyd` nguyên bản (SHA-256 `e1f884cbed7b0a97d8e2d0f85e5e05016933c00aeb999e0d79842587df1be6a5`). `run_windows.bat` yêu cầu Python **3.12 64-bit**. Trên Windows đúng phiên bản, ứng dụng nạp `ChatGPTHandler`, dùng `get_send_js` và `get_read_js`. Nhật ký lúc mở ứng dụng phải ghi **“Đang dùng module ai_chatgpt.pyd do người dùng cung cấp.”** Nếu không nạp được, nhật ký ghi rõ lý do và dùng bộ Web tích hợp; không coi đó là đã chạy module.

Lớp tích hợp chuyển chuỗi JSON `text/is_generating` của module sang giao thức hiện có, giữ bộ đọc dự phòng và các kiểm tra ID/số dòng/checkpoint. Chỉ gọi thao tác gửi của module một lần, chờ ô nhập được xóa để xác nhận thao tác rồi đọc phản hồi; không bấm thêm nút gửi của bộ tích hợp. Đóng/Dừng hủy callback gửi trễ còn chờ. Nội dung phụ đề được truyền qua biến JSON thay vì chèn trực tiếp vào template literal của module.

`build_exe_windows.bat` dùng Python 3.12 và spec kèm binary vào bản đóng gói. Không nén UPX để giữ đúng checksum. Bản `.exe` cũ không tự nhận thay đổi: chạy mã nguồn hoặc build lại trên Windows.

Linux và Python khác phiên bản vẫn dùng bộ Web tích hợp để phát triển. Kiểm thử bằng `python -B -m unittest -v test_engine test_web_connect test_native_chatgpt_bridge test_app_web_bridge`. Kiểm thử Linux xác minh định dạng/checksum binary, điều kiện nạp và lớp tích hợp bằng API giả lập trên QtWebEngine; chưa thực thi binary Windows hoặc xác minh bản đóng gói `.exe`. Module này không loại bỏ giới hạn hoặc yêu cầu đăng nhập do ChatGPT áp dụng.

### v1.3.1: Giữ JSON xuất hiện giữa hai lần đọc định kỳ

Ngoài việc đọc định kỳ qua module `.pyd`, ứng dụng cài bộ theo dõi thay đổi DOM trước khi điền/gửi lô. Bộ này chỉ giữ JSON đầy đủ đúng các ID và số dòng của lô hiện tại; không giữ JSON cắt dở, prompt, phản hồi sai lô hoặc bản dịch cũ có sẵn trước lúc gửi. Khi phản hồi bị xóa giữa hai lần đọc, lần đọc tiếp theo vẫn có thể nhập bản hợp lệ đã giữ. Python tiếp tục kiểm tra lại trước khi ghi checkpoint.

Trong dòng “Cấu trúc Web”, `captureInstalled` cho biết bộ theo dõi còn tồn tại trong trang, `capturedReplies` cho biết số bản JSON hợp lệ đã bắt được cho lô này. Dừng/đóng ứng dụng, kết thúc lô hoặc chờ giới hạn sẽ ngắt bộ theo dõi; ID phiên ngăn dùng nhầm dữ liệu lô trước. Thông báo hết thời gian chờ chỉ rõ chưa nhận JSON mới hợp lệ, thay vì kết luận module chưa được nạp hoặc chưa đăng nhập.

Kiểm thử bổ sung: `python -B -m unittest -v test_response_capture` dùng QtWebEngine thật với JSON xuất hiện rồi bị xóa trước lần đọc. Cơ chế này không thể khôi phục nội dung chưa từng có JSON đầy đủ trong DOM, nội dung mất trước khi bộ theo dõi được gọi, hoặc phản hồi mất do tải lại cả trang trước lần đọc tiếp theo. Không tự gửi lại yêu cầu để tránh dịch trùng hay gửi thêm khi dịch vụ yêu cầu chờ.

### v1.3.2: Chờ nút gửi cho module ai_chatgpt

Lớp tích hợp trước đây cho module gọi thao tác gửi sau 400 ms, nhưng nếu nút chưa sẵn sàng tại thời điểm đó thì chỉ chờ xác nhận đến hết 30 giây. Bản này giữ nguyên file `.pyd`, chuẩn bị lô một lần và chờ nút gửi thực sự được bật trước khi gọi callback gửi của module. Kiểm tra mỗi 500 ms, giới hạn tối đa 30 giây; không dùng nút submit ngoài form soạn chat và không gọi lại hàm gửi sau khi đã bấm.

Việc xác nhận dùng cả ô nhập đã xóa sau thao tác và số lần xuất hiện của chính prompt mới trong vùng hội thoại (loại trừ nội dung ô soạn thảo). Vì vậy prompt còn trong ô nhập không tự động bị coi là chưa gửi nếu đã thấy yêu cầu mới được đăng. Phản hồi/yêu cầu cũ có sẵn trước thao tác không được tính làm xác nhận. Dừng, đóng hoặc bắt đầu chờ giới hạn sẽ hủy callback còn chờ. Nhật ký ghi lý do chờ và cách xác nhận để phân biệt nút chưa bật với đã bấm nhưng chưa được trang tiếp nhận.

Kiểm thử dùng giao thức module giả lập trên QtWebEngine: nút chỉ bật sau 1,2–2,2 giây và trường hợp yêu cầu đã được đăng nhưng draft chưa xóa. Chưa xác minh trực tiếp với binary trong phiên Windows của người dùng. Nếu trang luôn vô hiệu hóa nút gửi hoặc không nhận yêu cầu, ứng dụng vẫn dừng và giữ tiến độ; bản sửa không bỏ qua yêu cầu chờ của dịch vụ.

### v1.3.3: Không cuộn/chọn toàn trang khi dùng module

Bộ đọc của module có thao tác tự cuộn đến câu trả lời mỗi lần đọc. Lớp tích hợp bỏ thao tác này để không tự thay đổi vị trí nhìn của người dùng. Bộ gửi được giới hạn vào editor thực sự có thể nhập: thay lệnh selectAll toàn trang bằng Range chỉ bao nội dung ô chat, và kiểm tra focus trước khi chèn văn bản. File `.pyd` gốc vẫn giữ nguyên.

Nút **Hiện ô chat** dừng phiên hiện tại, rồi cuộn/focus ô nhập nếu nó vẫn tồn tại. Nếu trang không còn editor, ứng dụng báo rõ và hướng dẫn nhấn **⟳**; không chèn ô nhập giả hoặc tự sửa giao diện ChatGPT. Tải lại Web cũng dừng phiên trước để hủy callback gửi cũ, giữ checkpoint và dùng lại hồ sơ trình duyệt. Sau khi ô chat đã hiện, bấm Bắt đầu để tiếp tục các ID còn thiếu.

Khi chưa thấy editor, trạng thái kết nối chuyển sang chờ thay vì vẫn báo sẵn sàng. Không thể xác nhận nguyên nhân biến mất editor trên máy Windows chỉ từ ảnh; nếu ChatGPT không render ô nhập hoặc đang yêu cầu chờ/xác minh thì cần xử lý trạng thái thực tế của dịch vụ.

### v1.4.0: Phục hồi lỗi Web tạm thời có giới hạn

Tùy chọn **Tự phục hồi khi Web chậm** bật mặc định. Khi kiểm tra ô chat bị lỗi, editor tạm biến mất, nút gửi chưa bật hoặc phản hồi đến muộn, ứng dụng giữ checkpoint và thử phục hồi sau 5 giây, tối đa 3 lần cho mỗi giai đoạn của một lô. Có thể tắt tùy chọn để dừng ngay như trước.

Phục hồi đọc phản hồi chỉ đọc lại lô đang chờ, không tạo prompt mới hay gửi lại yêu cầu. Với module native, chỉ tiếp tục callback chờ nút của chính yêu cầu hiện tại khi chưa bấm gửi; nếu đã bấm thì chỉ kiểm tra xác nhận. Bộ đếm callback bảo đảm không bấm lần hai. Dừng/đóng cửa sổ hoặc sang lô mới hủy các lần phục hồi còn chờ. Giới hạn chờ phản hồi tối đa 15 phút vẫn áp dụng; thông báo yêu cầu chờ của ChatGPT được xử lý riêng.

Nhật ký ghi rõ giai đoạn và số lần phục hồi. Hết ngân sách thử lại, JSON vẫn sai hoặc dịch vụ yêu cầu hành động thủ công thì ứng dụng vẫn dừng và giữ tiến độ. Đây là tăng khả năng chịu lỗi tạm thời, không phải bảo đảm ChatGPT Web chạy không lỗi hoặc không giới hạn. Quy trình dài qua API có cấu trúc hoặc mô hình cục bộ có thể giảm phụ thuộc DOM; backend hiện tại vẫn dùng ChatGPT Web theo lựa chọn của người dùng.
