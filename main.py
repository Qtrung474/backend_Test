import json
import os
import random
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

try:
    from .database import get_db_connection, init_db, seed_initial_data
    from .schemas import (
        ProductCreate, OrderCreate, FreezeOrderRequest, CustomerCreate,
        LoginRequest, RegisterRequest, ShopUpdateRequest
    )
except ImportError:
    from database import get_db_connection, init_db, seed_initial_data
    from schemas import (
        ProductCreate, OrderCreate, FreezeOrderRequest, CustomerCreate,
        LoginRequest, RegisterRequest, ShopUpdateRequest
    )

app = FastAPI(
    title="JML Store Multi-Vendor Marketplace API",
    description="Hệ thống Backend FastAPI + SQL quản lý Sàn TMĐT trung gian (Sản phẩm, Đơn hàng Escrow, Khách hàng, Cửa hàng)",
    version="1.0.0",
)

# Cấu hình CORS cho phép Frontend (Live Server 5500 hoặc bất kỳ cổng nào) gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


# ==============================================================================
# 1. API SẢN PHẨM (DÀNH CHO CẢ TRANG USER VÀ TRANG ADMIN)
# ==============================================================================
@app.get("/api/products")
def get_all_products():
    """Lấy danh sách sản phẩm Flash Sale và Gợi ý hôm nay từ SQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM products
        WHERE status = 'approved'
        ORDER BY id DESC;
    """)
    rows = cursor.fetchall()
    conn.close()

    flash_products = []
    recommend_products = []

    for r in rows:
        item = {
            "id": r["id"],
            "category": r["category"],
            "title": r["title"],
            "price": r["price"],
            "originalPrice": r["original_price"],
            "discount": r["discount"],
            "rating": r["rating"],
            "sold": r["sold"],
            "soldCount": r["sold"],
            "totalStock": r["total_stock"],
            "images": json.loads(r["images_json"]),
            "angles": json.loads(r["angles_json"]),
            "exclusive": r["exclusive"] or "Bán Chạy",
            "shopName": r["shop_name"],
        }
        if r["is_flash_sale"] == 1:
            flash_products.append(item)
        else:
            recommend_products.append(item)

    # Sắp xếp flash_products theo id tăng dần để giữ thứ tự chuẩn
    flash_products.sort(key=lambda x: x["id"])

    return {
        "flash_products": flash_products,
        "recommend_products": recommend_products,
    }


@app.get("/api/admin/products/pending")
def get_pending_products():
    """Lấy danh sách sản phẩm đang chờ Admin kiểm duyệt."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM products
        WHERE status = 'pending'
        ORDER BY id DESC;
    """)
    rows = cursor.fetchall()
    conn.close()

    pending_list = []
    for r in rows:
        imgs = json.loads(r["images_json"]) if r["images_json"] else []
        pending_list.append({
            "id": r["id"],
            "title": r["title"],
            "category": r["category"],
            "price": r["price"],
            "price_formatted": f"{int(r['price']):,} ₫".replace(",", "."),
            "shop_name": r["shop_name"],
            "image": imgs[0] if imgs else "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=800&q=80",
            "stock": r["total_stock"],
            "status": r["status"]
        })
    return {"pending_products": pending_list}


@app.put("/api/admin/products/{product_id}/approve")
def approve_pending_product(product_id: int):
    """Admin duyệt đưa sản phẩm lên kệ sàn."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET status = 'approved' WHERE id = ?;", (product_id,))
    conn.commit()
    conn.close()
    return {"message": f"Đã duyệt sản phẩm #{product_id} lên kệ sàn thành công!"}


@app.put("/api/admin/products/{product_id}/reject")
def reject_pending_product(product_id: int):
    """Admin từ chối sản phẩm của Shop."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET status = 'rejected' WHERE id = ?;", (product_id,))
    conn.commit()
    conn.close()
    return {"message": f"Đã từ chối sản phẩm #{product_id}."}


@app.post("/api/seller/products")
def seller_submit_product(payload: ProductCreate):
    """Chủ Shop gửi đăng sản phẩm mới (chuyển sang trạng thái 'pending' chờ Admin duyệt)."""
    orig_price = payload.original_price or int(payload.price * 1.2)
    discount_pct = max(1, round((1 - payload.price / max(orig_price, 1)) * 100))
    discount_str = f"-{discount_pct}%"

    img_url = payload.image.strip() if payload.image and payload.image.strip() else "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=800&q=80"
    images = [img_url, img_url, img_url, img_url]
    angles = ["Chính diện", "Góc nghiêng", "Cận cảnh", "Thực tế"]

    conn = get_db_connection()
    cursor = conn.cursor()

    clean_shop_name = (payload.shop_name or "JML Official Store").strip()
    cursor.execute("SELECT shop_key FROM shops WHERE name = ?;", (clean_shop_name,))
    if not cursor.fetchone():
        sh_key = f"SH-{random.randint(100, 999)}"
        words = [w[0].upper() for w in clean_shop_name.split() if w]
        initials = "".join(words[:2]) if words else "SH"
        cursor.execute("""
            INSERT INTO shops (shop_key, id_display, initials, name, badge, badge_class, meta, gmv, fee, product_count, rating, status)
            VALUES (?, ?, ?, ?, 'JML MALL', 'bg-danger-500 text-white', ?, '0 ₫', '0 ₫', '1 sản phẩm', '★ 5.0 (Mới)', 'active');
        """, (sh_key, f"#{sh_key}", initials, clean_shop_name, f"Mã Shop: #{sh_key} • Đối tác chính thức trên Sàn"))

    cursor.execute("""
        INSERT INTO products (category, title, price, original_price, discount, rating, sold, total_stock, images_json, angles_json, exclusive, shop_name, is_flash_sale, status)
        VALUES (?, ?, ?, ?, ?, 5.0, 0, ?, ?, ?, 'Chờ Duyệt', ?, ?, 'pending');
    """, (
        payload.category,
        payload.title,
        payload.price,
        orig_price,
        discount_str,
        payload.stock or 50,
        json.dumps(images),
        json.dumps(angles),
        clean_shop_name,
        1 if payload.is_flash_sale else 0
    ))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "message": f"Sản phẩm '{payload.title}' đã được gửi và đang chờ Admin kiểm duyệt!",
        "product_id": new_id,
        "status": "pending"
    }


