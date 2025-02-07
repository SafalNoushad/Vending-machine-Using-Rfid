from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
import threading
from flask_cors import CORS
import logging
import traceback

app = Flask(__name__)
CORS(app)

# Dummy admin credentials
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin'

def get_db_connection():
    conn = sqlite3.connect('your_database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Function to execute a query and fetch all results
def query_db(query, args=(), one=False):
    conn = get_db_connection()
    cur = conn.execute(query, args)
    rv = cur.fetchall()
    cur.close()
    conn.close()
    return (rv[0] if rv else None) if one else rv

# Route to render the login page
@app.route('/')
def login():
    return render_template('login.html')

# Route to handle login form submission
@app.route('/login', methods=['POST'])
def login_post():
    username = request.form.get('username')
    password = request.form.get('password')

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        # Successful login, redirect to admin dashboard
        return redirect(url_for('dashboard'))
    else:
        # Failed login, render login page with error message
        error_message = "Invalid username or password"
        return render_template('login.html', error_message=error_message)

@app.route('/dashboard')
def dashboard():
    try:
        # Fetch users, products, and transactions data from the database
        users = get_users()
        products = query_db('SELECT * FROM product')
        transactions = query_db('SELECT * FROM transactions')
        return render_template('dashboard.html', users=users, products=products, transactions=transactions)
    except Exception as e:
        return render_template('error.html', error=str(e)), 500



# Route to handle adding users
@app.route('/add_user', methods=['POST'])
def add_user():
    try:
        rfid = request.form['rfid']
        name = request.form['name']
        conn = get_db_connection()
        conn.execute('INSERT INTO user (rfid, name) VALUES (?, ?)', (rfid, name))
        conn.commit()
        return redirect(url_for('dashboard'))
    except Exception as e:
        return jsonify(error=str(e)), 500
    
# Function to fetch users from the database
def get_users():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM user').fetchall()
    conn.close()
    return users

# Route to handle deleting users
@app.route('/delete_user', methods=['POST'])
def delete_user():
    try:
        user_id = request.json['id']
        conn = get_db_connection()
        conn.execute('DELETE FROM user WHERE rfid = ?', (user_id,))
        conn.commit()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/add_product', methods=['POST'])
def add_product():
    try:
        product_id = request.form['productId']
        expiry_date = request.form['expiryDate']
        price = float(request.form['price'])  # Convert price to float
        conn = get_db_connection()
        conn.execute('INSERT INTO product (product_id, expiry_date, price) VALUES (?, ?, ?)', (product_id, expiry_date, price))
        conn.commit()
        return redirect(url_for('dashboard'))
    except Exception as e:
        return jsonify(error=str(e)), 500

# Route to fetch existing products
@app.route('/get_products')
def get_products():
    try:
        products = query_db('SELECT * FROM product')
        # Convert the rows to a list of dictionaries
        product_list = [{'product_id': product['product_id'], 'expiry_date': product['expiry_date'], 'price': product['price']} for product in products]
        return jsonify(product_list)
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/validate_rfid', methods=['POST'])
def validate_rfid():
    try:
        # Get the RFID tag from the request
        rfid = request.json['rfid']
        
        # Query the database for the RFID tag
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM user WHERE rfid = ?', (rfid,))
        user = cursor.fetchone()
        
        if user:
            # If the RFID tag exists in the database, return a valid response
            return jsonify(valid=True, name=user['name'])
        else:
            # If the RFID tag doesn't exist in the database, return an invalid response
            return jsonify(valid=False), 401
    except Exception as e:
        # If an error occurs, return an error response
        return jsonify(error=str(e)), 500
    
qr_code_scanned = False

# Function to reset the flag after 15 seconds
def reset_flag():
    global qr_code_scanned
    qr_code_scanned = False

# Route to initiate QR code scanning
@app.route('/initiate', methods=['GET'])
def initiate_qr_scan():
    global qr_code_scanned
    
    # Set the flag to True
    qr_code_scanned = True
    
    # Create a timer to reset the flag after 15 seconds
    timer = threading.Timer(15.0, reset_flag)
    timer.start()
    
    # Return the response
    return jsonify(message="QR code scanning initiated. Flag set to True."), 200

# Route to check flag status
@app.route('/check_flag', methods=['GET'])
def check_flag():
    global qr_code_scanned
    return jsonify(flag=qr_code_scanned), 200


@app.route('/delete_product', methods=['POST'])
def delete_product():
    try:
        # Extract product ID from the request
        product_id = request.json['product_id']
        
        # Connect to the database
        conn = get_db_connection()
        
        # Delete the product with the given product ID
        conn.execute('DELETE FROM product WHERE product_id = ?', (product_id,))
        
        # Commit the changes
        conn.commit()
        
        # Close the database connection
        conn.close()
        
        # Return success response
        return jsonify(success=True)
    except Exception as e:
        # Return error response if an exception occurs
        return jsonify(error=str(e)), 500
    
@app.route('/get_user_name/<uid>', methods=['GET'])
def get_user_name(uid):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM user WHERE rfid = ?', (uid,))
        user = cursor.fetchone()
        conn.close()

        if user:
            return jsonify({'name': user['name']})
        else:
            return jsonify({'error': 'User not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    try:
        # Extract data from the request
        user_name = request.json['user_name']
        amount_paid = request.json['amount_paid']  # Convert to float
        product_id = request.json['product_id']    # Convert to integer
        
        # Connect to the database
        conn = get_db_connection()
        
        # Insert the transaction into the database using a parameterized query
        conn.execute('INSERT INTO transactions (user_name, amount_paid, product_id) VALUES (?, ?, ?)', (user_name, amount_paid, product_id))
        conn.commit()
        
        # Close the database connection
        conn.close()
        
        # Return a success response
        return jsonify(success=True), 200
    except Exception as e:
        return jsonify(error=str(e)), 500




@app.route('/get_transactions')
def get_transactions():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM transactions')
        transactions = cursor.fetchall()
        conn.close()

        transaction_list = []
        for transaction in transactions:
            transaction_dict = {
                'transaction_id': transaction['transaction_id'],
                'user_name': transaction['user_name'],
                'amount_paid': transaction['amount_paid'],
                'product_id': transaction['product_id']
            }
            transaction_list.append(transaction_dict)

        return jsonify(transaction_list)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/clear_transactions', methods=['POST'])
def clear_transactions():
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM transactions')  # Delete all rows from the transactions table
        conn.commit()
        conn.close()
        return jsonify(success=True), 200
    except Exception as e:
        return jsonify(error=str(e)), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
