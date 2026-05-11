import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from models import db, Product, User, Wishlist, PushSubscription
from dotenv import load_dotenv
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth
from pywebpush import webpush, WebPushException
from flask_mail import Mail, Message
import threading
from bot import start_bot

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///boutique.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-123')

# Base URL for external links (Notifications)
BASE_URL = os.getenv('BASE_URL', 'http://127.0.0.1:5000').rstrip('/')

# Mail Configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', os.getenv('MAIL_USERNAME'))

mail = Mail(app)

# VAPID Keys for Push
app.config['VAPID_PUBLIC_KEY'] = os.getenv('VAPID_PUBLIC_KEY', 'MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAExFzXEVgQw1233Uw14Y3PIVgo2ALRZZZL/6vB9rubCC5a49giYTSauezJgBKC/bFczfbzv4mE5rx5r4pVS7AVUg==')
app.config['VAPID_PRIVATE_KEY'] = os.getenv('VAPID_PRIVATE_KEY')

# Support Constants
CONTACT_PHONE = "9840996011"
CONTACT_EMAIL = "sowarnalatha@gmail.com"
WHATSAPP_NUMBER = "919840996011"

db.init_app(app)

# Login Manager
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# OAuth Configuration
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# Create database tables
with app.app_context():
    db.create_all()

@app.route('/')
@login_required
def index():
    q = request.args.get('q')
    category = request.args.get('category')
    
    query = Product.query
    if q:
        query = query.filter(Product.name.contains(q) | Product.description.contains(q))
    if category:
        query = query.filter(Product.category == category)
        
    products = query.order_by(Product.created_at.desc()).all()
    categories = db.session.query(Product.category).distinct().all()
    categories = [c[0] for c in categories]
    
    wishlist_ids = []
    if current_user.is_authenticated:
        wishlist_ids = [w.product_id for w in Wishlist.query.filter_by(user_id=current_user.id).all()]
    
    return render_template('index.html', products=products, categories=categories, wishlist_ids=wishlist_ids, contact_phone=CONTACT_PHONE, contact_email=CONTACT_EMAIL)

@app.route('/product/<int:product_id>')
@login_required
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    
    is_in_wishlist = False
    if current_user.is_authenticated:
        is_in_wishlist = Wishlist.query.filter_by(user_id=current_user.id, product_id=product_id).first() is not None
    
    return render_template('product_detail.html', product=product, whatsapp_number=WHATSAPP_NUMBER, is_in_wishlist=is_in_wishlist, contact_phone=CONTACT_PHONE, contact_email=CONTACT_EMAIL)

# Auth Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid email or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # New Detailed Fields
        phone_code = request.form.get('phone_code', '+91')
        phone = request.form.get('phone')
        house_no = request.form.get('house_no')
        street = request.form.get('street')
        state = request.form.get('state')
        country = request.form.get('country')
        postal_code = request.form.get('postal_code')
        
        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash('Email already registered')
            return redirect(url_for('register'))
            
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password, method='scrypt'),
            phone_code=phone_code,
            phone=phone,
            house_no=house_no,
            street=street,
            state=state,
            country=country,
            postal_code=postal_code
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Google Login
@app.route('/login/google')
def login_google():
    redirect_uri = url_for('google_authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def google_authorize():
    token = google.authorize_access_token()
    user_info = token.get('userinfo')
    if user_info:
        user = User.query.filter_by(email=user_info['email']).first()
        if not user:
            user = User(
                username=user_info['name'],
                email=user_info['email'],
                google_id=user_info['sub'],
                profile_pic=user_info['picture']
            )
            db.session.add(user)
            db.session.commit()
        login_user(user)
    return redirect(url_for('index'))

# Wishlist Routes
@app.route('/wishlist')
@login_required
def wishlist():
    wishlist_items = Wishlist.query.filter_by(user_id=current_user.id).all()
    products = [item.product for item in wishlist_items]
    return render_template('wishlist.html', products=products, contact_phone=CONTACT_PHONE, contact_email=CONTACT_EMAIL)

@app.route('/wishlist/toggle/<int:product_id>')
@login_required
def toggle_wishlist(product_id):
    item = Wishlist.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if item:
        db.session.delete(item)
        flash('Removed from wishlist')
    else:
        new_item = Wishlist(user_id=current_user.id, product_id=product_id)
        db.session.add(new_item)
        flash('Added to wishlist!')
    db.session.commit()
    return redirect(request.referrer or url_for('index'))

# Push Notification Routes
@app.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    subscription_info = request.json
    if not subscription_info:
        return jsonify({'error': 'No subscription info provided'}), 400
    
    # Check if subscription already exists for this user
    existing = PushSubscription.query.filter_by(user_id=current_user.id, subscription_json=json.dumps(subscription_info)).first()
    if not existing:
        new_sub = PushSubscription(user_id=current_user.id, subscription_json=json.dumps(subscription_info))
        db.session.add(new_sub)
        db.session.commit()
    
    return jsonify({'status': 'success'})

def send_push_notification(user, title, body, url=None):
    subscriptions = PushSubscription.query.filter_by(user_id=user.id).all()
    results = []
    
    # Default URL if none provided
    if not url:
        url = BASE_URL + "/"

    for sub in subscriptions:
        try:
            webpush(
                subscription_info=json.loads(sub.subscription_json),
                data=json.dumps({
                    'title': title,
                    'body': body,
                    'url': url
                }),
                vapid_private_key=os.getenv('VAPID_PRIVATE_KEY'),
                vapid_claims={"sub": f"mailto:{CONTACT_EMAIL}"}
            )
            results.append(True)
        except WebPushException as ex:
            print(f"WebPush error: {ex}")
            results.append(False)
    return results

bot_thread = threading.Thread(target=start_bot)
bot_thread.daemon = True
bot_thread.start()

if __name__ == '__main__':
    app.run(debug=True)
