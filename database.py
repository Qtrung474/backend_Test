import pymysql
import json
import os
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==============================================================================
# CẤU HÌNH KẾT NỐI MYSQL SERVER (Chạy trên cổng mặc định 3306)
# Bạn có thể chỉnh sửa trực tiếp user/password ở đây hoặc qua file .env
# ==============================================================================
MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "123456"),
    "database": os.getenv("MYSQL_DB", "jml_marketplace"),
    "charset": "utf8mb4",
    "autocommit": True,
}


class MySQLRow(dict):
    """Hỗ trợ truy cập cả theo tên cột row['title'] và chỉ số row[0] như SQLite Row."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class CursorWrapper:
    """Wrapper cho PyMySQL Cursor: Tự động chuyển đổi ký tự ? của SQLite sang %s của MySQL."""
    def __init__(self, cursor):
        self.cur = cursor

    def execute(self, sql, args=None):
        sql_converted = sql.replace("?", "%s")
        return self.cur.execute(sql_converted, args)

    def executemany(self, sql, args=None):
        sql_converted = sql.replace("?", "%s")
        return self.cur.executemany(sql_converted, args)

    def fetchone(self):
        row = self.cur.fetchone()
        return MySQLRow(row) if row else None

    def fetchall(self):
        rows = self.cur.fetchall()
        return [MySQLRow(r) for r in rows]

    def __getattr__(self, name):
        return getattr(self.cur, name)


class ConnectionWrapper:
    """Wrapper cho PyMySQL Connection."""
    def __init__(self, conn):
        self.conn = conn

    def cursor(self):
        return CursorWrapper(self.conn.cursor(pymysql.cursors.DictCursor))

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def __getattr__(self, name):
        return getattr(self.conn, name)


def ensure_database_exists():
    """Tự động tạo database MySQL 'jml_marketplace' nếu chưa có."""
    try:
        conn = pymysql.connect(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            charset="utf8mb4",
            autocommit=True
        )
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_CONFIG['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn.close()
    except Exception as e:
        print("Cảnh báo kiểm tra database:", e)


def get_db_connection():
    """Tạo kết nối tới cơ sở dữ liệu MySQL Server (127.0.0.1:3306)."""
    ensure_database_exists()
    conn = pymysql.connect(**MYSQL_CONFIG)
    return ConnectionWrapper(conn)


def init_db(seed=False):
    """Khởi tạo các bảng MySQL (products, customers, orders, order_items, shops)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Bảng SHOPS (Cửa hàng / Sellers)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shops (
        shop_key VARCHAR(50) PRIMARY KEY,
        id_display VARCHAR(50) NOT NULL,
        initials VARCHAR(10) NOT NULL,
        name VARCHAR(255) NOT NULL,
        badge VARCHAR(50) NOT NULL,
        badge_class VARCHAR(100) NOT NULL,
        meta TEXT NOT NULL,
        gmv VARCHAR(50) NOT NULL,
        fee VARCHAR(50) NOT NULL,
        product_count VARCHAR(50) NOT NULL,
        rating VARCHAR(50) NOT NULL,
        status VARCHAR(50) DEFAULT 'active'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # 2. Bảng PRODUCTS (Sản phẩm trên sàn)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INT AUTO_INCREMENT PRIMARY KEY,
        category VARCHAR(100) NOT NULL,
        title VARCHAR(255) NOT NULL,
        price BIGINT NOT NULL,
        original_price BIGINT NOT NULL,
        discount VARCHAR(20) NOT NULL,
        rating FLOAT DEFAULT 5.0,
        sold INT DEFAULT 0,
        total_stock INT DEFAULT 100,
        images_json TEXT NOT NULL,
        angles_json TEXT NOT NULL,
        exclusive VARCHAR(100) DEFAULT '',
        shop_name VARCHAR(255) DEFAULT 'AB Technology Ltd',
        is_flash_sale TINYINT(1) DEFAULT 0,
        status VARCHAR(50) DEFAULT 'approved'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # 3. Bảng CUSTOMERS (Khách hàng / Người mua)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        cust_key VARCHAR(50) PRIMARY KEY,
        id_display VARCHAR(50) NOT NULL,
        name VARCHAR(255) NOT NULL,
        phone VARCHAR(50) NOT NULL UNIQUE,
        email VARCHAR(255) NOT NULL,
        avatar TEXT NOT NULL,
        `rank` VARCHAR(50) DEFAULT 'Đồng',
        rank_badge VARCHAR(100) NOT NULL,
        joined VARCHAR(50) NOT NULL,
        orders_count INT DEFAULT 0,
        total_spent VARCHAR(50) DEFAULT '0 ₫',
        status VARCHAR(50) DEFAULT 'Hoạt động',
        status_badge VARCHAR(100) DEFAULT 'bg-emerald-50 text-emerald-600',
        address TEXT NOT NULL,
        is_banned TINYINT(1) DEFAULT 0
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # 4. Bảng ORDERS (Đơn hàng Trung gian & Quỹ giữ hộ Escrow)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_key VARCHAR(50) PRIMARY KEY,
        id_display VARCHAR(50) NOT NULL,
        escrow_badge VARCHAR(100) NOT NULL,
        escrow_class VARCHAR(100) NOT NULL,
        time_info TEXT NOT NULL,
        shop_name VARCHAR(255) NOT NULL,
        shop_address TEXT NOT NULL,
        buyer_name VARCHAR(255) NOT NULL,
        buyer_phone VARCHAR(50) DEFAULT '',
        buyer_address TEXT NOT NULL,
        total VARCHAR(50) NOT NULL,
        numeric_total BIGINT DEFAULT 0,
        fee VARCHAR(50) NOT NULL,
        net VARCHAR(50) NOT NULL,
        status VARCHAR(50) DEFAULT 'escrow',
        created_at VARCHAR(50) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # 5. Bảng ORDER_ITEMS (Chi tiết từng mặt hàng trong đơn)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS order_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        order_key VARCHAR(50) NOT NULL,
        name VARCHAR(255) NOT NULL,
        variant VARCHAR(255) NOT NULL,
        price VARCHAR(50) NOT NULL,
        qty VARCHAR(50) NOT NULL,
        subtotal VARCHAR(50) NOT NULL,
        FOREIGN KEY (order_key) REFERENCES orders (order_key) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # 6. Bảng USERS (Tài khoản Đăng nhập cho Khách hàng, Chủ Shop, Admin)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100) NOT NULL UNIQUE,
        password VARCHAR(255) NOT NULL,
        role VARCHAR(20) NOT NULL,
        full_name VARCHAR(255) NOT NULL,
        phone VARCHAR(50) DEFAULT '',
        email VARCHAR(255) DEFAULT '',
        address TEXT,
        shop_key VARCHAR(50) DEFAULT '',
        shop_name VARCHAR(255) DEFAULT '',
        cust_key VARCHAR(50) DEFAULT '',
        created_at VARCHAR(50) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # Tạo sẵn tài khoản Super Admin mặc định nếu chưa có (admin / 123456)
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin';")
    if cursor.fetchone()[0] == 0:
        now_str = datetime.now().strftime("%d/%m/%Y")
        cursor.execute("""
            INSERT INTO users (username, password, role, full_name, phone, email, address, created_at)
            VALUES ('admin', '123456', 'admin', 'Hoàng Nam (Super Admin)', '0900000000', 'admin@jmlstore.vn', 'Trụ sở JML Store', ?);
        """, (now_str,))

    conn.commit()
    if seed:
        seed_initial_data(conn)
    conn.close()


def seed_initial_data(conn):
    """Nạp dữ liệu mẫu ban đầu nếu được yêu cầu."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM shops;")
    if cursor.fetchone()[0] == 0:
        shops_data = [
            ("SH-102", "#SH-102", "AB", "AB Technology Ltd", "JML MALL", "bg-danger-500 text-white", "Mã Shop: #SH-102 • Quận 1, TP.HCM", "$312,400.00", "$21,868.00", "142 mặt hàng", "★ 4.9 / 5.0", "active"),
            ("SH-418", "#SH-418", "ZF", "Zara Fashion Store", "YÊU THÍCH+", "bg-warning-500 text-white", "Mã Shop: #SH-418 • Quận Hoàn Kiếm, Hà Nội", "$198,200.00", "$13,874.00", "98 mặt hàng", "★ 4.8 / 5.0", "active"),
            ("SH-015", "#SH-015", "CF", "Canon Flagship Store", "JML MALL", "bg-danger-500 text-white", "Mã Shop: #SH-015 • Quận 3, TP.HCM", "$164,500.00", "$11,515.00", "64 mặt hàng", "★ 4.9 / 5.0", "active"),
            ("SH-889", "#SH-889", "SM", "SoundMax Audio Shop", "TIÊU CHUẨN", "bg-neutral-200 text-neutral-700", "Mã Shop: #SH-889 • Hải Châu, Đà Nẵng", "$42,800.00", "$2,996.00", "52 mặt hàng", "★ 4.5 / 5.0", "active")
        ]
        cursor.executemany("INSERT INTO shops VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", shops_data)
        conn.commit()
