import os
import pymysql
from datetime import date
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
from dotenv import load_dotenv

# ------------------------------------------------------------------
# Load environment variables from 'config.env' specifically
# ------------------------------------------------------------------
load_dotenv('config.env') 

app = Flask(__name__)

# SECRET KEY IS REQUIRED FOR SESSIONS
app.secret_key = 'super_secret_lego_key' 

# ------------------------------------------------------------------
# DATABASE CONNECTION FUNCTION
# ------------------------------------------------------------------
def get_db_connection():
    connection = pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        port=int(os.getenv('DB_PORT', 3306)),
        cursorclass=pymysql.cursors.DictCursor,
        ssl={'ssl': {}}
    )
    return connection

# ------------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------------

# 1. Landing Page (Login)
@app.route('/', methods=['GET', 'POST'])
def landing():
    if request.method == 'POST':
        user_id = request.form['user_id']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM USERS WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if user:
            session['user_id'] = user['user_id']
            session['name'] = user['name']
            # Initialize cart if not exists
            if 'cart' not in session:
                session['cart'] = {}
            return redirect(url_for('dashboard'))
        else:
            return redirect(url_for('create_user', new_id=user_id))

    return render_template('index.html')

# 2. Create User Page
@app.route('/create_user', methods=['GET', 'POST'])
def create_user():
    if request.method == 'POST':
        user_id = request.form['user_id']
        name = request.form['name']
        address = request.form['address']
        age = request.form['age']
        user_balance = 100.00 
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            query = "INSERT INTO USERS (user_id, name, address, user_balance, age) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(query, (user_id, name, address, user_balance, age))
            conn.commit()
            
            cursor.close()
            conn.close()
            
            session['user_id'] = user_id
            session['name'] = name
            session['cart'] = {} # Initialize empty cart
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            return f"Error creating user: {str(e)}"

    prefill_id = request.args.get('new_id', '')
    return render_template('create_user.html', prefill_id=prefill_id)

# 3. Dashboard (The Main Store Page)
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('landing'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch Lego Sets
    query = """
        SELECT 
            l.set_id, l.name, l.price, l.theme, l.pieces_num, l.set_quantity,
            COALESCE(ROUND(AVG(r.rating), 1), 0) as set_rating
        FROM LEGO_SET l
        LEFT JOIN REVIEW r ON l.set_id = r.set_id
        GROUP BY l.set_id, l.name, l.price, l.theme, l.pieces_num, l.set_quantity
    """
    cursor.execute(query)
    lego_sets = cursor.fetchall()
    
    # Fetch Pieces
    cursor.execute("""
        SELECT rp.*, ls.name as set_name 
        FROM REPLACEMENT_PIECE rp 
        JOIN LEGO_SET ls ON rp.set_id = ls.set_id
    """)
    pieces = cursor.fetchall()
    
    cursor.close()
    conn.close()

    # Calculate Cart Badge (Unique Items Count)
    cart = session.get('cart', {})
    # MODIFIED: Use len(cart) instead of sum(cart.values())
    cart_count = len(cart)
        
    return render_template('dashboard.html', user=session, lego_sets=lego_sets, pieces=pieces, cart_count=cart_count)

# 4. Submit Rating
@app.route('/submit_rating', methods=['POST'])
def submit_rating():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401

    data = request.get_json()
    set_id = data.get('set_id')
    rating = data.get('rating')
    user_id = session['user_id']
    today = date.today()

    if not set_id or not rating:
        return jsonify({"status": "error", "message": "Missing set_id or rating"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT MAX(review_id) as max_id FROM REVIEW")
        result = cursor.fetchone()
        max_id = result['max_id']
        
        if max_id is None:
            new_review_id = 1
        else:
            new_review_id = int(max_id) + 1

        query = "INSERT INTO REVIEW (review_id, rating, set_id, user_id, review_date) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(query, (new_review_id, rating, set_id, user_id, today))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({"status": "success", "message": "Rating saved!"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 5. Add To Cart
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401

    data = request.get_json()
    item_type = data.get('type') # 'set' or 'piece'
    item_id = data.get('id')
    quantity = int(data.get('qty', 1))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check Stock Level in Database
    stock_available = 0
    if item_type == 'set':
        cursor.execute("SELECT set_quantity FROM LEGO_SET WHERE set_id = %s", (item_id,))
        result = cursor.fetchone()
        if result: stock_available = result['set_quantity']
    elif item_type == 'piece':
        cursor.execute("SELECT rp_quantity FROM REPLACEMENT_PIECE WHERE piece_id = %s", (item_id,))
        result = cursor.fetchone()
        if result: stock_available = result['rp_quantity']
    
    cursor.close()
    conn.close()

    cart = session.get('cart', {})
    cart_key = f"{item_type}_{item_id}"
    current_in_cart = cart.get(cart_key, 0)

    if (current_in_cart + quantity) > stock_available:
        return jsonify({
            "status": "error", 
            "message": f"Not enough stock! You have {current_in_cart} in cart, only {stock_available} available."
        })

    # Add to session cart
    cart[cart_key] = current_in_cart + quantity
    session['cart'] = cart
    session.modified = True 

    # MODIFIED: Return unique item count (len) instead of total quantity (sum)
    new_total = len(cart)
    
    return jsonify({"status": "success", "cart_count": new_total})

# 6. Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))

# 7. Test Route
@app.route('/test_db')
def test_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE() as db_name;")
        result = cursor.fetchone()
        cursor.execute("SHOW TABLES;")
        tables = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "db": result['db_name'], "tables": tables})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(debug=True)