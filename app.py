from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime
import random
import sqlite3
import stripe
import os
from dotenv import load_dotenv
import base64

load_dotenv()

# Set Stripe secret API key from environment
stripe.api_key = os.getenv('sk_test_51MMDkGE28d0n3i0slrtdPvDR3gJLEj88uWvFXvFi9h9n80YlAHKJNfHKkktbwJpE2RpCqO4OvUaSmWmEfwmWAfeS00DaTEfYZp')

app = Flask(__name__)

stripe.api_key = "sk_test_51MMDkGE28d0n3i0slrtdPvDR3gJLEj88uWvFXvFi9h9n80YlAHKJNfHKkktbwJpE2RpCqO4OvUaSmWmEfwmWAfeS00DaTEfYZp"

def encode_to_base64(value):
    """Encodes a string to Base64 (URL-safe)."""
    return base64.urlsafe_b64encode(value.encode()).decode()

def decode_from_base64(value):
    """Decodes a Base64 string."""
    return base64.urlsafe_b64decode(value.encode()).decode()

def get_db_connection():
    conn = sqlite3.connect('rossbay.db')
    conn.row_factory = sqlite3.Row
    return conn

def create_payment_intent(amount, currency='gbp', payment_method_types=None):
    if payment_method_types is None:
        payment_method_types = ['card']
    try:
        payment_intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Convert to cents
            currency=currency,
            payment_method_types=payment_method_types
        )
        return payment_intent
    except Exception as e:
        raise e

@app.context_processor
def utility_processor():
    return dict(encode_to_base64=encode_to_base64)

# Route for the home page
@app.route('/')
def home():
    return redirect(url_for('login'))

# Route for the login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if the entered credentials exist in the database
        cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
        user = cursor.fetchone()

        conn.close()

        if user:
            enc_fname = encode_to_base64(user['fname'])
            enc_userid = encode_to_base64(user['userid'])
            return redirect(url_for('homepage', enc_fname=enc_fname, enc_userid=enc_userid))
        else:
            return "Invalid username or password"

    return render_template('login.html')

# Route for the registration page
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fname = request.form['fname']
        lname = request.form['lname']
        username = request.form['username']
        if "@rossall.org.uk" not in username:
            return 'Invalid email address'
        password = request.form['password']
        userid = str(random.randint(1000000000, 9999999999))

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if the username already exists
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            return 'Username already exists!'

        # Insert new user
        cursor.execute('INSERT INTO users (fname, lname, username, password, userid) VALUES (?, ?, ?, ?, ?)', 
                       (fname, lname, username, password, userid))
        conn.commit()
        conn.close()

        return redirect(url_for('login'))
    
    return render_template('register.html')

# Route for the order page
@app.route('/order/<enc_fname>/<enc_userid>/<storeid>', methods=['GET', 'POST'])
def order(enc_fname, enc_userid, storeid):
    try:
        fname = decode_from_base64(enc_fname)
        userid = decode_from_base64(enc_userid)
    except Exception:
        return "Invalid URL parameters", 400
    menulist = []

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM menulist WHERE storeid = ?',(storeid,))
    menulist = cursor.fetchall()

    cursor.execute('SELECT * FROM stores WHERE storeid = ?',(storeid,))
    store = cursor.fetchone()

    if store:
        storename = store['store']
    else: storename = "Store not found"

    if request.method == 'POST':
        selected_items = request.form.getlist('order_items')  # Selected items
        action = request.form.get('action')  # Determine if it's 'add' or 'submit'
        

        if action == 'add':
            # Handle "Add to Order" action - insert into a pending order table
            for item in selected_items:
                quantity = request.form.get(f'quantity_{item}')  # Get the corresponding quantity
                if quantity:  # Ensure the quantity is provided
                    cursor.execute('INSERT INTO pending_orders (userid, storeid, item, quantity) VALUES (?, ?, ?, ?)', 
                                   (userid, storeid, item, int(quantity)))
            conn.commit()

            return redirect(url_for('order', enc_fname=enc_fname, enc_userid=enc_userid, storeid=storeid))

        elif action == 'submit':
            return redirect(url_for('ordersum', enc_fname=enc_fname, enc_userid=enc_userid))

        return redirect(url_for('homepage', enc_fname=enc_fname, enc_userid=enc_userid))

    return render_template('order.html', fname=fname, userid=userid, storeid=storeid, menulist=menulist, storename=storename, enc_userid=enc_userid, enc_fname=enc_fname)

@app.route('/listedorder', methods=['GET', 'POST'])
def listedorder():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Query to fetch all orders
    cursor.execute('''
        SELECT 
            orders.orderid,
            GROUP_CONCAT(DISTINCT stores.store) AS storenames,
            SUM(menulist.price * orders.quantity) AS total_price
        FROM orders
        JOIN stores ON orders.storeid = stores.storeid
        JOIN menulist ON orders.item = menulist.item
        GROUP BY orders.orderid;
    ''')  # No parameters required

    # Fetch results
    result = cursor.fetchall()
    
    # Transform rows into dictionaries
    compiled_orders = [dict(row) for row in result]
    
    conn.close()
    
    return render_template('listedorder.html', rows=compiled_orders)  # Or render a template with this data



