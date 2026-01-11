# from dotenv import load_dotenv
# import os
# import mysql.connector

# class MySQLPipeline:
#     def __init__(self):
#         load_dotenv()  # Load environment variables from .env
#         self.create_connection()
#         self.create_table()

#     def create_connection(self):
#         self.conn = mysql.connector.connect(
#             host=os.getenv("DB_HOST"),
#             port=int(os.getenv("DB_PORT")),
#             user=os.getenv("DB_USER"),
#             password=os.getenv("DB_PASSWORD"),
#             database=os.getenv("DB_NAME"),
#             ssl_ca=os.getenv("DB_SSL_CA")
#         )
#         self.curr = self.conn.cursor()

#     def create_table(self):
#         # Create table with composite unique key on (vendor, link)
#         self.curr.execute("""
#         CREATE TABLE IF NOT EXISTS cpu_prices (
#             id INT AUTO_INCREMENT PRIMARY KEY,
#             name VARCHAR(255),
#             link VARCHAR(500),
#             price VARCHAR(50),
#             vendor VARCHAR(255),
#             UNIQUE KEY unique_vendor_link (vendor, link)
#         )
#         """)
#         self.conn.commit()

#     def open_spider(self, spider):
#         # Optionally start a transaction
#         self.conn.start_transaction()

#     def process_item(self, item, spider):
#         try:
#             self.curr.execute("""
#                 INSERT INTO cpu_prices (name, link, price, vendor) VALUES (%s, %s, %s, %s)
#                 ON DUPLICATE KEY UPDATE
#                     name = VALUES(name),
#                     price = VALUES(price)
#             """, (
#                 item.get('name'),
#                 item.get('link'),
#                 item.get('price'),
#                 item.get('vendor'),
#             ))
#             # Optional: commit every item or batch commit
#             self.conn.commit()
#         except mysql.connector.Error as err:
#             print(f"Error inserting item: {err}")  # Log the error
#             self.conn.rollback()
#         return item

#     def close_spider(self, spider):
#         # Commit any remaining changes and close
#         self.conn.commit()
#         self.curr.close()
#         self.conn.close()
