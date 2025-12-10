import os
import pymysql
from datetime import date, timedelta
from flask import Flask, jsonify, render_template, request, redirect, url_for, session
from dotenv import load_dotenv

# ------------------------------------------------------------------
# ROBUST CONFIGURATION LOADING
# ------------------------------------------------------------------
try:
    basedir = os.path.abspath(os.path.dirname(__file__))
except NameError:
    basedir = os.getcwd()

config_path = os.path.join(basedir, 'config.env')
if not os.path.exists(config_path):
    config_path = os.path.join(basedir, '.env')

load_dotenv(config_path)

app = Flask(__name__)
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

# Landing Page (Login)
@app.route('/', methods=['GET', 'POST'])
def landing():
    error = None
    if request.method == 'POST':
        user_id = request.form['user_id']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM USERS WHERE user_id = %s AND password = %s", (user_id, password))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if user:
            session['user_id'] = user['user_id']
            session['name'] = user['name']
            if 'cart' not in session:
                session['cart'] = {}
            
            #admin check
            if user_id.lower() == 'admin':
                session['is_admin'] = True
                return redirect(url_for('admin_dashboard'))
            
            #normal user
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid User ID or Password. Please try again."
    return render_template('index.html', error=error)

# Create User Page
@app.route('/create_user', methods=['GET', 'POST'])
def create_user():
    if request.method == 'POST':
        user_id = request.form['user_id']
        password = request.form['password']
        name = request.form['name']
        address = request.form['address']
        age = request.form['age']
        user_balance = 0 
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            query = "INSERT INTO USERS (user_id, name, address, user_balance, age, password) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(query, (user_id, name, address, user_balance, age, password))
            conn.commit()
            
            cursor.close()
            conn.close()
            
            session['user_id'] = user_id
            session['name'] = name
            session['cart'] = {} 
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            return f"Error creating user: {str(e)}"

    prefill_id = request.args.get('new_id', '')
    return render_template('create_user.html', prefill_id=prefill_id)

# Dashboard
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('landing'))
    
    show_in_stock = request.args.get('stock') == 'on'
    sort_by = request.args.get('sort', 'default')
    max_price = request.args.get('price')
    active_tab = request.args.get('tab', 'sets')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch Lego Sets with Average Rating
    query_sets = """
        SELECT 
            l.set_id, l.name, l.price, l.theme, l.pieces_num, l.set_quantity,
            COALESCE(ROUND(AVG(r.rating), 1), 0) as set_rating,
            COUNT(DISTINCT os.order_item_id) as popularity
        FROM LEGO_SET l
        LEFT JOIN REVIEW r ON l.set_id = r.set_id
        LEFT JOIN ORDER_SET os ON l.set_id = os.set_id
        WHERE 1=1
    """
    params_sets = []

    # Apply Filters
    if show_in_stock:
        query_sets += " AND l.set_quantity > 0"
    
    if max_price:
        query_sets += " AND l.price <= %s"
        params_sets.append(float(max_price))

    query_sets += " GROUP BY l.set_id"

    # Apply Sorting
    if sort_by == 'popular':
        query_sets += " ORDER BY popularity DESC"
    elif sort_by == 'rating':
        query_sets += " ORDER BY set_rating DESC"
    else:
        # Default sort (e.g. by Name)
        query_sets += " ORDER BY l.name ASC"

    cursor.execute(query_sets, tuple(params_sets))
    lego_sets = cursor.fetchall()
    
    # Fetch Pieces
    query_pieces = """
        SELECT 
            rp.*, ls.name as set_name,
            COUNT(DISTINCT op.order_item_id) as popularity
        FROM REPLACEMENT_PIECE rp 
        JOIN LEGO_SET ls ON rp.set_id = ls.set_id
        LEFT JOIN ORDER_PIECE op ON rp.piece_id = op.piece_id
        WHERE 1=1
    """
    params_pieces = []

    if show_in_stock:
        query_pieces += " AND rp.rp_quantity > 0"
    
    if max_price:
        query_pieces += " AND rp.price <= %s"
        params_pieces.append(float(max_price))

    query_pieces += " GROUP BY rp.piece_id"

    if sort_by == 'popular':
        query_pieces += " ORDER BY popularity DESC"
    else:
        query_pieces += " ORDER BY rp.piece_id ASC"

    cursor.execute(query_pieces, tuple(params_pieces))
    pieces = cursor.fetchall()
    
    cursor.close()
    conn.close()

    cart = session.get('cart', {})
    cart_count = len(cart)
        
    return render_template('dashboard.html',
                        user=session, 
                        lego_sets=lego_sets, 
                        pieces=pieces, 
                        cart_count=cart_count,
                        current_stock=show_in_stock,
                        current_sort=sort_by,
                        current_price=max_price,
                        current_tab=active_tab)

