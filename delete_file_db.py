import mysql.connector

# Koneksi ke database MySQL
conn = mysql.connector.connect(
    host='localhost',
    user='root',
    password='',
    database='kms_db'
)

cursor = conn.cursor()

# Menonaktifkan foreign key checks
cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

# Daftar tabel yang akan di-truncate
tables = ["kms_app_docdetails", "kms_app_documents", "kms_app_postinglistlemmas", "kms_app_postinglists", "kms_app_refinements", "kms_app_termlemmas", "kms_app_terms"]

# Melakukan TRUNCATE TABLE pada setiap tabel dalam daftar
for table in tables:
    truncate_query = f"TRUNCATE TABLE {table}"
    cursor.execute(truncate_query)

# Mengaktifkan kembali foreign key checks
cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

# Commit perubahan dan tutup koneksi
conn.commit()
cursor.close()
conn.close()

