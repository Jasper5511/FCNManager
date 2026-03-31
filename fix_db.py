"""修復資料庫：加入 user_id 欄位，重建 app_users 表"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'instance', 'fcn_data.db')
print(f'Database: {db_path}')

conn = sqlite3.connect(db_path)
c = conn.cursor()

# 重建 app_users
c.execute('DROP TABLE IF EXISTS app_users')

# 加 user_id 到 clients
try:
    c.execute('ALTER TABLE clients ADD COLUMN user_id INTEGER')
    print('Added user_id to clients')
except:
    print('clients.user_id already exists')

# 加 user_id 到 products
try:
    c.execute('ALTER TABLE products ADD COLUMN user_id INTEGER')
    print('Added user_id to products')
except:
    print('products.user_id already exists')

# 移除 product_code 的 unique 限制（SQLite 無法直接移除，但新資料不會衝突）

conn.commit()
conn.close()
print('DONE')