# Profile Page
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('landing'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    user_id = session['user_id']
    
    # Fetch User Info (Real-time balance)
    cursor.execute("SELECT * FROM USERS WHERE user_id = %s", (user_id,))
    user_info = cursor.fetchone()
    
    # Fetch Past Orders
    cursor.execute("SELECT * FROM ORDERS WHERE user_id = %s ORDER BY order_date DESC", (user_id,))
    orders = cursor.fetchall()
    
    # Fetch Reviews
    cursor.execute("""
        SELECT r.*, l.name as set_name 
        FROM REVIEW r 
        JOIN LEGO_SET l ON r.set_id = l.set_id 
        WHERE r.user_id = %s 
        ORDER BY r.review_date DESC
    """, (user_id,))
    reviews = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('profile.html', user=user_info, orders=orders, reviews=reviews)

# Add Funds
@app.route('/add_funds', methods=['POST'])
def add_funds():
    if 'user_id' not in session:
        return redirect(url_for('landing'))
        
    try:
        amount = float(request.form.get('amount', '0'))
    except ValueError:
        amount = 0.0
    
    user_id = session['user_id']
    
    if amount > 0:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE USERS SET user_balance = user_balance + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
        cursor.close()
        conn.close()
    
    return redirect(url_for('profile'))

# Checkout Page
@app.route('/checkout')
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('landing'))

    cart = session.get('cart', {})
    if not cart:
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    
    user_id = session['user_id']
    
    # Fetch User Balance
    cursor.execute("SELECT user_balance FROM USERS WHERE user_id = %s", (user_id,))
    user_balance = cursor.fetchone()['user_balance']

    # Build detailed list of items in cart
    cart_items = []
    total_cost = 0

    for key, qty in cart.items():
        item_type, item_id = key.split('_')
        
        if item_type == 'set':
            cursor.execute("SELECT * FROM LEGO_SET WHERE set_id = %s", (item_id,))
            item = cursor.fetchone()
            if item:
                cost = float(item['price']) * qty
                cart_items.append({
                    'type': 'set',
                    'id': item['set_id'],
                    'name': item['name'],
                    'price': float(item['price']),
                    'qty': qty,
                    'total': cost
                })
                total_cost += cost
                
        elif item_type == 'piece':
            cursor.execute("""
                SELECT rp.*, ls.name as set_name 
                FROM REPLACEMENT_PIECE rp 
                JOIN LEGO_SET ls ON rp.set_id = ls.set_id
                WHERE rp.piece_id = %s
            """, (item_id,))
            item = cursor.fetchone()
            if item:
                cost = float(item['price']) * qty
                cart_items.append({
                    'type': 'piece',
                    'id': item['piece_id'],
                    'name': f"Piece from {item['set_name']}",
                    'price': float(item['price']),
                    'qty': qty,
                    'total': cost
                })
                total_cost += cost

    cursor.close()
    conn.close()

    return render_template('checkout.html', 
    cart_items=cart_items, 
    total_cost=total_cost, 
    user_balance=float(user_balance),
    can_afford=(float(user_balance) >= total_cost))