@app.post("/api/admin/products")
def create_or_approve_product(payload: ProductCreate):
    """Admin thêm mới hoặc duyệt sản phẩm hiển thị lên trang User (Lưu vào SQL)."""
    orig_price = payload.original_price or int(payload.price * 1.2)
    discount_pct = max(1, round((1 - payload.price / max(orig_price, 1)) * 100))
    discount_str = f"-{discount_pct}%"

    images = [payload.image, payload.image, payload.image, payload.image]
    angles = ["Chính diện", "Góc nghiêng", "Cận cảnh", "Thực tế"]

    conn = get_db_connection()
    cursor = conn.cursor()

    # Tự động đảm bảo Shop tồn tại trong bảng shops nếu chưa có
    clean_shop_name = (payload.shop_name or "JML Official Store").strip()
    cursor.execute("SELECT shop_key FROM shops WHERE name = ?;", (clean_shop_name,))
    if not cursor.fetchone():
        sh_key = f"SH-{random.randint(100, 999)}"
        words = [w[0].upper() for w in clean_shop_name.split() if w]
        initials = "".join(words[:2]) if words else "SH"
        cursor.execute("""
            INSERT INTO shops (shop_key, id_display, initials, name, badge, badge_class, meta, gmv, fee, product_count, rating, status)
            VALUES (?, ?, ?, ?, 'JML MALL', 'bg-danger-500 text-white', ?, '0 ₫', '0 ₫', '1 sản phẩm', '★ 5.0 (Mới)', 'active');
        """, (sh_key, f"#{sh_key}", initials, clean_shop_name, f"Mã Shop: #{sh_key} • Đối tác chính thức trên Sàn"))

    cursor.execute("""
        INSERT INTO products (category, title, price, original_price, discount, rating, sold, total_stock, images_json, angles_json, exclusive, shop_name, is_flash_sale, status)
        VALUES (?, ?, ?, ?, ?, 5.0, 0, ?, ?, ?, 'Mới Lên Kệ', ?, ?, 'approved');
    """, (
        payload.category,
        payload.title,
        payload.price,
        orig_price,
        discount_str,
        payload.stock or 100,
        json.dumps(images),
        json.dumps(angles),
        clean_shop_name,
        1 if payload.is_flash_sale else 0
    ))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "message": f"Đã lưu sản phẩm '{payload.title}' vào cơ sở dữ liệu MySQL!",
        "product": {
            "id": new_id,
            "category": payload.category,
            "title": payload.title,
            "price": payload.price,
            "originalPrice": orig_price,
            "discount": discount_str,
            "rating": 5.0,
            "soldCount": 0,
            "totalStock": payload.stock or 100,
            "shopName": clean_shop_name,
            "images": images,
            "angles": angles,
        }
    }


@app.delete("/api/products/{product_id}")
def delete_product_by_id(product_id: int):
    """Chủ Shop hoặc Admin xóa sản phẩm theo ID khỏi MySQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?;", (product_id,))
    conn.commit()
    conn.close()
    return {"message": f"Đã xóa sản phẩm #{product_id} khỏi MySQL Database."}


@app.delete("/api/admin/products")
def delete_product(title: str = Query(..., description="Tên sản phẩm cần gỡ bỏ")):
    """Admin khóa & xóa vĩnh viễn sản phẩm khỏi SQL Database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE title LIKE ?;", (f"%{title}%",))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()

    return {
        "message": f"Đã xóa sản phẩm '{title}' khỏi SQL Database ({deleted_rows} bản ghi)."
    }


