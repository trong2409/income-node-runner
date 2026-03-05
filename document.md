# Income Node Runner

Script quản lý nhiều node chạy song song, mỗi node sử dụng một proxy riêng.

## Cấu trúc thư mục

```
income-node-runner/
├── main.sh              # Script chính
├── proxies.txt          # Danh sách proxy (mỗi dòng 1 proxy)
├── properties.conf      # Config dùng chung cho tất cả node
├── source/              # Thư mục gốc được copy cho từng node
├── runtime/             # (tự động tạo) Chứa tất cả các node
│   ├── node-1/
│   ├── node-2/
│   └── ...
```

## Các file cấu hình

| File | Mô tả |
|------|--------|
| `proxies.txt` | Danh sách proxy, mỗi dòng một proxy. Dòng bắt đầu bằng `#` sẽ bị bỏ qua. Format: `protocol://username:password@ip:port` |
| `properties.conf` | File config dùng chung, sẽ được copy vào từng node khi setup |
| `source/` | Thư mục template gốc, được copy nguyên cho từng node |

## Lệnh

### `--setup-node`

```bash
./main.sh --setup-node
```

Tạo các thư mục `runtime/node-{i}` từ danh sách proxy trong `proxies.txt`:
- Tự động tạo thư mục `runtime/` nếu chưa có
- Đọc proxy từ `proxies.txt`, bỏ qua dòng comment (`#`) và dòng trống
- Với mỗi proxy thứ i, copy thư mục `source/` thành `runtime/node-{i}/`
- Ghi proxy tương ứng vào `runtime/node-{i}/proxies.txt`
- Copy `properties.conf` vào `runtime/node-{i}/properties.conf`
- Đặt `DEVICE_NAME='node-{i}'` trong `properties.conf` của từng node
- Nếu `runtime/node-{i}` đã tồn tại, sẽ bị xóa và tạo lại

### `--add-proxy <proxy> [proxy2 proxy3 ...]`

```bash
./main.sh --add-proxy socks5://user:pass@1.2.3.4:1080
./main.sh --add-proxy socks5://user:pass@1.2.3.4:1080 http://user:pass@5.6.7.8:8080
```

Thêm proxy mới và tạo node tương ứng:
- Thêm proxy vào cuối file `proxies.txt`
- Tạo node mới với số thứ tự tiếp theo (dựa trên số proxy hiện có trong `proxies.txt`)
- Hỗ trợ thêm nhiều proxy cùng lúc

### `--delete-node <num> [num2 num3 ...]`

```bash
./main.sh --delete-node 3          # Delete node-3
./main.sh --delete-node 1 3 5      # Delete node-1, node-3, node-5
```

Stop và xóa một hoặc nhiều node:
- Stop node trước (chạy `internetIncome.sh --delete`)
- Xóa dòng tương ứng trong `earnapp-links.txt`
- Xóa thư mục node

### `--delete-all`

```bash
./main.sh --delete-all
```

Stop và xóa tất cả thư mục `node-*` bên trong `runtime/`.

### `--start-node <num> [num2 num3 ...]`

```bash
./main.sh --start-node 3         # Start node-3
./main.sh --start-node 1 3 5     # Start node-1, node-3, node-5
```

Chạy `sudo bash internetIncome.sh --start` trong một hoặc nhiều node:
- Truyền một hoặc nhiều số thứ tự node
- Bỏ qua node không tồn tại hoặc không có `internetIncome.sh`

### `--start-all`

```bash
./main.sh --start-all
```

Chạy `sudo bash internetIncome.sh --start` trong tất cả các node trong `runtime/`.

> **Lưu ý**: Mỗi khi start node (cả `--start-node` và `--start-all`), nếu node có file `earnapp.txt`, nội dung sẽ tự động được ghi vào `earnapp-links.txt`.

### `--stop-node <num> [num2 num3 ...]`

```bash
./main.sh --stop-node 3          # Stop node-3
./main.sh --stop-node 1 3 5      # Stop node-1, node-3, node-5
```

Chạy `sudo bash internetIncome.sh --delete` trong một hoặc nhiều node:
- Truyền một hoặc nhiều số thứ tự node
- Bỏ qua node không tồn tại hoặc không có `internetIncome.sh`

### `--stop-all`

```bash
./main.sh --stop-all
```

Chạy `sudo bash internetIncome.sh --delete` trong tất cả các node trong `runtime/`.

### `--update-properties`

```bash
./main.sh --update-properties
```

Copy file `properties.conf` gốc ghi đè vào `properties.conf` của tất cả các node trong `runtime/`:
- Dùng khi chỉnh sửa `properties.conf` và muốn áp dụng cho tất cả node mà không cần chạy lại `--setup-node`

### `--collect-earnapp`

```bash
./main.sh --collect-earnapp
```

Thu thập link earnapp từ tất cả các node vào file `earnapp-links.txt`:
- Duyệt qua tất cả `runtime/node-*`, kiểm tra file `earnapp.txt` trong từng node
- Nếu có, ghi vào `earnapp-links.txt` theo format: `node-{i} : {nội dung earnapp.txt}`
- Hiển thị kết quả ra console sau khi thu thập xong
- File `earnapp.txt` được tạo tự động bởi `internetIncome.sh` khi EARNAPP=true trong `properties.conf`
