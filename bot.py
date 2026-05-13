import os
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
    CallbackQueryHandler,
)
import cloudinary
import cloudinary.uploader
from models import db, Product, User, Order, PushSubscription
from app import app, mail, send_push_notification, BASE_URL
from flask_mail import Message
from dotenv import load_dotenv

load_dotenv()

# Configure Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Cloudinary Configuration
cloudinary.config(
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key = os.getenv('CLOUDINARY_API_KEY'),
    api_secret = os.getenv('CLOUDINARY_API_SECRET')
)

# States for ConversationHandler
PHOTO, NAME, PRICE, DESCRIPTION, CATEGORY = range(5)
EDIT_SELECT, EDIT_FIELD, EDIT_VALUE = range(5, 8)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✨ Welcome to SOWARNA SAREES Admin Bot!\n\n"
        "Available Commands:\n"
        "➕ /add - Add a new product\n"
        "✏️ /edit - Edit an existing product\n"
        "🗑️ /delete - Remove a product\n"
        "👥 /users - View all customers\n"
        "✅ /paid <email> - Confirm payment\n"
        "❌ /cancel - Stop current operation"
    )

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with app.app_context():
        users = User.query.all()
        if not users:
            await update.message.reply_text("No users registered yet.")
            return

        response = "👥 *Registered Customers:*\n\n"
        for user in users:
            response += f"👤 *{user.username}*\n"
            response += f"📧 Email: `{user.email}`\n"
            response += f"📞 Phone: {user.phone_code or ''} {user.phone or 'N/A'}\n"
            response += f"🏠 Address: {user.house_no or ''}, {user.street or ''}\n"
            response += f"📍 State: {user.state or 'N/A'}, {user.country or 'N/A'}\n"
            response += f"📮 PIN: {user.postal_code or 'N/A'}\n"
            response += "-------------------\n"
        
        await update.message.reply_text(response, parse_mode='Markdown')