# ==============================================================================
# 2. API ĐƠN HÀNG & QUỸ GIỮ HỘ ESCROW (USER ĐẶT HÀNG <-> ADMIN QUẢN LÝ)
# ==============================================================================
@app.get("/api/admin/orders")
def get_all_orders():
    """Lấy toàn bộ danh sách đơn hàng kèm sản phẩm trong từng đơn từ SQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY order_key DESC;")
    order_rows = cursor.fetchall()

    orders_dict = {}
    for o in order_rows:
        cursor.execute("SELECT * FROM order_items WHERE order_key = ?;", (o["order_key"],))
        items_rows = cursor.fetchall()
        items = [
            {
                "name": item["name"],
                "variant": item["variant"],
                "price": item["price"],
                "qty": item["qty"],
                "subtotal": item["subtotal"],
            }
            for item in items_rows
        ]
        orders_dict[o["order_key"]] = {
            "id": o["id_display"],
            "key": o["order_key"],
            "escrowBadge": o["escrow_badge"],
            "escrowClass": o["escrow_class"],
            "time": o["time_info"],
            "shopName": o["shop_name"],
            "shopAddress": o["shop_address"],
            "buyerName": o["buyer_name"],
            "buyerPhone": o["buyer_phone"],
            "buyerAddress": o["buyer_address"],
            "total": o["total"],
            "numericTotal": o["numeric_total"],
            "fee": o["fee"],
            "net": o["net"],
            "status": o["status"],
            "items": items,
        }

    conn.close()
    return {"orders": orders_dict}


@app.get("/api/user/orders")
def get_user_orders(phone: str = Query(""), name: str = Query("")):
    """Lấy danh sách lịch sử đơn hàng của người dùng theo SĐT hoặc Tên."""
    conn = get_db_connection()
    cursor = conn.cursor()

    clean_phone = phone.strip()
    clean_name = name.strip()

    if clean_phone and clean_name:
        cursor.execute("""
            SELECT * FROM orders 
            WHERE buyer_phone = ? OR buyer_name LIKE ? 
            ORDER BY order_key DESC;
        """, (clean_phone, f"%{clean_name}%"))
    elif clean_phone:
        cursor.execute("SELECT * FROM orders WHERE buyer_phone = ? ORDER BY order_key DESC;", (clean_phone,))
    elif clean_name:
        cursor.execute("SELECT * FROM orders WHERE buyer_name LIKE ? ORDER BY order_key DESC;", (f"%{clean_name}%",))
    else:
        # Nếu chưa đăng nhập / chưa có thông tin, trả về danh sách 10 đơn gần nhất
        cursor.execute("SELECT * FROM orders ORDER BY order_key DESC LIMIT 10;")

    rows = cursor.fetchall()
    orders_list = []
    for o in rows:
        cursor.execute("SELECT * FROM order_items WHERE order_key = ?;", (o["order_key"],))
        items_rows = cursor.fetchall()
        items = [
            {
                "name": it["name"],
                "variant": it["variant"],
                "price": it["price"],
                "qty": it["qty"],
                "subtotal": it["subtotal"]
            }
            for it in items_rows
        ]
        orders_list.append({
            "order_key": o["order_key"],
            "id_display": o["id_display"],
            "buyer_name": o["buyer_name"],
            "buyer_phone": o["buyer_phone"],
            "buyer_address": o["buyer_address"],
            "shop_name": o["shop_name"],
            "shop_address": o["shop_address"],
            "total": o["total"],
            "numeric_total": o["numeric_total"],
            "fee": o["fee"],
            "net": o["net"],
            "status": o["status"],
            "escrow_badge": o["escrow_badge"],
            "escrow_class": o["escrow_class"],
            "time_info": o["time_info"],
            "created_at": o["created_at"],
            "items": items
        })

    conn.close()
    return {"orders": orders_list}


@app.post("/api/orders")
def create_order(payload: OrderCreate):
    """Khách hàng đặt hàng từ trang User -> Kiểm tra khóa tài khoản -> Lưu vào SQL."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Kiểm tra xem khách hàng (theo SĐT hoặc Tên) có đang bị Admin khóa trong SQL không
    cursor.execute("""
        SELECT * FROM customers
        WHERE (phone = ? OR name = ?) AND is_banned = 1;
    """, (payload.buyer_phone.strip(), payload.buyer_name.strip()))
    banned_cust = cursor.fetchone()

    if banned_cust:
        conn.close()
        raise HTTPException(
            status_code=403,
            detail=f"Tài khoản / Số điện thoại ({payload.buyer_phone}) đã bị Ban Quản Trị Sàn khóa do vi phạm chính sách!"
        )

    # 2. Tạo mã đơn hàng mới
    order_num = random.randint(1000, 9999)
    order_key = f"MP-{order_num}"
    order_id = f"#{order_key}"
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    date_only = datetime.now().strftime("%d/%m/%Y")
    time_info = f"Thời gian đặt: {now_str} • Vận chuyển: GHN Express (Mã: GHN{random.randint(1000000, 9999999)})"

    cursor.execute("""
        INSERT INTO orders (
            order_key, id_display, escrow_badge, escrow_class, time_info,
            shop_name, shop_address, buyer_name, buyer_phone, buyer_address,
            total, numeric_total, fee, net, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'escrow', ?);
    """, (
        order_key,
        order_id,
        "🔒 Sàn đang giữ tiền",
        "bg-primary-50 text-primary-500",
        time_info,
        payload.shop_name,
        "Kho lấy hàng: Nguyễn Thị Minh Khai, Quận 1, TP.HCM",
        f"{payload.buyer_name} ({payload.buyer_phone})",
        payload.buyer_phone,
        payload.buyer_address,
        payload.total,
        payload.numeric_total,
        payload.fee,
        payload.net,
        date_only
    ))

    # 3. Lưu từng sản phẩm vào bảng order_items
    for item in payload.items:
        cursor.execute("""
            INSERT INTO order_items (order_key, name, variant, price, qty, subtotal)
            VALUES (?, ?, ?, ?, ?, ?);
        """, (order_key, item.name, item.variant, item.price, item.qty, item.subtotal))

    # 4. Cập nhật hoặc thêm mới Khách hàng vào bảng customers
    cursor.execute("SELECT * FROM customers WHERE phone = ?;", (payload.buyer_phone.strip(),))
    existing_cust = cursor.fetchone()

    if existing_cust:
        new_count = (existing_cust["orders_count"] or 0) + 1
        cursor.execute("""
            UPDATE customers
            SET orders_count = ?, total_spent = ?, address = ?
            WHERE cust_key = ?;
        """, (new_count, payload.total, payload.buyer_address, existing_cust["cust_key"]))
    else:
        cust_num = random.randint(100, 999)
        cust_key = f"CUST-{cust_num}"
        cursor.execute("""
            INSERT INTO customers (
                cust_key, id_display, name, phone, email, avatar,
                `rank`, rank_badge, joined, orders_count, total_spent,
                status, status_badge, address, is_banned
            ) VALUES (?, ?, ?, ?, ?, ?, 'Đồng', 'bg-neutral-100 text-neutral-600 border-neutral-200', ?, 1, ?, 'Hoạt động', 'bg-emerald-50 text-emerald-600', ?, 0);
        """, (
            cust_key,
            f"#{cust_key}",
            payload.buyer_name,
            payload.buyer_phone,
            f"{payload.buyer_phone}@gmail.com",
            "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=80&h=80&q=80",
            date_only,
            payload.total,
            payload.buyer_address,
        ))

    conn.commit()
    conn.close()

    return {
        "message": "Đặt hàng thành công và đã lưu vào cơ sở dữ liệu SQL!",
        "order_key": order_key,
        "order_id": order_id,
    }


