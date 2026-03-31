import sqlite3, os
c = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'instance', 'fcn_data.db'))
print('USERS:', c.execute('SELECT id,username,role FROM app_users').fetchall())
print('CLIENTS:', c.execute('SELECT id,name,user_id FROM clients').fetchall())
print('PRODUCTS:', c.execute('SELECT id,product_code,user_id FROM products').fetchall())
