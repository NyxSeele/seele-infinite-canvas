"""
Run this script to fix the admin user's role in the database.
Usage: python fix_admin_role.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from db.session import SessionLocal
from models import User

db = SessionLocal()
try:
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        print("未找到 admin 用户，请先运行 init_db.py")
        sys.exit(1)
    if admin.role == "admin":
        print(f"admin 角色已正确：role = {admin.role}，无需修复")
    else:
        admin.role = "admin"
        db.commit()
        print(f"已修复：admin 角色已更新为 'admin'")
finally:
    db.close()
