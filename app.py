import os
import pymysql
from flask import Flask, jsonify
from dotenv import load_dotenv

# 1. Load environment variables from the .env file
load_dotenv()

app = Flask(__name__)

# 2. Database Connection Function
def get_db_connection():
    # We use pymysql because it's pure Python and easy to set up
    connection = pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        port=int(os.getenv('DB_PORT', 3306)), # Default to 3306 if not found
        cursorclass=pymysql.cursors.DictCursor,
        
        # Aiven requires SSL. passing an empty dictionary often triggers the 
        # default SSL context which satisfies Aiven's requirement.
        ssl={'ssl': {}}
    )
    return connection

# ------------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------------

@app.route('/')
def home():
    return "<h1>Flask App is Running!</h1><p>Go to <a href='/test_db'>/test_db</a> to check the database connection.</p>"

@app.route('/test_db')
def test_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Simple query to check connection
        cursor.execute("SELECT DATABASE() as db_name;")
        result = cursor.fetchone()
        
        # Optional: Show tables to verify your import worked
        cursor.execute("SHOW TABLES;")
        tables = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success", 
            "message": "Connected to Aiven Cloud DB!",
            "connected_to": result['db_name'],
            "tables_found": tables
        })
        
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": str(e)
        })

if __name__ == '__main__':
    app.run(debug=True)