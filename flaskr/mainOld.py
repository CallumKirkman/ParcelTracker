import logging
import pyrebase
import os
import pymysql

from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for

import firebase_admin
from firebase_admin import credentials, firestore

from pymongo import MongoClient

app = Flask(__name__)

# TODO: Fix databases

# Firebase details
firebaseConfig = {
    "apiKey": "AIzaSyBIYDxM_WvnjhiSL5SSZEM_mRsYelfvFgk",
    "authDomain": "ck-ad-1.firebaseapp.com",
    "projectId": "ck-ad-1",
    "storageBucket": "ck-ad-1.appspot.com",
    "messagingSenderId": "695010505553",
    "appId": "1:695010505553:web:c8594855c4a3a6734a1970",
    "measurementId": "G-G8SD0BZYBJ",
    "databaseURL": "",
}

# Initialize firebase
firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()

# Initialize firestore
cred = credentials.Certificate("ck-ad-1-firebase-adminsdk-szo9b-4294d0a5ab.json")
firebase_admin.initialize_app(cred)
# initialize firestore instance
firestoreDB = firestore.client()


# Initialize mongoDB
def open_mongodb_connection():
    if os.environ.get('GAE_ENV') == 'standard':
        mongo_username = os.environ.get('MONGO_DB_USERNAME')
        mongo_password = os.environ.get('MONGO_DB_PASSWORD')
    else:
        load_dotenv()
        mongo_username = os.getenv('MONGO_DB_USERNAME')
        mongo_password = os.getenv('MONGO_DB_PASSWORD')

    client_connection_string = (
        "mongodb+srv://mainUser:mainPassword@cluster.ktjzqqr.mongodb.net/parcelDatabase?retryWrites=true&w=majority")
    print(client_connection_string)
    cluster = MongoClient(client_connection_string)
    mongo_db = cluster["order-database"]
    order_collection = mongo_db["orders"]

    return order_collection


# Product SQL connect to database
def open_cloudsql_connection():
    try:
        # When deployed to App Engine, the `GAE_ENV` environment variable will be set to `standard`
        if os.environ.get('GAE_ENV') == 'standard':
            db_user = os.environ.get('CLOUD_SQL_USERNAME')
            db_password = os.environ.get('CLOUD_SQL_PASSWORD')
            db_name = os.environ.get('CLOUD_SQL_DATABASE_NAME')
            db_connection_name = os.environ.get('CLOUD_SQL_CONNECTION_NAME')

            # If deployed, use the local socket interface for accessing Cloud SQL
            unix_socket = '/cloudsql/{}'.format(db_connection_name)
            cnx = pymysql.connect(user=db_user, password=db_password, unix_socket=unix_socket, db=db_name,
                                  cursorclass=pymysql.cursors.DictCursor)
        else:
            load_dotenv()
            db_user = os.getenv('CLOUD_SQL_USERNAME')
            db_password = os.getenv('CLOUD_SQL_PASSWORD')
            db_name = os.getenv('CLOUD_SQL_DATABASE_NAME')

            # If running locally, use the TCP connections instead
            # Set up Cloud SQL Proxy (cloud.google.com/sql/docs/mysql/sql-proxy)
            host = '127.0.0.1'
            port = 1433
            cnx = pymysql.connect(user=db_user, password=db_password, host=host, port=port, db=db_name,
                                  cursorclass=pymysql.cursors.DictCursor)

    except pymysql.MySQLError as e:
        return e

    return cnx


# Product SQL get data
def get_data(item, table, column, column_id):
    cnx = open_cloudsql_connection()

    with cnx.cursor() as cursor:
        if column is None:
            # Get everything
            fetched_items = cursor.execute('select %s from %s;' % (item, table))
            items = cursor.fetchall()
        else:
            # Get specific entry
            fetched_items = cursor.execute("select * from %s where %s='%s';" % (table, column, column_id))
            items = cursor.fetchone()
    if fetched_items > 0:
        return items
    else:
        got_items = 'No items in DB'
        return got_items


# Product SQL create data
def create_data(table, item_id, item_name, item):
    cnx = open_cloudsql_connection()
    with cnx.cursor() as cursor:
        cursor.execute('INSERT INTO %s (%s, %s) VALUES(%s, %s)' % (table, item_id, item_name, item["4"], item["test"]))
    cnx.commit()
    cnx.close()