@app.put("/api/admin/orders/{order_key}/release")
def release_order_escrow(order_key: str):
    """Admin duyệt giải ngân tiền từ quỹ Escrow về ví Shop trong SQL."""
    clean_key = order_key.replace("#", "")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orders
        SET status = 'released',
            escrow_badge = '✓ Đã giải ngân về Ví Shop',
            escrow_class = 'bg-success-50 text-success-500'
        WHERE order_key = ?;
    """, (clean_key,))
    conn.commit()
    conn.close()

    return {"message": f"Đã giải ngân đơn hàng #{clean_key} trong SQL Database!"}


@app.put("/api/admin/orders/{order_key}/freeze")
def freeze_order_escrow(order_key: str, payload: FreezeOrderRequest):
    """Admin đóng băng tiền đơn hàng do khiếu nại/tranh chấp trong SQL."""
    clean_key = order_key.replace("#", "")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orders
        SET status = 'dispute',
            escrow_badge = ?,
            escrow_class = 'bg-danger-50 text-danger-500'
        WHERE order_key = ?;
    """, (f"⚠️ Đang đóng băng tranh chấp ({payload.reason})", clean_key))
    conn.commit()
    conn.close()

    return {"message": f"Đã đóng băng đơn hàng #{clean_key} trong SQL Database!"}