# DELETE PRODUCT FLOW
async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with app.app_context():
        products = Product.query.all()
        if not products:
            await update.message.reply_text("No products to delete.")
            return

        keyboard = []
        for p in products:
            keyboard.append([InlineKeyboardButton(f"{p.name} (₹{p.price})", callback_data=f"del_{p.id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select a product to delete:", reply_markup=reply_markup)

async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    prod_id = int(query.data.split('_')[1])
    
    if query.data.startswith("del_"):
        with app.app_context():
            product = Product.query.get(prod_id)
            if not product:
                await query.edit_message_text("Product not found.")
                return
            
            keyboard = [
                [InlineKeyboardButton("Yes, Delete it!", callback_data=f"confdel_{prod_id}")],
                [InlineKeyboardButton("No, Cancel", callback_data="cancel_del")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"⚠️ Are you sure you want to delete *{product.name}*?", reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data.startswith("confdel_"):
        with app.app_context():
            product = Product.query.get(prod_id)
            if product:
                name = product.name
                db.session.delete(product)
                db.session.commit()
                await query.edit_message_text(f"✅ Product *{name}* has been removed.", parse_mode='Markdown')
            else:
                await query.edit_message_text("Product already removed.")
    
    elif query.data == "cancel_del":
        await query.edit_message_text("Deletion cancelled.")

# EDIT PRODUCT FLOW
async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with app.app_context():
        products = Product.query.all()
        if not products:
            await update.message.reply_text("No products to edit.")
            return ConversationHandler.END

        keyboard = []
        for p in products:
            keyboard.append([InlineKeyboardButton(f"{p.name}", callback_data=f"edit_{p.id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select a product to edit:", reply_markup=reply_markup)
        return EDIT_SELECT

async def edit_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    prod_id = int(query.data.split('_')[1])
    context.user_data['edit_prod_id'] = prod_id
    
    keyboard = [
        [InlineKeyboardButton("Name", callback_data="field_name")],
        [InlineKeyboardButton("Price", callback_data="field_price")],
        [InlineKeyboardButton("Category", callback_data="field_category")],
        [InlineKeyboardButton("Description", callback_data="field_description")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("What detail do you want to edit?", reply_markup=reply_markup)
    return EDIT_FIELD

async def edit_field_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    field = query.data.split('_')[1]
    context.user_data['edit_field'] = field
    
    await query.edit_message_text(f"Please enter the new value for *{field.capitalize()}*:", parse_mode='Markdown')
    return EDIT_VALUE

async def handle_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_value = update.message.text
    prod_id = context.user_data['edit_prod_id']
    field = context.user_data['edit_field']
    
    with app.app_context():
        product = Product.query.get(prod_id)
        if not product:
            await update.message.reply_text("Product not found.")
            return ConversationHandler.END
        
        if field == 'name':
            product.name = new_value
        elif field == 'price':
            try:
                product.price = float(new_value)
            except ValueError:
                await update.message.reply_text("Please enter a valid number for price.")
                return EDIT_VALUE
        elif field == 'category':
            product.category = new_value
        elif field == 'description':
            product.description = new_value
            
        db.session.commit()
        await update.message.reply_text(f"✅ Product {field} updated successfully!")
    
    return ConversationHandler.END

# EXISTING FLOWS...
async def confirm_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide the user's email:\nExample: `/paid customer@email.com`", parse_mode='Markdown')
        return
    
    email = context.args[0]
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if not user:
            await update.message.reply_text(f"User with email {email} not found.")
            return

        msg = Message(
            "Order Confirmed - SOWARNA SAREES",
            recipients=[user.email]
        )
        msg.body = (
            f"Hi {user.username},\n\n"
            f"Exciting news! Your payment has been confirmed and your order is now being processed.\n\n"
            f"Shipping Details:\n"
            f"Address: {user.house_no}, {user.street}, {user.state}, {user.postal_code}\n\n"
            f"Thank you for choosing SOWARNA SAREES! We hope you love your collection."
        )
        
        try:
            mail.send(msg)
            send_push_notification(
                user, 
                "Order Confirmed! ✨", 
                "Your payment was received. We're preparing your sarees for delivery!",
                url=f"{BASE_URL}/"
            )
            await update.message.reply_text(f"✅ Payment confirmed for {user.username}.\nEmail and Push notification sent!")
        except Exception as e:
            await update.message.reply_text(f"❌ Payment confirmed, but notification failed: {str(e)}")

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please send the product image.")
    return PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    photo_path = "temp_image.jpg"
    await photo_file.download_to_drive(photo_path)
    
    upload_result = cloudinary.uploader.upload(photo_path)
    context.user_data['image_url'] = upload_result['secure_url']
    os.remove(photo_path)
    
    await update.message.reply_text("Image uploaded! Now, what is the Product Name?")
    return NAME

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Great! What is the Selling Price?")
    return PRICE

async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text)
        context.user_data['price'] = price
        await update.message.reply_text("Enter a short description (or send /skip for default):")
        return DESCRIPTION
    except ValueError:
        await update.message.reply_text("Please enter a valid number for the price.")
        return PRICE

async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text
    if desc == '/skip':
        desc = "Exquisite high-quality product from our premium boutique collection. Handpicked for elegance and comfort."
    context.user_data['description'] = desc
    
    reply_keyboard = [['Saree', 'Jewel', 'Kurti', 'Other']]
    await update.message.reply_text(
        "What is the Category?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return CATEGORY

def notify_new_product(product_id, name, price, category):
    """Background task to send notifications without blocking the bot."""
    with app.app_context():
        try:
            product_link = f"{BASE_URL}/product/{product_id}"
            users = User.query.all()
            for user in users:
                # Push Notification
                try:
                    send_push_notification(
                        user,
                        "New Arrival! 🛍️",
                        f"{name} is now live in our {category} collection. Tap to view!",
                        url=product_link
                    )
                except Exception as e:
                    logging.error(f"Push notification failed for {user.email}: {str(e)}")

                # Email Notification
                try:
                    msg = Message(
                        f"New Arrival: {name}",
                        recipients=[user.email]
                    )
                    msg.body = (
                        f"Check out our latest addition!\n\n"
                        f"🛍️ Product: {name}\n"
                        f"💰 Price: ₹{price}\n"
                        f"📂 Category: {category}\n\n"
                        f"View Product:\n{product_link}"
                    )
                    mail.send(msg)
                except Exception as e:
                    logging.error(f"Email failed for {user.email}: {str(e)}")
        except Exception as e:
            logging.error(f"Notification error: {str(e)}")

async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = update.message.text
    name = context.user_data['name']
    price = context.user_data['price']
    image_url = context.user_data['image_url']
    description = context.user_data['description']

    with app.app_context():
        try:
            # Create Product
            new_product = Product(
                name=name,
                price=price,
                image_url=image_url,
                category=category,
                description=description
            )

            # Save to DB
            db.session.add(new_product)
            db.session.commit()
            
            product_id = new_product.id

            logging.info(f"Successfully added product: {name}")

            # SEND SUCCESS IMMEDIATELY (FAST RESPONSE)
            await update.message.reply_text(
                f"✅ Product Added Successfully!\n\n"
                f"🛍️ Name: {name}\n"
                f"📂 Category: {category}\n"
                f"💰 Price: ₹{price}",
                reply_markup=ReplyKeyboardRemove()
            )

            # Offload notifications to background thread
            import threading
            threading.Thread(target=notify_new_product, args=(product_id, name, price, category)).start()

        except Exception as e:
            logging.error(f"Error adding product via bot: {str(e)}")
            await update.message.reply_text(
                f"❌ Error adding product:\n{str(e)}",
                reply_markup=ReplyKeyboardRemove()
            )

    return ConversationHandler.END



async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Action cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def start_bot():

    token = os.getenv('TELEGRAM_BOT_TOKEN')

    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not found")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    application = ApplicationBuilder().token(token).build()

    add_conv = ConversationHandler(
        entry_points=[CommandHandler('add', add_start)],
        states={
            PHOTO: [MessageHandler(filters.PHOTO, handle_photo)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price)],
            DESCRIPTION: [
                CommandHandler('skip', handle_description),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description)
            ],
            CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    edit_conv = ConversationHandler(
        entry_points=[CommandHandler('edit', edit_start)],
        states={
            EDIT_SELECT: [CallbackQueryHandler(edit_select_callback, pattern="^edit_")],
            EDIT_FIELD: [CallbackQueryHandler(edit_field_callback, pattern="^field_")],
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_value)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('users', list_users))
    application.add_handler(CommandHandler('paid', confirm_paid))
    application.add_handler(CommandHandler('delete', delete_start))

    application.add_handler(
        CallbackQueryHandler(
            delete_callback,
            pattern="^(del_|confdel_|cancel_del)"
        )
    )

    application.add_handler(add_conv)
    application.add_handler(edit_conv)

    print("🤖 Telegram Bot Started")

    application.run_polling(stop_signals=None)