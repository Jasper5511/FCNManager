"""修復資料庫：刪除舊的 app_users 表，讓 app 自動重建正確結構"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'instance', 'fcn_data.db')
print(f'Database path: {db_path}')
print(f'File exists: {os.path.exists(db_path)}')

conn = sqlite3.connect(db_path)
c = conn.cursor()

# 列出所有表
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print(f'Tables before: {tables}')

# 刪除 app_users
c.execute('DROP TABLE IF EXISTS app_users')
conn.commit()

# 確認
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print(f'Tables after: {tables}')

conn.close()
print('DONE - now reload the web app')
