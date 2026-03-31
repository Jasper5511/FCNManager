import sqlite3, os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'fcn_data.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Step 1: 確保 app_users 有正確欄位
c.execute('DROP TABLE IF EXISTS app_users')
c.execute('''CREATE TABLE app_users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(200) NOT NULL,
    role VARCHAR(10) DEFAULT 'user',
    created_at DATETIME
)''')
print('Step 1: app_users table recreated')

# Step 2: 建立 admin 帳號 (使用 werkzeug 雜湊)
from werkzeug.security import generate_password_hash
admin_pw = generate_password_hash('fcn2026')
c.execute('INSERT INTO app_users (id, username, password, role) VALUES (1, ?, ?, ?)',
          ('admin', admin_pw, 'admin'))
print('Step 2: admin account created (id=1)')

# Step 3: 確保 clients 有 user_id 欄位
try:
    c.execute('ALTER TABLE clients ADD COLUMN user_id INTEGER')
    print('Step 3: Added user_id to clients')
except:
    print('Step 3: clients.user_id already exists')

# Step 4: 確保 products 有 user_id 欄位
try:
    c.execute('ALTER TABLE products ADD COLUMN user_id INTEGER')
    print('Step 4: Added user_id to products')
except:
    print('Step 4: products.user_id already exists')

# Step 5: 把所有資料歸屬 admin (id=1)
c.execute('UPDATE clients SET user_id=1 WHERE user_id IS NULL')
c.execute('UPDATE products SET user_id=1 WHERE user_id IS NULL')
print('Step 5: All data assigned to admin (user_id=1)')

conn.commit()

# Step 6: 驗證
users = c.execute('SELECT id, username, role FROM app_users').fetchall()
clients = c.execute('SELECT count(*), user_id FROM clients GROUP BY user_id').fetchall()
products = c.execute('SELECT count(*), user_id FROM products GROUP BY user_id').fetchall()
print(f'Step 6: Users={users}, Clients={clients}, Products={products}')

conn.close()
print('ALL DONE - go reload the web app')