# Initialise person as dictionary
person = {"is_logged_in": False, "name": "", "email": "", "uid": "", "address": "", "picture": "", "admin": False}
idToken = ""


@app.context_processor
def inject_status():
    return dict(logg_status=person["is_logged_in"], name=person["name"], email=person["email"], uid=person["uid"],
                address=person["address"], picture=person["picture"], admin=person["admin"])


@app.route('/')
@app.route('/home')
def home():
    if person["is_logged_in"]:
        return render_template("user_home.html")
    else:
        return render_template("home.html")


@app.route('/product')
def product():
    products = get_data("*", "product", None, None)

    return render_template('product.html', products=products)


@app.route('/tracking')
def tracking():
    order_collection = open_mongodb_connection()

    if person["admin"]:
        order_find = order_collection.find()
    else:
        order_find = order_collection.find({"order.uid": person["uid"]})

    orders = []
    for order in order_find:
        orders.append(order)

    if len(orders) == 0:
        orders = "No current orders"

    return render_template('tracking.html', orders=orders)


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/account')
def account():
    # Get the data of the active user
    account_data = firestoreDB.collection(u'users').document(person["uid"]).get()
    account_data = account_data.to_dict()
    # "name": name, "email": email, "address": address, "picture": picture, "admin": admin

    # Update the data of the active user
    person["name"] = account_data["name"]
    person["email"] = account_data["email"]
    person["address"] = account_data["address"]
    person["picture"] = account_data["picture"]

    return render_template('account.html')


@app.route('/delete-account')
def delete_account():
    # Delete user information
    firestoreDB.collection(u'users').document(person["uid"]).delete()

    # Delete user account
    auth.delete_user_account(idToken)

    return redirect(url_for('logout'))


@app.route('/update-account', methods=["POST", "GET"])
def update_account():
    if request.method == "POST":  # Only if data has been posted
        request_result = request.form  # Get the data
        name = request_result["name"]
        email = request_result["email"]
        address = request_result["address"]
        picture = request_result["picture"]

        if name == "":
            name = person["name"]
        if email == "":
            email = person["email"]
        if address == "":
            address = person["address"]
        if picture == "":
            picture = person["picture"]

        user_info = {"name": name, "email": email, "address": address, "picture": picture}

        firestoreDB.collection(u'users').document(person["uid"]).set(user_info, merge=True)

        return redirect(url_for('home'))

    else:
        return redirect(url_for('error_found'))


@app.route('/checkout')
def checkout():
    item_location = firestoreDB.collection(u'users').document(person["uid"]).collection(u'basket').stream()
    items = []
    checkout_price = 0
    for item in item_location:
        items.append(item.to_dict())
        price = item.to_dict()
        checkout_price = checkout_price + price["total_price"]

    if len(items) == 0:
        items = "No items in cart"

    return render_template('checkout.html', items=items, checkout_price=checkout_price)


@app.route('/create-order')
def create_order():
    order_collection = open_mongodb_connection()

    item_location = firestoreDB.collection(u'users').document(person["uid"]).collection(u'basket').stream()
    date = datetime.today().strftime('%d-%m-%y')
    items = []
    checkout_price = 0
    for item in item_location:
        items.append(item.to_dict())
        price = item.to_dict()
        checkout_price = checkout_price + price["total_price"]
        item.reference.delete()

    order = {"uid": person["uid"], "items": items, "orderPrice": checkout_price, "date": date,
             "progress": "processing"}

    order_collection.insert_one({"order": order})

    return redirect(url_for('tracking'))


@app.route('/empty')
def empty_cart():
    item_location = firestoreDB.collection(u'users').document(person["uid"]).collection(u'basket').stream()
    for item in item_location:
        item.reference.delete()

    return redirect(url_for('product'))