@app.route('/ordersum/<enc_fname>/<enc_userid>', methods=['GET', 'POST'])
def ordersum(enc_fname, enc_userid):
    try:
        fname = decode_from_base64(enc_fname)
        userid = decode_from_base64(enc_userid)
    except Exception:
        return "Invalid URL parameters", 400
    pending_orders = []
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT po.storeid, po.item, po.quantity, s.store AS storename, m.price
        FROM pending_orders po
        JOIN stores s ON po.storeid = s.storeid
        JOIN menulist m ON po.storeid = m.storeid AND po.item = m.item
        WHERE po.userid = ?
    ''', (userid,))
    
    pending_orders = cursor.fetchall()

    cursor.execute('''
        SELECT SUM(po.quantity * m.price)
        FROM pending_orders po
        JOIN menulist m ON po.storeid = m.storeid AND po.item = m.item
        WHERE po.userid = ?
    ''', (userid,))
    
    ordertotal = cursor.fetchone()[0]

    if ordertotal is None:
        ordertotal = 0
    else:
        ordertotal = round(ordertotal, 2)
    

    
    conn.close()

    return render_template('ordersum.html', enc_fname=enc_fname, enc_userid=enc_userid, fname=fname, userid=userid, pending_orders=pending_orders, ordertotal=ordertotal)

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'POST':
        userid = request.form['userid']
        house = request.form['house']
        extracost = request.form['extracost']
        extradesc = request.form['extradesc']
        orderpass = random.randint(1000,9999)

        conn = sqlite3.connect('rossbay.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO temp_ordersext (userid, desc, descost, house, orderpass) VALUES (?, ?, ?, ?, ?)',
                       (userid, house, extracost, extradesc, orderpass))
        conn.commit()
        conn.close()

        return redirect(url_for('create_checkout_session'))

    return render_template('ordersum.html')

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    userid = request.form['userid']  # Get the user ID
    fname = request.form['fname']  # Get the user's first name
    enc_userid = encode_to_base64(userid)
    enc_fname = encode_to_base64(fname)
    price_in_gbp = int(ordertotal * 100)  # Convert to pence (for GBP)
    

    conn = get_db_connection()
    cursor = conn.cursor()

        # Retrieve the total cost for the order
    cursor.execute('SELECT descost FROM temp_ordersext WHERE userid = ?', (userid,))
    descost = cursor.fetchone()['descost']
    ordertotal = float(request.form['ordertotal'])

    try:
        # Create a Stripe Checkout Session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'gbp',  # Set your currency
                    'product_data': {
                        'name': 'Order from Cart',  # Customize this description
                    },
                    'unit_amount': int((price_in_gbp + descost) * 100),  # Amount in pence
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f'http://127.0.0.1:5000/payment-success/{enc_fname}/{enc_userid}',  # Redirect on success
            cancel_url=f'http://127.0.0.1:5000/payment-failed?fname={enc_fname}',  # Redirect on failure
        )

        # Return the session URL to the frontend for redirection
        return jsonify({'url': session.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 403

@app.route('/delete_order', methods=['POST'])
def delete_order():

    item = request.form.get('item')
    storeid = request.form.get('storeid')
    userid = request.form.get('userid')
    fname = request.form.get('fname')
    

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Delete the specific order from the pending_orders table
    cursor.execute('''
        DELETE FROM pending_orders
        WHERE item = ? AND storeid = ? AND userid = ?
    ''', (item, storeid, userid))
    
    conn.commit()
    conn.close()
    
    # Redirect back to the ordersum page
    return redirect(url_for('ordersum', fname=fname, userid=userid))

@app.route('/payment-success/<enc_fname>/<enc_userid>')
def payment_success(enc_fname, enc_userid):
    try:
        fname = decode_from_base64(enc_fname)
        userid = decode_from_base64(enc_userid)
    except Exception:
        return "Invalid URL parameters", 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Process all pending orders for the user
        cursor.execute('SELECT * FROM pending_orders WHERE userid = ?', (userid,))
        pending_orders = cursor.fetchall()

        if not pending_orders:
            return redirect(url_for('homepage', enc_fname=enc_fname, enc_userid=enc_userid))

        for order in pending_orders:
            orderid = f"{datetime.now().strftime('%y%m%d%H%M')}{random.randint(100, 999)}{userid[-3:]}"
            cursor.execute('''
                INSERT INTO orders (orderid, userid, storeid, item, quantity)
                VALUES (?, ?, ?, ?, ?)
            ''', (orderid, order['userid'], order['storeid'], order['item'], order['quantity']))

        # Clear pending orders after processing
        cursor.execute('DELETE FROM pending_orders WHERE userid = ?', (userid,))
        conn.commit()

        # Redirect to homepage with the correct fname
        return redirect(url_for('homepage', enc_fname=enc_fname, enc_userid=enc_userid))
    
    except Exception as e:
        conn.rollback()
        return f"An error occurred: {str(e)}", 500

    finally:
        conn.close()




@app.route('/payment-failed')
def payment_failed():
    return render_template('failure.html')


@app.route('/homepage/<enc_fname>/<enc_userid>')
def homepage(enc_fname, enc_userid):
    try:
        fname = decode_from_base64(enc_fname)
        userid = decode_from_base64(enc_userid)
    except Exception:
        return "Invalid URL parameters", 400
    return render_template('homepage.html', fname=fname, userid=userid)



if __name__ == '__main__':
    app.run(debug=True)
