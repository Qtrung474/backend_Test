from pydantic import BaseModel
from typing import List, Optional


class ProductCreate(BaseModel):
    title: str
    category: str = "tech"
    price: int
    original_price: Optional[int] = None
    image: str = "https://images.unsplash.com/photo-1546435770-a3e426bf472b?auto=format&fit=crop&w=800&q=80"
    shop_name: str = "AB Technology Ltd"
    is_flash_sale: bool = False
    stock: int = 100


class OrderItemCreate(BaseModel):
    name: str
    variant: str
    price: str
    qty: str
    subtotal: str


class OrderCreate(BaseModel):
    buyer_name: str
    buyer_phone: str
    buyer_address: str
    shop_name: str = "AB Technology Ltd (JML Mall - #SH-102)"
    total: str
    numeric_total: int = 0
    fee: str
    net: str
    items: List[OrderItemCreate]


class FreezeOrderRequest(BaseModel):
    reason: str = "Khách khiếu nại sản phẩm lỗi"


class CustomerCreate(BaseModel):
    name: str
    phone: str
    email: str
    address: str
    rank: str = "Đồng"


class LoginRequest(BaseModel):
    username: str
    password: str
    role: Optional[str] = None


class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "customer"  # 'customer', 'seller', 'admin'
    full_name: str
    phone: str
    email: str = ""
    address: str = ""
    shop_name: str = ""
    shop_badge: str = "TIÊU CHUẨN"


class ShopUpdateRequest(BaseModel):
    shop_key: str
    name: str
    badge: str = "TIÊU CHUẨN"
    address: str = ""