@app.route('/add-to-cart', methods=['POST'])
def add_product_to_cart():
    try:
        quantity = int(request.form['quantity'])
        code = request.form['code']
        # Validate the received values
        if quantity and code and request.method == 'POST':
            row = get_data("*", "product", "code", code)

            # Update new quantity & add total price
            row = {'name': row['name'], 'code': row['code'], 'image': row['image'], 'quantity': quantity,
                   'price': row['price'], 'total_price': quantity * row['price']}

            # Check if item already in basket
            ref = firestoreDB.collection(u'users').document(person["uid"]).collection(u'basket').document(
                row["name"]).get()
            if ref.exists:
                # Update quantity & add total price
                ref = ref.to_dict()
                basket_quantity = int(row["quantity"]) + int(ref["quantity"])

                row = {'name': row['name'], 'code': row['code'], 'image': row['image'], 'quantity': basket_quantity,
                       'price': row['price'], 'total_price': basket_quantity * row['price']}

                firestoreDB.collection(u'users').document(person["uid"]).collection(u'basket').document(row["name"]) \
                    .set(row, merge=True)
            else:
                # Add item
                firestoreDB.collection(u'users').document(person["uid"]).collection(u'basket').document(
                    row["name"]).set(row)

            return redirect(url_for('product'))
        else:
            return redirect(url_for('error_found'))
    except Exception as e:
        print(e)


# If someone clicks on login, they are redirected to /login
@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "POST":  # Only if data has been posted
        request_result = request.form  # Get the data
        email = request_result["email"]
        password = request_result["pass"]
        try:
            # Try signing in the user with the given information
            user = auth.sign_in_with_email_and_password(email, password)

            global idToken
            idToken = user["idToken"]

            # Add data to global person
            global person
            person["is_logged_in"] = True
            person["email"] = user["email"]
            person["uid"] = user["localId"]

            # Get the data of the user
            login_data = firestoreDB.collection(u'users').document(person["uid"]).get()
            login_data = login_data.to_dict()
            # "name": name, "email": email, "address": address, "picture": picture, "admin": admin

            person["name"] = login_data["name"]
            person["address"] = login_data["address"]
            person["picture"] = login_data["picture"]
            person["admin"] = login_data["admin"]

        except:
            # If there is any error, redirect to error
            return redirect(url_for('error_found'))
        else:
            # To home page
            return redirect(url_for('home'))
    else:
        if person["is_logged_in"]:
            return redirect(url_for('home'))
        else:
            return redirect(url_for('error_found'))


# If someone clicks on signup, they are redirected to /signup
@app.route("/signup", methods=["POST", "GET"])
def signup():
    if request.method == "POST":  # Only listen to POST
        request_result = request.form  # Get the data submitted
        name = request_result["name"]
        email = request_result["email"]
        password = request_result["pass"]
        confirm_password = request_result["confPass"]
        if password == confirm_password:
            try:
                # Try creating the user account using the provided data
                auth.create_user_with_email_and_password(email, password)
                # Login the user
                user = auth.sign_in_with_email_and_password(email, password)

                global idToken
                idToken = user["idToken"]

                # Add data to global person
                global person
                person["is_logged_in"] = True
                person["name"] = name
                person["email"] = user["email"]
                person["uid"] = user["localId"]
                person["address"] = "Add address"
                person["picture"] = "/static/assets/user.png"
                person["admin"] = False

                # Append data to the firebase realtime database
                signup_data = {"name": name, "email": email, "address": person["address"], "picture": person["picture"],
                               "admin": person["admin"]}
                firestoreDB.collection(u'users').document(person["uid"]).set(signup_data)
            except:
                # If there is any error, redirect to error
                return redirect(url_for('error_found'))
            else:
                # To home page
                return redirect(url_for('home'))
    else:
        if person["is_logged_in"]:
            return redirect(url_for('home'))
        else:
            return redirect(url_for('error_found'))


@app.route('/logout')
def logout():
    # Reset global variables
    global idToken
    idToken = ""

    global person
    person = {"is_logged_in": False, "name": "", "email": "", "uid": "", "address": "", "picture": "", "admin": False}

    return redirect(url_for('home'))


@app.errorhandler(500)
def server_error(e):
    # Log the error and stacktrace.
    logging.exception('An error occurred during a request.')
    return render_template('404.html'), 500


@app.route('/error')
def error_found():
    # Log the error and stacktrace.
    logging.exception('An error occurred during a request.')
    return render_template('404.html')


if __name__ == '__main__':
    app.run()