# ==============================================================================
# 3. API QUẢN LÝ KHÁCH HÀNG (BUYERS / USERS)
# ==============================================================================
@app.get("/api/admin/customers")
def get_all_customers():
    """Lấy danh sách khách hàng và lịch sử mua hàng từ SQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customers ORDER BY cust_key DESC;")
    cust_rows = cursor.fetchall()

    customers_dict = {}
    for c in cust_rows:
        cursor.execute("""
            SELECT id_display, shop_name, created_at, total, status
            FROM orders
            WHERE buyer_phone = ?
            ORDER BY order_key DESC;
        """, (c["phone"],))
        order_rows = cursor.fetchall()

        history = [
            {
                "id": o["id_display"],
                "shop": o["shop_name"].split("(")[0].strip(),
                "date": o["created_at"],
                "total": o["total"],
                "status": (
                    "Đã hoàn tất" if o["status"] == "released"
                    else "Tranh chấp / Khiếu nại" if o["status"] == "dispute"
                    else "Sàn đang giữ tiền"
                ),
            }
            for o in order_rows
        ]

        customers_dict[c["cust_key"]] = {
            "id": c["id_display"],
            "name": c["name"],
            "phone": c["phone"],
            "email": c["email"],
            "avatar": c["avatar"],
            "rank": c["rank"],
            "rankBadge": c["rank_badge"],
            "joined": c["joined"],
            "ordersCount": c["orders_count"],
            "totalSpent": c["total_spent"],
            "status": "Đã bị khóa" if c["is_banned"] == 1 else c["status"],
            "statusBadge": "bg-red-100 text-red-700 font-bold" if c["is_banned"] == 1 else c["status_badge"],
            "address": c["address"],
            "isBanned": bool(c["is_banned"]),
            "ordersHistory": history,
        }

    conn.close()
    return {"customers": customers_dict}


@app.put("/api/admin/customers/{cust_key}/toggle-ban")
def toggle_customer_ban(cust_key: str):
    """Admin Khóa hoặc Mở khóa tài khoản khách hàng trong SQL."""
    clean_key = cust_key.replace("#", "")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customers WHERE cust_key = ?;", (clean_key,))
    cust = cursor.fetchone()
    if not cust:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng!")

    new_ban = 0 if cust["is_banned"] == 1 else 1
    new_status = "Đã bị khóa" if new_ban == 1 else "Hoạt động"
    new_badge = "bg-red-100 text-red-700 font-bold" if new_ban == 1 else "bg-emerald-50 text-emerald-600"

    cursor.execute("""
        UPDATE customers
        SET is_banned = ?, status = ?, status_badge = ?
        WHERE cust_key = ?;
    """, (new_ban, new_status, new_badge, clean_key))
    conn.commit()
    conn.close()

    return {
        "cust_key": clean_key,
        "name": cust["name"],
        "phone": cust["phone"],
        "is_banned": bool(new_ban),
        "status": new_status,
    }


@app.delete("/api/admin/customers/{cust_key}")
def delete_customer(cust_key: str):
    """Admin xóa vĩnh viễn khách hàng khỏi hệ thống."""
    clean_key = cust_key.replace("#", "")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customers WHERE cust_key = ?;", (clean_key,))
    cust = cursor.fetchone()
    if not cust:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng!")

    phone = cust["phone"]
    # Xóa khách hàng trong bảng customers
    cursor.execute("DELETE FROM customers WHERE cust_key = ?;", (clean_key,))
    # Xóa user tương ứng trong bảng users nếu có
    cursor.execute("DELETE FROM users WHERE cust_key = ? OR phone = ? OR username = ?;", (clean_key, phone, phone))
    conn.commit()
    conn.close()

    return {"message": f"Đã xóa vĩnh viễn khách hàng {cust['name']} (#{clean_key})!", "cust_key": clean_key}


@app.post("/api/admin/customers")
def create_customer(payload: CustomerCreate):
    """Admin thêm khách hàng mới trực tiếp vào SQL."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM customers WHERE phone = ?;", (payload.phone,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Số điện thoại này đã tồn tại trong danh sách khách hàng!")

    cust_key = f"CUST-{random.randint(100, 999)}"
    id_display = f"#{cust_key}"
    rank_badges = {
        "Kim Cương": "bg-indigo-50 text-indigo-700 border-indigo-200",
        "Vàng": "bg-amber-50 text-amber-700 border-amber-200",
        "Bạc": "bg-slate-50 text-slate-700 border-slate-200",
        "Đồng": "bg-neutral-100 text-neutral-600 border-neutral-200"
    }
    badge = rank_badges.get(payload.rank, "bg-neutral-100 text-neutral-600 border-neutral-200")
    avatar = f"https://api.dicebear.com/7.x/avataaars/svg?seed={payload.phone}"
    today_str = datetime.now().strftime("%d/%m/%Y")

    cursor.execute("""
        INSERT INTO customers (
            cust_key, id_display, name, phone, email, avatar, `rank`, rank_badge,
            joined, orders_count, total_spent, status, status_badge, address, is_banned
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '0 ₫', 'Hoạt động', 'bg-emerald-50 text-emerald-600', ?, 0);
    """, (
        cust_key, id_display, payload.name, payload.phone, payload.email,
        avatar, payload.rank, badge, today_str, payload.address
    ))
    conn.commit()
    conn.close()

    return {
        "message": "Thêm khách hàng vào SQL thành công!",
        "cust_key": cust_key,
        "id_display": id_display,
        "name": payload.name,
        "phone": payload.phone,
        "email": payload.email,
        "rank": payload.rank,
    }


# ==============================================================================
# 3.5. API CHỈ SỐ DASHBOARD & ĐẶT VỀ 0 (RESET / METRICS)
# ==============================================================================
@app.get("/api/admin/metrics")
def get_admin_metrics():
    """Lấy toàn bộ chỉ số thực tế được tính toán từ các bảng SQL."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Sản phẩm
    cursor.execute("SELECT COUNT(*) FROM products;")
    total_products = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM products WHERE status = 'pending';")
    pending_products = cursor.fetchone()[0]

    # 2. Khách hàng
    cursor.execute("SELECT COUNT(*) FROM customers;")
    total_customers = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM customers WHERE `rank` IN ('VIP', 'Kim Cương', 'Vàng');")
    vip_customers = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM customers WHERE orders_count > 0;")
    active_buyers = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM customers WHERE is_banned = 1;")
    banned_customers = cursor.fetchone()[0]

    # 3. Đơn hàng & GMV & Hoa hồng
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(numeric_total), 0) FROM orders;")
    order_row = cursor.fetchone()
    total_orders = order_row[0]
    total_gmv = int(order_row[1]) if order_row[1] is not None else 0
    total_revenue = round(total_gmv * 0.07)

    # 4. Cửa hàng
    cursor.execute("SELECT COUNT(*) FROM shops;")
    total_shops = cursor.fetchone()[0]

    conn.close()

    return {
        "total_gmv": total_gmv,
        "total_revenue": total_revenue,
        "total_products": total_products,
        "pending_products": pending_products,
        "total_customers": total_customers,
        "vip_customers": vip_customers,
        "active_buyers": active_buyers,
        "banned_customers": banned_customers,
        "total_orders": total_orders,
        "total_shops": total_shops,
    }


@app.post("/api/admin/reset-data")
def reset_all_data():
    """Đặt toàn bộ chỉ số và dữ liệu về 0 (Xóa sạch các bảng để test từ đầu)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM order_items;")
    cursor.execute("DELETE FROM orders;")
    cursor.execute("DELETE FROM customers;")
    cursor.execute("DELETE FROM products;")
    cursor.execute("DELETE FROM shops;")
    cursor.execute("DELETE FROM users WHERE role != 'admin';")
    conn.commit()
    conn.close()
    return {"message": "Toàn bộ dữ liệu và chỉ số đã được đặt về 0 thành công!"}


@app.post("/api/admin/seed-sample-data")
def seed_sample_data_api():
    """Nạp lại bộ dữ liệu mẫu ban đầu nếu muốn."""
    conn = get_db_connection()
    seed_initial_data(conn)
    conn.close()
    return {"message": "Đã nạp lại dữ liệu mẫu thành công!"}


# ==============================================================================
# 4. API ĐĂNG NHẬP & ĐĂNG KÝ (KHÁCH HÀNG, CHỦ SHOP / SELLER, ADMIN)
# ==============================================================================
@app.post("/api/auth/register")
def register_account(payload: RegisterRequest):
    """Đăng ký tài khoản mới cho Khách hàng, Chủ Shop hoặc Admin vào MySQL."""
    conn = get_db_connection()
    cursor = conn.cursor()

    username = payload.username.strip()
    phone = payload.phone.strip()
    email = payload.email.strip() or f"{username}@jmlstore.vn"
    full_name = payload.full_name.strip()
    address = payload.address.strip() or "TP. Hồ Chí Minh"
    role = payload.role.strip().lower()
    now_str = datetime.now().strftime("%d/%m/%Y")

    # Kiểm tra trùng username
    cursor.execute("SELECT id FROM users WHERE username = ?;", (username,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail=f"Tên đăng nhập '{username}' đã tồn tại!")

    cust_key = ""
    shop_key = ""
    shop_name = ""

    if role == "customer":
        # Kiểm tra xem SĐT đã có trong bảng customers chưa
        cursor.execute("SELECT cust_key FROM customers WHERE phone = ?;", (phone,))
        existing_c = cursor.fetchone()
        if existing_c:
            cust_key = existing_c["cust_key"]
        else:
            cust_key = f"CUST-{random.randint(100, 999)}"
            avatar_url = "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=100&q=80"
            cursor.execute("""
                INSERT INTO customers (
                    cust_key, id_display, name, phone, email, avatar,
                    `rank`, rank_badge, joined, orders_count, total_spent,
                    status, status_badge, address, is_banned
                ) VALUES (?, ?, ?, ?, ?, ?, 'Đồng', 'bg-neutral-100 text-neutral-600 border-neutral-200', ?, 0, '0 ₫', 'Hoạt động', 'bg-emerald-50 text-emerald-600', ?, 0);
            """, (cust_key, f"#{cust_key}", full_name, phone, email, avatar_url, now_str, address))

    elif role == "seller":
        shop_name = (payload.shop_name or f"{full_name} Official").strip()
        shop_key = f"SH-{random.randint(100, 999)}"
        words = [w[0].upper() for w in shop_name.split() if w]
        initials = "".join(words[:2]) if words else "SH"

        badge = payload.shop_badge or "JML MALL"
        if badge == "JML MALL":
            badge_class = "bg-danger-500 text-white"
        elif badge == "YÊU THÍCH+":
            badge_class = "bg-warning-500 text-white"
        else:
            badge_class = "bg-neutral-200 text-neutral-700"

        meta_str = f"Chủ Shop: {full_name} ({phone}) • Kho: {address}"

        cursor.execute("""
            INSERT INTO shops (
                shop_key, id_display, initials, name, badge, badge_class,
                meta, gmv, fee, product_count, rating, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '0 ₫', '0 ₫', '0 sản phẩm', '★ 5.0 (Mới)', 'active');
        """, (shop_key, f"#{shop_key}", initials, shop_name, badge, badge_class, meta_str))

    cursor.execute("""
        INSERT INTO users (
            username, password, role, full_name, phone, email, address,
            shop_key, shop_name, cust_key, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (username, payload.password, role, full_name, phone, email, address, shop_key, shop_name, cust_key, now_str))

    new_user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "message": "Đăng ký tài khoản thành công!",
        "user": {
            "id": new_user_id,
            "username": username,
            "role": role,
            "full_name": full_name,
            "phone": phone,
            "email": email,
            "address": address,
            "shop_key": shop_key,
            "shop_name": shop_name,
            "cust_key": cust_key,
        }
    }


@app.post("/api/auth/login")
def login_account(payload: LoginRequest):
    """Đăng nhập cho Khách hàng, Chủ Shop hoặc Admin từ MySQL."""
    conn = get_db_connection()
    cursor = conn.cursor()

    identifier = payload.username.strip()
    pwd = payload.password

    cursor.execute("""
        SELECT * FROM users
        WHERE (username = ? OR phone = ? OR email = ?) AND password = ?;
    """, (identifier, identifier, identifier, pwd))
    user_row = cursor.fetchone()

    # Hỗ trợ đăng nhập nhanh cho Khách hàng được Admin tạo từ bảng customers (mật khẩu mặc định 123456)
    if not user_row and pwd == "123456":
        cursor.execute("""
            SELECT * FROM customers
            WHERE phone = ? OR email = ? OR cust_key = ?;
        """, (identifier, identifier, identifier))
        cust = cursor.fetchone()
        if cust:
            if cust["is_banned"] == 1:
                conn.close()
                raise HTTPException(status_code=403, detail="Tài khoản Khách hàng này đã bị Ban Quản Trị Sàn khóa!")
            conn.close()
            return {
                "message": "Đăng nhập Khách hàng thành công!",
                "user": {
                    "id": 0,
                    "username": cust["phone"],
                    "role": "customer",
                    "full_name": cust["name"],
                    "phone": cust["phone"],
                    "email": cust["email"],
                    "address": cust["address"],
                    "shop_key": "",
                    "shop_name": "",
                    "cust_key": cust["cust_key"],
                    "rank": cust["rank"],
                }
            }

    if not user_row:
        conn.close()
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập (SĐT/Email) hoặc mật khẩu!")

    # Nếu là customer, kiểm tra xem có bị khóa trong bảng customers không
    cust_rank = "Đồng"
    if user_row["role"] == "customer":
        cursor.execute("SELECT is_banned, `rank` FROM customers WHERE cust_key = ? OR phone = ?;", (user_row["cust_key"], user_row["phone"]))
        c_check = cursor.fetchone()
        if c_check:
            if c_check["is_banned"] == 1:
                conn.close()
                raise HTTPException(status_code=403, detail="Tài khoản của bạn đã bị Ban Quản Trị Sàn khóa do vi phạm chính sách!")
            cust_rank = c_check["rank"]

    conn.close()
    return {
        "message": "Đăng nhập thành công!",
        "user": {
            "id": user_row["id"],
            "username": user_row["username"],
            "role": user_row["role"],
            "full_name": user_row["full_name"],
            "phone": user_row["phone"],
            "email": user_row["email"],
            "address": user_row["address"] or "",
            "shop_key": user_row["shop_key"] or "",
            "shop_name": user_row["shop_name"] or "",
            "cust_key": user_row["cust_key"] or "",
            "rank": cust_rank,
        }
    }


# ==============================================================================
# 5. API QUẢN LÝ CỬA HÀNG (SHOPS) & GIAO DIỆN CHỦ SHOP (SELLER CENTER)
# ==============================================================================
@app.get("/api/admin/shops")
def get_all_shops():
    """Lấy danh sách toàn bộ Cửa hàng (Shops) kèm sản phẩm & doanh thu thực tế từ MySQL."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM shops ORDER BY shop_key DESC;")
    shop_rows = cursor.fetchall()

    shops_dict = {}
    for s in shop_rows:
        s_name = s["name"]
        # Lấy danh sách sản phẩm của Shop
        cursor.execute("SELECT * FROM products WHERE shop_name LIKE ? ORDER BY id DESC;", (f"%{s_name}%",))
        p_rows = cursor.fetchall()

        products_list = [
            {
                "id": p["id"],
                "name": p["title"],
                "sku": f"SKU-{p['id']:04d}",
                "price": f"{int(p['price']):,} ₫".replace(",", "."),
                "numeric_price": p["price"],
                "stock": f"{p['total_stock']} kho",
                "sold": f"Đã bán {p['sold']}",
                "status": "Đang bán" if p["status"] == "approved" else "Chờ duyệt"
            }
            for p in p_rows
        ]

        # Tính tổng GMV của Shop từ bảng orders
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(numeric_total), 0)
            FROM orders
            WHERE shop_name LIKE ?;
        """, (f"%{s_name}%",))
        o_stat = cursor.fetchone()
        shop_orders_count = o_stat[0] if o_stat else 0
        shop_gmv_num = int(o_stat[1]) if (o_stat and o_stat[1] is not None) else 0
        shop_fee_num = round(shop_gmv_num * 0.07)

        gmv_str = f"{shop_gmv_num:,} ₫".replace(",", ".") if shop_gmv_num > 0 else "0 ₫"
        fee_str = f"{shop_fee_num:,} ₫".replace(",", ".") if shop_fee_num > 0 else "0 ₫"

        shops_dict[s["shop_key"]] = {
            "shop_key": s["shop_key"],
            "id_display": s["id_display"],
            "initials": s["initials"],
            "name": s_name,
            "badge": s["badge"],
            "badgeClass": s["badge_class"],
            "meta": s["meta"],
            "gmv": gmv_str,
            "numericGmv": shop_gmv_num,
            "fee": fee_str,
            "numericFee": shop_fee_num,
            "ordersCount": shop_orders_count,
            "productCount": f"{len(products_list)} sản phẩm",
            "numericProductCount": len(products_list),
            "rating": s["rating"],
            "status": s["status"],
            "products": products_list,
        }

    conn.close()
    return {"shops": shops_dict}


@app.get("/api/seller/dashboard")
def get_seller_dashboard(shop_key: str = Query(""), shop_name: str = Query("")):
    """Lấy toàn bộ dữ liệu Tổng quan, Sản phẩm, Đơn hàng, Ví tiền của một Cửa hàng (Chủ Shop)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    shop_row = None
    if shop_key:
        cursor.execute("SELECT * FROM shops WHERE shop_key = ?;", (shop_key,))
        shop_row = cursor.fetchone()
    if not shop_row and shop_name:
        cursor.execute("SELECT * FROM shops WHERE name = ?;", (shop_name,))
        shop_row = cursor.fetchone()

    # Nếu không truyền shop_key/shop_name (chưa đăng nhập), không tự ý lấy bừa shop của người khác
    if not shop_row:
        conn.close()
        return {
            "shop": None,
            "metrics": {
                "total_gmv": 0,
                "total_net": 0,
                "total_fee": 0,
                "escrow_balance": 0,
                "available_balance": 0,
                "total_orders": 0,
                "total_products": 0,
            },
            "products": [],
            "orders": []
        }

    actual_name = shop_row["name"]
    actual_key = shop_row["shop_key"]

    # 1. Sản phẩm của Shop
    cursor.execute("SELECT * FROM products WHERE shop_name LIKE ? ORDER BY id DESC;", (f"%{actual_name}%",))
    prod_rows = cursor.fetchall()
    products = []
    for p in prod_rows:
        imgs = json.loads(p["images_json"]) if p["images_json"] else []
        products.append({
            "id": p["id"],
            "title": p["title"],
            "category": p["category"],
            "price": p["price"],
            "original_price": p["original_price"],
            "discount": p["discount"],
            "stock": p["total_stock"],
            "sold": p["sold"],
            "rating": p["rating"],
            "is_flash_sale": p["is_flash_sale"] == 1,
            "image": imgs[0] if imgs else "",
            "status": p["status"]
        })

    # 2. Đơn hàng của Shop
    cursor.execute("SELECT * FROM orders WHERE shop_name LIKE ? ORDER BY order_key DESC;", (f"%{actual_name}%",))
    ord_rows = cursor.fetchall()
    orders = []
    total_gmv = 0
    escrow_balance = 0
    available_balance = 0

    for o in ord_rows:
        cursor.execute("SELECT * FROM order_items WHERE order_key = ?;", (o["order_key"],))
        items_rows = cursor.fetchall()
        items = [
            {
                "name": it["name"],
                "variant": it["variant"],
                "price": it["price"],
                "qty": it["qty"],
                "subtotal": it["subtotal"]
            }
            for it in items_rows
        ]
        num_tot = int(o["numeric_total"] or 0)
        net_val = round(num_tot * 0.93)
        total_gmv += num_tot
        if o["status"] == "released":
            available_balance += net_val
        elif o["status"] == "escrow":
            escrow_balance += net_val

        orders.append({
            "order_key": o["order_key"],
            "id_display": o["id_display"],
            "buyer_name": o["buyer_name"],
            "buyer_phone": o["buyer_phone"],
            "buyer_address": o["buyer_address"],
            "total": o["total"],
            "numeric_total": num_tot,
            "fee": o["fee"],
            "net": o["net"],
            "status": o["status"],
            "escrow_badge": o["escrow_badge"],
            "time_info": o["time_info"],
            "created_at": o["created_at"],
            "items": items
        })

    total_fee = round(total_gmv * 0.07)
    total_net = total_gmv - total_fee

    conn.close()
    return {
        "shop": {
            "shop_key": actual_key,
            "id_display": shop_row["id_display"],
            "initials": shop_row["initials"],
            "name": actual_name,
            "badge": shop_row["badge"],
            "badge_class": shop_row["badge_class"],
            "meta": shop_row["meta"],
            "rating": shop_row["rating"],
            "status": shop_row["status"],
        },
        "metrics": {
            "total_gmv": total_gmv,
            "total_net": total_net,
            "total_fee": total_fee,
            "escrow_balance": escrow_balance,
            "available_balance": available_balance,
            "total_orders": len(orders),
            "total_products": len(products),
        },
        "products": products,
        "orders": orders
    }


@app.put("/api/seller/shop")
def update_seller_shop(payload: ShopUpdateRequest):
    """Chủ Shop cập nhật thông tin cửa hàng trong MySQL."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM shops WHERE shop_key = ?;", (payload.shop_key,))
    old_shop = cursor.fetchone()
    if not old_shop:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy Cửa hàng!")

    old_name = old_shop["name"]
    new_name = payload.name.strip()
    badge = payload.badge

    if badge == "JML MALL":
        badge_class = "bg-danger-500 text-white"
    elif badge == "YÊU THÍCH+":
        badge_class = "bg-warning-500 text-white"
    else:
        badge_class = "bg-neutral-200 text-neutral-700"

    meta_str = payload.address.strip() if payload.address else old_shop["meta"]
    words = [w[0].upper() for w in new_name.split() if w]
    initials = "".join(words[:2]) if words else "SH"

    cursor.execute("""
        UPDATE shops
        SET name = ?, initials = ?, badge = ?, badge_class = ?, meta = ?
        WHERE shop_key = ?;
    """, (new_name, initials, badge, badge_class, meta_str, payload.shop_key))

    if old_name != new_name:
        cursor.execute("UPDATE products SET shop_name = ? WHERE shop_name = ?;", (new_name, old_name))
        cursor.execute("UPDATE users SET shop_name = ? WHERE shop_key = ?;", (new_name, payload.shop_key))

    conn.commit()
    conn.close()
    return {"message": "Đã cập nhật hồ sơ Cửa hàng thành công!", "shop_name": new_name}


# ==============================================================================
# 6. PHỤC VỤ GIAO DIỆN FRONTEND TĨNH TRỰC TIẾP TỪ FASTAPI VÀ CÁC ĐƯỜNG DẪN TRỰC TIẾP
# ==============================================================================
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.get("/")
def root():
    """Mặc định vào thẳng giao diện Khách Hàng (User)"""
    return RedirectResponse(url="/frontend/user/index.html")


@app.get("/login")
def login_portal():
    """Điều hướng vào thẳng giao diện Khách Hàng (Mỗi trang đăng nhập trực tiếp tại trang đó)"""
    return RedirectResponse(url="/frontend/user/index.html")


@app.get("/user")
def user_portal():
    """Đường link riêng vào thẳng Kênh Khách Hàng (User Storefront)"""
    return RedirectResponse(url="/frontend/user/index.html")


@app.get("/seller")
def seller_portal():
    """Đường link riêng vào thẳng Kênh Chủ Shop / Cửa Hàng (Seller Center)"""
    return RedirectResponse(url="/frontend/seller/index.html")


@app.get("/admin")
def admin_portal():
    """Đường link riêng vào thẳng Kênh Quản Trị Sàn (Admin)"""
    return RedirectResponse(url="/frontend/admin/index.html")