# Place Order
@app.route('/place_order', methods=['POST'])
def place_order():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401

    cart = session.get('cart', {})
    if not cart:
        return jsonify({"status": "error", "message": "Cart is empty"}), 400

    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Recalculate Total Cost to prevent tampering
        total_cost = 0
        items_to_process = []

        for key, qty in cart.items():
            item_type, item_id = key.split('_')
            
            if item_type == 'set':
                cursor.execute("SELECT price, set_quantity FROM LEGO_SET WHERE set_id = %s", (item_id,))
                item = cursor.fetchone()
                # Check stock again just in case
                if item['set_quantity'] < qty:
                    raise Exception(f"Not enough stock for set {item_id}")
                total_cost += float(item['price']) * qty
                items_to_process.append({'type': 'set', 'id': item_id, 'qty': qty, 'price': item['price']})
                
            elif item_type == 'piece':
                cursor.execute("SELECT price, rp_quantity FROM REPLACEMENT_PIECE WHERE piece_id = %s", (item_id,))
                item = cursor.fetchone()
                if item['rp_quantity'] < qty:
                    raise Exception(f"Not enough stock for piece {item_id}")
                total_cost += float(item['price']) * qty
                items_to_process.append({'type': 'piece', 'id': item_id, 'qty': qty, 'price': item['price']})

        # Check User Balance
        cursor.execute("SELECT user_balance FROM USERS WHERE user_id = %s", (user_id,))
        balance = float(cursor.fetchone()['user_balance'])
        
        if balance < total_cost:
            raise Exception("Insufficient funds")

        # Create Order
        # Get next order_id
        cursor.execute("SELECT MAX(order_id) as max_id FROM ORDERS")
        max_o_id = cursor.fetchone()['max_id']
        new_order_id = 1 if max_o_id is None else int(max_o_id) + 1
        
        today = date.today()
        arrival = today + timedelta(days=5) # Random 5 day shipping logic
        
        cursor.execute("""
            INSERT INTO ORDERS (order_id, order_date, user_id, order_arrival) 
            VALUES (%s, %s, %s, %s)
        """, (new_order_id, today, user_id, arrival))

        # Process Items (Insert into Order_Item and Deduct Stock)
        cursor.execute("SELECT MAX(order_item_id) as max_id FROM ORDER_ITEM")
        max_oi_id = cursor.fetchone()['max_id']
        current_oi_id = 1 if max_oi_id is None else int(max_oi_id) + 1

        for item in items_to_process:
            # Insert into Order_Item
            cursor.execute("""
                INSERT INTO ORDER_ITEM (order_item_id, order_item_quantity, price, order_id)
                VALUES (%s, %s, %s, %s)
            """, (current_oi_id, item['qty'], item['price'], new_order_id))

            # Link to Set or Piece table
            if item['type'] == 'set':
                cursor.execute("INSERT INTO ORDER_SET (order_item_id, set_id) VALUES (%s, %s)", (current_oi_id, item['id']))
                # Deduct Stock
                cursor.execute("UPDATE LEGO_SET SET set_quantity = set_quantity - %s WHERE set_id = %s", (item['qty'], item['id']))
            else:
                cursor.execute("INSERT INTO ORDER_PIECE (order_item_id, piece_id) VALUES (%s, %s)", (current_oi_id, item['id']))
                # Deduct Stock
                cursor.execute("UPDATE REPLACEMENT_PIECE SET rp_quantity = rp_quantity - %s WHERE piece_id = %s", (item['qty'], item['id']))
            
            current_oi_id += 1

        # Deduct User Balance
        cursor.execute("UPDATE USERS SET user_balance = user_balance - %s WHERE user_id = %s", (total_cost, user_id))

        conn.commit()
        cursor.close()
        conn.close()

        # Clear Cart
        session['cart'] = {}
        session.modified = True
        
        return jsonify({"status": "success"})

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

