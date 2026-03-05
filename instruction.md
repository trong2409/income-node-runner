# Instruction for LLM Agents

Bạn đang làm việc với project **income-node-runner** — một hệ thống quản lý nhiều node chạy song song, mỗi node dùng một proxy riêng.

## Quy tắc bắt buộc

- **Luôn đọc `document.md`** trước khi thực hiện bất kỳ thay đổi nào. File này chứa mô tả đầy đủ cấu trúc thư mục, các file cấu hình, và danh sách lệnh hiện có.
- **Sau mỗi thay đổi, cập nhật `document.md`** để phản ánh đúng trạng thái hiện tại của project (thêm/sửa/xóa lệnh, thay đổi cấu trúc, v.v.).
- **Không sửa thư mục `source/`** trừ khi được yêu cầu rõ ràng. Đây là thư mục template gốc.
- **Không sửa trực tiếp các file bên trong `runtime/`**. Thư mục này được tạo tự động bởi script, mọi thay đổi sẽ bị ghi đè khi chạy `--setup-node`.

## Cấu trúc project

```
income-node-runner/
├── main.sh              # Script chính — tất cả logic nằm ở đây
├── proxies.txt          # Danh sách proxy (input của user)
├── properties.conf      # Config dùng chung cho tất cả node
├── source/              # Template gốc — KHÔNG SỬA
├── runtime/             # Tự động tạo — chứa node-1/, node-2/, ...
├── document.md          # Tài liệu tính năng — CẬP NHẬT SAU MỖI THAY ĐỔI
└── instruction.md       # File này — hướng dẫn cho LLM
```

## Cách hoạt động của `main.sh`

Script sử dụng cấu trúc `case` để xử lý các lệnh truyền qua argument:

```bash
./main.sh <command>
```

### Lệnh hiện có

| Lệnh | Hàm | Mô tả |
|-------|------|--------|
| `--setup-node` | `setup_nodes()` | Đọc `proxies.txt`, copy `source/` thành `runtime/node-{i}` cho mỗi proxy, ghi proxy và `properties.conf` vào từng node |
| `--add-proxy <proxy> [proxies...]` | `add_proxy()` | Thêm proxy vào `proxies.txt` và tạo node tương ứng |
| `--delete-node <num> [nums...]` | `delete_nodes()` | Stop và xóa một hoặc nhiều node, xóa earnapp link tương ứng |
| `--delete-all` | `delete_all_nodes()` | Stop và xóa tất cả node |
| `--start-node <num> [nums...]` | `run_nodes("start", "--start", ...)` | Start một hoặc nhiều node (chạy `internetIncome.sh --start`) |
| `--start-all` | `run_all_nodes("start", "--start")` | Start tất cả node |
| `--stop-node <num> [nums...]` | `run_nodes("stop", "--delete", ...)` | Stop một hoặc nhiều node (chạy `internetIncome.sh --delete`) |
| `--stop-all` | `run_all_nodes("stop", "--delete")` | Stop tất cả node |
| `--update-properties` | `update_properties()` | Copy `properties.conf` gốc ghi đè vào tất cả node |
| `--collect-earnapp` | `collect_earnapp()` | Thu thập `earnapp.txt` từ tất cả node vào `earnapp-links.txt` |

### Khi thêm lệnh mới

1. Viết hàm mới trong `main.sh`
2. Thêm case mới vào block `case "$1" in ... esac`
3. Thêm dòng mô tả vào phần help (case `*`)
4. Cập nhật `document.md` với mô tả lệnh mới

## Biến toàn cục trong `main.sh`

| Biến | Giá trị |
|------|---------|
| `SCRIPT_DIR` | Thư mục chứa `main.sh` |
| `SOURCE_DIR` | `$SCRIPT_DIR/source` |
| `PROXY_FILE` | `$SCRIPT_DIR/proxies.txt` |
| `PROPERTIES_FILE` | `$SCRIPT_DIR/properties.conf` |
| `RUNTIME_DIR` | `$SCRIPT_DIR/runtime` |

## Quy ước

- Tên lệnh: `--<action>-<target>` (ví dụ: `--setup-node`, `--delete-node`)
- Tên hàm: `<action>_<target>s()` (ví dụ: `setup_nodes()`, `delete_nodes()`)
- Các node nằm trong `runtime/node-{i}` với `i` bắt đầu từ 1
- Proxy format: `protocol://username:password@ip:port` hoặc `protocol://ip:port`