# Get Order Details API
@app.route('/get_order_details/<int:order_id>')
def get_order_details(order_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT 
            oi.order_item_quantity as quantity,
            oi.price,
            o.order_arrival,
            CASE 
                WHEN os.set_id IS NOT NULL THEN ls.name 
                WHEN op.piece_id IS NOT NULL THEN CONCAT('Piece from ', ls_p.name)
                ELSE 'Unknown Item'
            END as item_name
        FROM ORDER_ITEM oi
        JOIN ORDERS o ON oi.order_id = o.order_id
        LEFT JOIN ORDER_SET os ON oi.order_item_id = os.order_item_id
        LEFT JOIN LEGO_SET ls ON os.set_id = ls.set_id
        LEFT JOIN ORDER_PIECE op ON oi.order_item_id = op.order_item_id
        LEFT JOIN REPLACEMENT_PIECE rp ON op.piece_id = rp.piece_id
        LEFT JOIN LEGO_SET ls_p ON rp.set_id = ls_p.set_id
        WHERE oi.order_id = %s
    """
    
    cursor.execute(query, (order_id,))
    items = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify(items)

# Submit Rating
@app.route('/submit_rating', methods=['POST'])
def submit_rating():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401

    data = request.get_json()
    set_id = data.get('set_id')
    rating = data.get('rating')
    user_id = session['user_id']
    today = str(date.today()) # Cast to string for safety

    if not set_id or not rating:
        return jsonify({"status": "error", "message": "Missing set_id or rating"}), 400

    # Type safety to prevent errors
    try:
        set_id = int(set_id)
        rating = int(rating)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid data format"}), 400

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
        print(f"DB Error in submit_rating: {e}") # Print to terminal for debugging
        return jsonify({"status": "error", "message": str(e)}), 500

# Add To Cart
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401

    data = request.get_json()
    item_type = data.get('type')
    item_id = data.get('id')
    quantity = int(data.get('qty', 1))

    conn = get_db_connection()
    cursor = conn.cursor()

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

    cart[cart_key] = current_in_cart + quantity
    session['cart'] = cart
    session.modified = True 

    new_total = len(cart)
    
    return jsonify({"status": "success", "cart_count": new_total})

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))

# Test Route
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

@app.route('/admin')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('landing'))

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # --- STATISTICS ---
    
    # Total Revenue (Sum of all order items)
    cursor.execute("SELECT SUM(price * order_item_quantity) as total FROM ORDER_ITEM")
    revenue = cursor.fetchone()['total'] or 0
    
    # Most Popular Set (Most ordered)
    cursor.execute("""
        SELECT l.name, COUNT(*) as sales
        FROM ORDER_SET os
        JOIN LEGO_SET l ON os.set_id = l.set_id
        GROUP BY l.set_id
        ORDER BY sales DESC
        LIMIT 1
    """)
    popular_set = cursor.fetchone()
    
    # Low Stock Alert (Sets < 5)
    cursor.execute("SELECT name, set_quantity FROM LEGO_SET WHERE set_quantity < 5")
    low_stock_sets = cursor.fetchall()
    
    # Past Orders
    order_sort = request.args.get('order_sort', 'recent')
    
    base_query = """
        SELECT
            o.order_id,
            o.order_date,
            o.user_id,
            o.order_arrival,
            SUM(oi.price * oi.order_item_quantity) as total_cost,
            SUM(oi.order_item_quantity) as total_items
        FROM ORDERS o
        LEFT JOIN ORDER_ITEM oi ON o.order_id = oi.order_id
        GROUP BY o.order_id, o.order_date, o.user_id, o.order_arrival
    """
    
    if order_sort == 'expensive':
        base_query += " ORDER BY total_cost DESC"
    elif order_sort == 'items':
        base_query += " ORDER BY total_items DESC"
    else:
        # default sorts by most recent
        base_query += " ORDER BY o.order_date DESC"
    
    cursor.execute(base_query)
    past_orders = cursor.fetchall()
    
    # Fetch all items for inventory management dropdowns
    cursor.execute("SELECT set_id, name, set_quantity FROM LEGO_SET ORDER BY name")
    all_sets = cursor.fetchall()
    
    cursor.execute("""
        SELECT rp.piece_id, ls.name as set_name, rp.rp_quantity 
        FROM REPLACEMENT_PIECE rp
        JOIN LEGO_SET ls ON rp.set_id = ls.set_id
    """)
    all_pieces = cursor.fetchall()

    cursor.close()
    conn.close()
    
    return render_template('admin.html', 
                        revenue=revenue, 
                        popular_set=popular_set, 
                        low_stock=low_stock_sets, 
                        past_orders=past_orders,
                        all_sets=all_sets,
                        all_pieces=all_pieces,
                        current_order_sort=order_sort)

@app.route('/admin/add_set', methods=['POST'])
def admin_add_set():
    if not session.get('is_admin'): return redirect(url_for('landing'))
    
    set_id = request.form['set_id']
    name = request.form['name']
    price = request.form['price']
    theme = request.form['theme']
    pieces = request.form['pieces']
    qty = request.form['quantity']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO LEGO_SET (set_id, name, price, theme, pieces_num, set_quantity)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (set_id, name, price, theme, pieces, qty))
        conn.commit()
    except Exception as e:
        print("Error adding set:", e)
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add_piece', methods=['POST'])
def admin_add_piece():
    if not session.get('is_admin'): return redirect(url_for('landing'))
    
    piece_id = request.form['piece_id']
    set_id = request.form['parent_set_id']
    price = request.form['price']
    qty = request.form['quantity']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO REPLACEMENT_PIECE (piece_id, set_id, price, rp_quantity)
            VALUES (%s, %s, %s, %s)
        """, (piece_id, set_id, price, qty))
        conn.commit()
    except Exception as e:
        print("Error adding piece:", e)
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update_stock', methods=['POST'])
def admin_update_stock():
    if not session.get('is_admin'): return redirect(url_for('landing'))
    
    item_type = request.form['type'] # 'set' or 'piece'
    item_id = request.form['item_id']
    new_qty = request.form['new_quantity']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if item_type == 'set':
            cursor.execute("UPDATE LEGO_SET SET set_quantity = %s WHERE set_id = %s", (new_qty, item_id))
        else:
            cursor.execute("UPDATE REPLACEMENT_PIECE SET rp_quantity = %s WHERE piece_id = %s", (new_qty, item_id))
        conn.commit()
    except Exception as e:
        print("Error updating stock:", e)
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
    
