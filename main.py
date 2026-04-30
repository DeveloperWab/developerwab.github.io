# main.py
import os
import threading
import logging
import json
import asyncio
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import re

# --- Logging ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
TOKEN = "8384600981:AAHhAm-cD1qjiav6UikKsII4FGNsAwzon2o"
MONGO_URI = "mongodb+srv://Vansh:Vansh000@cluster0.tqmuzxc.mongodb.net/?appName=Cluster0"
ADMIN_TRIGGER = "Vansh@000"
ADMIN_USER_IDS = []  # Add admin user IDs here

# --- MongoDB Connection ---
try:
    client = MongoClient(MONGO_URI)
    db = client['earning_bot_db']
    users_collection = db['users']
    tasks_collection = db['tasks']
    visit_tasks_collection = db['visit_tasks']
    task_submissions = db['task_submissions']
    withdrawals_collection = db['withdrawals']
    user_task_history = db['user_task_history']
    user_visit_history = db['user_visit_history']
    print("✅ MongoDB Connected Successfully!")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")
    client = None

# --- Flask for Railway ---
server = Flask(__name__)

@server.route('/')
def health_check():
    return jsonify({"status": "Bot is Live with MongoDB!", "timestamp": datetime.now().isoformat()}), 200

@server.route('/webhook', methods=['POST'])
def webhook():
    return jsonify({"status": "ok"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# --- Keyboards ---
USER_KEYBOARD = [
    ['📝 Tasks', '🔗 Visit & Earn'],
    ['💰 My Balance', '💸 Withdraw'],
    ['👥 Referral Program', '📊 My Stats'],
    ['📜 Task History', '💳 Withdrawal History'],
    ['❓ Help', 'ℹ️ About']
]

ADMIN_KEYBOARD = [
    ['📊 Dashboard', '👥 User Stats'],
    ['💰 Financial Stats', '💸 Withdrawal Requests'],
    ['📋 Pending Submissions', '📢 Broadcast'],
    ['➕ Add Task', '➕ Add Visit Task'],
    ['📜 All Tasks', '📊 Task Analytics'],
    ['🔙 Exit Admin']
]

WITHDRAWAL_METHODS = ['UPI', 'Bank Transfer', 'Crypto (Bitcoin)', 'Google Play Gift Card', 'Amazon Gift Card']
WITHDRAWAL_LIMITS = {
    'UPI': 30,
    'Bank Transfer': 50,
    'Crypto (Bitcoin)': 150,
    'Google Play Gift Card': 10,
    'Amazon Gift Card': 10
}

# --- Helper Functions ---
def get_user(chat_id):
    return users_collection.find_one({"user_id": chat_id})

def update_user_balance(chat_id, amount):
    users_collection.update_one(
        {"user_id": chat_id},
        {"$inc": {"balance": amount}}
    )

def is_admin(chat_id):
    if ADMIN_USER_IDS and chat_id in ADMIN_USER_IDS:
        return True
    # Check if user has admin trigger set
    user = get_user(chat_id)
    return user and user.get('is_admin', False)

# --- Admin Set Functions ---
async def set_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /setadmin <user_id>")
        return
    
    try:
        user_id = int(context.args[0])
        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"is_admin": True}},
            upsert=True
        )
        await update.message.reply_text(f"✅ User {user_id} is now an admin!")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID!")

# --- Bot Functions ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    args = context.args
    
    user_in_db = users_collection.find_one({"user_id": chat_id})
    
    if not user_in_db:
        # Check for referral
        referred_by = None
        if args and args[0].isdigit():
            referred_by = int(args[0])
            # Add referral bonus
            if referred_by != chat_id:
                update_user_balance(referred_by, 2.0)
                users_collection.update_one(
                    {"user_id": referred_by},
                    {"$inc": {"referrals": 1}}
                )
                try:
                    await context.bot.send_message(
                        referred_by,
                        f"🎉 New user joined using your referral link! +2 INR added to your balance."
                    )
                except:
                    pass
        
        new_user = {
            "user_id": chat_id,
            "username": user.username or "NoUsername",
            "name": user.first_name,
            "balance": 0.0,
            "referrals": 0,
            "tasks_done": 0,
            "visit_tasks_done": 0,
            "total_earned": 0.0,
            "total_withdrawn": 0.0,
            "status": "active",
            "joined_date": datetime.now(),
            "referred_by": referred_by,
            "is_admin": False
        }
        users_collection.insert_one(new_user)
        welcome_msg = f"👋 Hello {user.first_name}! Welcome to the Earning Bot!\n\n🎁 Complete tasks and earn money!\n💰 Earn 2 INR per referral!"
        
        if referred_by:
            welcome_msg += f"\n\n✅ You were referred by user {referred_by}!"
    else:
        welcome_msg = f"👋 Welcome back {user.first_name}!\n💰 Your balance: {user_in_db.get('balance', 0):.2f} INR"

    reply_markup = ReplyKeyboardMarkup(USER_KEYBOARD, resize_keyboard=True)
    await update.message.reply_text(welcome_msg, reply_markup=reply_markup)

# --- Task Functions ---
async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    page = context.user_data.get('task_page', 0)
    tasks_per_page = 5
    
    # Get active tasks that user hasn't completed
    user_completed = [t['task_id'] for t in user_task_history.find({"user_id": chat_id, "type": "task"})]
    
    tasks = list(tasks_collection.find({
        "status": "active",
        "expires_at": {"$gt": datetime.now()},
        "task_id": {"$nin": user_completed}
    }).skip(page * tasks_per_page).limit(tasks_per_page))
    
    if not tasks:
        if page == 0:
            await update.message.reply_text("📝 No tasks available at the moment. Check back later!")
        else:
            await update.message.reply_text("No more tasks!")
        return
    
    for task in tasks:
        keyboard = [[InlineKeyboardButton("🎯 Start Task", callback_data=f"start_task_{task['task_id']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = f"📌 *{task['name']}*\n\n"
        message += f"💰 *Reward:* {task['amount']} INR\n"
        message += f"📝 *Description:* {task['description']}\n"
        message += f"⏰ *Expires:* {task['expires_at'].strftime('%Y-%m-%d %H:%M')}"
        
        if task.get('image_id'):
            try:
                await update.message.reply_photo(
                    photo=task['image_id'],
                    caption=message,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            except:
                await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")
    
    # Add navigation buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data="task_prev"))
    
    next_tasks = list(tasks_collection.find({
        "status": "active",
        "expires_at": {"$gt": datetime.now()},
        "task_id": {"$nin": user_completed}
    }).skip((page + 1) * tasks_per_page).limit(1))
    
    if next_tasks:
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data="task_next"))
    
    if nav_buttons:
        nav_markup = InlineKeyboardMarkup([nav_buttons])
        await update.message.reply_text("📋 *Navigation*", reply_markup=nav_markup, parse_mode="Markdown")

async def start_task(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id):
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id
    
    task = tasks_collection.find_one({"task_id": task_id})
    
    if not task or task['status'] != 'active' or task['expires_at'] < datetime.now():
        await query.edit_message_text("❌ This task is no longer available!")
        return
    
    # Store task in context
    context.user_data['current_task'] = task_id
    
    keyboard = [[InlineKeyboardButton("🔗 Visit Link", url=task['link'])]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📌 *{task['name']}*\n\n"
        f"1️⃣ Click the button below to visit the website\n"
        f"2️⃣ Complete the required action\n"
        f"3️⃣ Take a screenshot as proof\n"
        f"4️⃣ Send the screenshot here\n\n"
        f"⚠️ *Note:* After completing, send your screenshot proof!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    context.user_data['awaiting_screenshot'] = True

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.user_data.get('awaiting_screenshot'):
        return
    
    if not update.message.photo:
        await update.message.reply_text("❌ Please send a screenshot photo!")
        return
    
    task_id = context.user_data.get('current_task')
    if not task_id:
        await update.message.reply_text("❌ No task selected! Please go to Tasks menu.")
        context.user_data['awaiting_screenshot'] = False
        return
    
    task = tasks_collection.find_one({"task_id": task_id})
    if not task:
        await update.message.reply_text("❌ Task no longer exists!")
        context.user_data['awaiting_screenshot'] = False
        return
    
    # Get the largest photo
    photo = update.message.photo[-1]
    file_id = photo.file_id
    
    # Save submission
    submission = {
        "submission_id": f"sub_{datetime.now().timestamp()}",
        "task_id": task_id,
        "task_name": task['name'],
        "user_id": chat_id,
        "username": update.effective_user.username or "NoUsername",
        "amount": task['amount'],
        "screenshot_id": file_id,
        "status": "pending",
        "submitted_at": datetime.now()
    }
    
    task_submissions.insert_one(submission)
    
    context.user_data['awaiting_screenshot'] = False
    context.user_data['current_task'] = None
    
    await update.message.reply_text(
        f"✅ Screenshot received!\n\n"
        f"Your submission for task '{task['name']}' is now pending admin approval.\n"
        f"💰 Amount: {task['amount']} INR\n\n"
        f"You will be notified once approved/rejected."
    )
    
    # Notify admins
    admins = users_collection.find({"is_admin": True})
    admin_keyboard = [[InlineKeyboardButton("📋 View Submission", callback_data=f"view_sub_{submission['submission_id']}")]]
    admin_markup = InlineKeyboardMarkup(admin_keyboard)
    
    for admin in admins:
        try:
            await context.bot.send_message(
                admin['user_id'],
                f"📋 *New Task Submission!*\n\n"
                f"User: {update.effective_user.first_name} (@{update.effective_user.username})\n"
                f"Task: {task['name']}\n"
                f"Amount: {task['amount']} INR",
                reply_markup=admin_markup,
                parse_mode="Markdown"
            )
        except:
            pass

# --- Visit Task Functions ---
async def show_visit_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    page = context.user_data.get('visit_page', 0)
    tasks_per_page = 5
    
    # Get active visit tasks
    user_completed_today = [v['task_id'] for v in user_visit_history.find({
        "user_id": chat_id,
        "completed_at": {"$gt": datetime.now() - timedelta(hours=24)}
    })]
    
    tasks = list(visit_tasks_collection.find({
        "status": "active",
        "expires_at": {"$gt": datetime.now()}
    }).skip(page * tasks_per_page).limit(tasks_per_page))
    
    # Filter out tasks completed in last 24 hours
    available_tasks = [t for t in tasks if t['task_id'] not in user_completed_today]
    
    if not available_tasks:
        await update.message.reply_text("🔗 No visit tasks available at the moment! Check back later.")
        return
    
    for task in available_tasks:
        keyboard = [[InlineKeyboardButton("🔗 Start Visit Task", callback_data=f"start_visit_{task['task_id']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = f"🔗 *{task['name']}*\n\n"
        message += f"💰 *Reward:* {task['amount']} INR\n"
        message += f"⏱️ *Time Required:* {task['visit_time']} seconds\n"
        message += f"🔄 *Cooldown:* 24 hours"
        
        if task.get('image_id'):
            try:
                await update.message.reply_photo(photo=task['image_id'], caption=message, reply_markup=reply_markup, parse_mode="Markdown")
            except:
                await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")

async def start_visit_task(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id):
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id
    
    task = visit_tasks_collection.find_one({"task_id": task_id})
    
    if not task or task['status'] != 'active' or task['expires_at'] < datetime.now():
        await query.edit_message_text("❌ This task is no longer available!")
        return
    
    # Check if user completed in last 24 hours
    recent_completion = user_visit_history.find_one({
        "user_id": chat_id,
        "task_id": task_id,
        "completed_at": {"$gt": datetime.now() - timedelta(hours=24)}
    })
    
    if recent_completion:
        next_available = recent_completion['completed_at'] + timedelta(hours=24)
        time_left = next_available - datetime.now()
        hours = int(time_left.total_seconds() // 3600)
        minutes = int((time_left.total_seconds() % 3600) // 60)
        await query.edit_message_text(f"⏰ You can only complete this task once every 24 hours!\n\nNext available in: {hours}h {minutes}m")
        return
    
    # Store task in context
    context.user_data['current_visit_task'] = task_id
    context.user_data['visit_start_time'] = datetime.now()
    
    keyboard = [[InlineKeyboardButton("🔗 Visit Website", url=task['link'])]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🔗 *{task['name']}*\n\n"
        f"1️⃣ Click the button below to visit the website\n"
        f"2️⃣ Stay on the website for *{task['visit_time']} seconds*\n"
        f"3️⃣ After {task['visit_time']} seconds, click '✅ Complete Task'\n\n"
        f"⚠️ *Warning:* Leaving early will invalidate the task!\n"
        f"💰 *Reward:* {task['amount']} INR",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    # Schedule completion check
    context.user_data['awaiting_visit_complete'] = True
    context.user_data['visit_check_time'] = datetime.now() + timedelta(seconds=task['visit_time'])

async def complete_visit_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id
    
    if not context.user_data.get('awaiting_visit_complete'):
        await query.edit_message_text("❌ No active visit task!")
        return
    
    task_id = context.user_data.get('current_visit_task')
    start_time = context.user_data.get('visit_start_time')
    required_time = context.user_data.get('visit_check_time')
    
    if not task_id or not start_time:
        await query.edit_message_text("❌ Task data missing! Please start again.")
        return
    
    task = visit_tasks_collection.find_one({"task_id": task_id})
    if not task:
        await query.edit_message_text("❌ Task no longer exists!")
        return
    
    time_spent = (datetime.now() - start_time).total_seconds()
    
    if time_spent >= task['visit_time']:
        # Add reward
        update_user_balance(chat_id, task['amount'])
        
        # Update user stats
        users_collection.update_one(
            {"user_id": chat_id},
            {
                "$inc": {
                    "visit_tasks_done": 1,
                    "tasks_done": 1,
                    "total_earned": task['amount']
                }
            }
        )
        
        # Record completion
        user_visit_history.insert_one({
            "user_id": chat_id,
            "task_id": task_id,
            "task_name": task['name'],
            "amount": task['amount'],
            "completed_at": datetime.now()
        })
        
        # Update task analytics
        visit_tasks_collection.update_one(
            {"task_id": task_id},
            {
                "$inc": {
                    "total_completions": 1,
                    "total_spent": task['amount']
                }
            }
        )
        
        await query.edit_message_text(
            f"✅ *Task Completed!*\n\n"
            f"Task: {task['name']}\n"
            f"💰 +{task['amount']} INR added to your balance!\n\n"
            f"You can complete this task again after 24 hours.",
            parse_mode="Markdown"
        )
        
        # Show new balance
        user = get_user(chat_id)
        await context.bot.send_message(chat_id, f"💰 Your new balance: {user.get('balance', 0):.2f} INR")
        
    else:
        await query.edit_message_text(
            f"❌ *Task Failed!*\n\n"
            f"You left the website too early!\n"
            f"Required: {task['visit_time']} seconds\n"
            f"You stayed: {int(time_spent)} seconds\n\n"
            f"Please try again.",
            parse_mode="Markdown"
        )
    
    # Clear context
    context.user_data['awaiting_visit_complete'] = False
    context.user_data['current_visit_task'] = None
    context.user_data['visit_start_time'] = None
    context.user_data['visit_check_time'] = None

# --- Withdrawal Functions ---
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    
    keyboard = []
    for method in WITHDRAWAL_METHODS:
        limit = WITHDRAWAL_LIMITS[method]
        keyboard.append([InlineKeyboardButton(f"{method} (Min: {limit} INR)", callback_data=f"withdraw_method_{method}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "💸 *Withdrawal*\n\n"
        f"💰 Your balance: {user.get('balance', 0):.2f} INR\n\n"
        "Select withdrawal method:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def process_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE, method):
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id
    
    context.user_data['withdrawal_method'] = method
    context.user_data['awaiting_withdrawal_details'] = True
    
    method_details = {
        'UPI': 'Please send your UPI ID (e.g., name@okhdfcbank)',
        'Bank Transfer': 'Please send:\nBank Name\nAccount Number\nIFSC Code\nAccount Holder Name',
        'Crypto (Bitcoin)': 'Please send your Bitcoin wallet address',
        'Google Play Gift Card': 'Please send your email address',
        'Amazon Gift Card': 'Please send your email address'
    }
    
    await query.edit_message_text(
        f"💸 *{method} Withdrawal*\n\n"
        f"{method_details[method]}\n\n"
        f"Minimum amount: {WITHDRAWAL_LIMITS[method]} INR\n\n"
        f"Please send your details:",
        parse_mode="Markdown"
    )

async def handle_withdrawal_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.user_data.get('awaiting_withdrawal_details'):
        return
    
    method = context.user_data.get('withdrawal_method')
    details = update.message.text
    user = get_user(chat_id)
    balance = user.get('balance', 0)
    min_amount = WITHDRAWAL_LIMITS[method]
    
    if balance < min_amount:
        await update.message.reply_text(
            f"❌ Insufficient balance!\n\n"
            f"Required: {min_amount} INR\n"
            f"Your balance: {balance:.2f} INR"
        )
        context.user_data['awaiting_withdrawal_details'] = False
        return
    
    context.user_data['withdrawal_details'] = details
    context.user_data['awaiting_withdrawal_amount'] = True
    
    await update.message.reply_text(
        f"💰 Your balance: {balance:.2f} INR\n"
        f"Minimum withdrawal: {min_amount} INR\n\n"
        f"Please enter the amount you want to withdraw:"
    )

async def process_withdrawal_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.user_data.get('awaiting_withdrawal_amount'):
        return
    
    try:
        amount = float(update.message.text)
        method = context.user_data.get('withdrawal_method')
        details = context.user_data.get('withdrawal_details')
        user = get_user(chat_id)
        balance = user.get('balance', 0)
        min_amount = WITHDRAWAL_LIMITS[method]
        
        if amount < min_amount:
            await update.message.reply_text(f"❌ Amount must be at least {min_amount} INR!")
            return
        
        if amount > balance:
            await update.message.reply_text(f"❌ Insufficient balance! Your balance: {balance:.2f} INR")
            return
        
        # Create withdrawal request
        withdrawal = {
            "withdrawal_id": f"wd_{datetime.now().timestamp()}",
            "user_id": chat_id,
            "username": update.effective_user.username or "NoUsername",
            "name": update.effective_user.first_name,
            "method": method,
            "details": details,
            "amount": amount,
            "status": "pending",
            "requested_at": datetime.now()
        }
        
        withdrawals_collection.insert_one(withdrawal)
        
        # Deduct from balance
        update_user_balance(chat_id, -amount)
        
        context.user_data['awaiting_withdrawal_amount'] = False
        context.user_data['awaiting_withdrawal_details'] = False
        context.user_data['withdrawal_method'] = None
        context.user_data['withdrawal_details'] = None
        
        await update.message.reply_text(
            f"✅ Withdrawal request submitted!\n\n"
            f"Amount: {amount} INR\n"
            f"Method: {method}\n\n"
            f"Your request is pending admin approval.\n"
            f"You will be notified once processed."
        )
        
        # Notify admins
        admins = users_collection.find({"is_admin": True})
        for admin in admins:
            try:
                await context.bot.send_message(
                    admin['user_id'],
                    f"💸 *New Withdrawal Request!*\n\n"
                    f"User: {update.effective_user.first_name} (@{update.effective_user.username})\n"
                    f"Amount: {amount} INR\n"
                    f"Method: {method}\n"
                    f"Details: {details}",
                    parse_mode="Markdown"
                )
            except:
                pass
                
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number!")

async def withdrawal_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    page = context.user_data.get('wd_history_page', 0)
    per_page = 10
    
    withdrawals = list(withdrawals_collection.find({"user_id": chat_id}).sort("requested_at", -1).skip(page * per_page).limit(per_page))
    
    if not withdrawals:
        await update.message.reply_text("💳 No withdrawal history found!")
        return
    
    message = "💳 *Your Withdrawal History*\n\n"
    for wd in withdrawals:
        status_emoji = {
            'pending': '⏳',
            'approved': '✅',
            'rejected': '❌'
        }.get(wd['status'], '❓')
        
        message += f"{status_emoji} *{wd['amount']} INR* - {wd['method']}\n"
        message += f"   Status: {wd['status'].upper()}\n"
        message += f"   Date: {wd['requested_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
    
    await update.message.reply_text(message, parse_mode="Markdown")

async def task_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # Get task submissions
    submissions = list(task_submissions.find({"user_id": chat_id}).sort("submitted_at", -1).limit(20))
    
    if not submissions:
        await update.message.reply_text("📜 No task history found!")
        return
    
    message = "📜 *Your Task History*\n\n"
    for sub in submissions:
        status_emoji = {
            'pending': '⏳',
            'approved': '✅',
            'rejected': '❌'
        }.get(sub['status'], '❓')
        
        message += f"{status_emoji} *{sub['task_name']}*\n"
        message += f"   Amount: {sub['amount']} INR\n"
        message += f"   Status: {sub['status'].upper()}\n"
        if sub.get('processed_at'):
            message += f"   Processed: {sub['processed_at'].strftime('%Y-%m-%d %H:%M')}\n"
        message += f"   Submitted: {sub['submitted_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
    
    await update.message.reply_text(message, parse_mode="Markdown")

# --- Admin Functions ---
async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("❌ Admin access required!")
        return
    
    total_users = users_collection.count_documents({})
    active_users = users_collection.count_documents({"status": "active"})
    total_earned = users_collection.aggregate([{"$group": {"_id": None, "total": {"$sum": "$total_earned"}}}]).next().get('total', 0)
    total_withdrawn = users_collection.aggregate([{"$group": {"_id": None, "total": {"$sum": "$total_withdrawn"}}}]).next().get('total', 0)
    pending_submissions = task_submissions.count_documents({"status": "pending"})
    pending_withdrawals = withdrawals_collection.count_documents({"status": "pending"})
    
    dashboard = (
        f"📊 *Admin Dashboard*\n\n"
        f"👥 Total Users: {total_users}\n"
        f"🟢 Active Users: {active_users}\n"
        f"💰 Total Earned: {total_earned:.2f} INR\n"
        f"💸 Total Withdrawn: {total_withdrawn:.2f} INR\n"
        f"📋 Pending Submissions: {pending_submissions}\n"
        f"💸 Pending Withdrawals: {pending_withdrawals}\n\n"
        f"📈 Platform Balance: {total_earned - total_withdrawn:.2f} INR"
    )
    
    await update.message.reply_text(dashboard, parse_mode="Markdown")

async def pending_submissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    
    submissions = list(task_submissions.find({"status": "pending"}).sort("submitted_at", -1).limit(20))
    
    if not submissions:
        await update.message.reply_text("No pending submissions!")
        return
    
    for sub in submissions:
        keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_sub_{sub['submission_id']}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"reject_sub_{sub['submission_id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            f"📋 *Pending Submission*\n\n"
            f"User: {sub.get('username', 'Unknown')}\n"
            f"Task: {sub['task_name']}\n"
            f"Amount: {sub['amount']} INR\n"
            f"Submitted: {sub['submitted_at'].strftime('%Y-%m-%d %H:%M')}"
        )
        
        try:
            if sub.get('screenshot_id'):
                await update.message.reply_photo(
                    photo=sub['screenshot_id'],
                    caption=message,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")
        except:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")

async def handle_submission_decision(update: Update, context: ContextTypes.DEFAULT_TYPE, submission_id, decision):
    query = update.callback_query
    await query.answer()
    
    submission = task_submissions.find_one({"submission_id": submission_id})
    if not submission:
        await query.edit_message_text("❌ Submission not found!")
        return
    
    if decision == "approve":
        # Add balance
        update_user_balance(submission['user_id'], submission['amount'])
        
        # Update user stats
        users_collection.update_one(
            {"user_id": submission['user_id']},
            {
                "$inc": {
                    "tasks_done": 1,
                    "total_earned": submission['amount']
                }
            }
        )
        
        # Update submission
        task_submissions.update_one(
            {"submission_id": submission_id},
            {
                "$set": {
                    "status": "approved",
                    "processed_at": datetime.now(),
                    "processed_by": query.from_user.id
                }
            }
        )
        
        # Update task completion count
        tasks_collection.update_one(
            {"task_id": submission['task_id']},
            {"$inc": {"total_completions": 1, "total_spent": submission['amount']}}
        )
        
        # Record in user history
        user_task_history.insert_one({
            "user_id": submission['user_id'],
            "task_id": submission['task_id'],
            "task_name": submission['task_name'],
            "amount": submission['amount'],
            "status": "approved",
            "completed_at": datetime.now()
        })
        
        await query.edit_message_text(f"✅ Submission approved! +{submission['amount']} INR added.")
        
        # Notify user
        try:
            await context.bot.send_message(
                submission['user_id'],
                f"✅ *Task Approved!*\n\n"
                f"Your submission for '{submission['task_name']}' has been approved!\n"
                f"💰 +{submission['amount']} INR added to your balance.",
                parse_mode="Markdown"
            )
        except:
            pass
            
    else:  # reject
        task_submissions.update_one(
            {"submission_id": submission_id},
            {
                "$set": {
                    "status": "rejected",
                    "processed_at": datetime.now(),
                    "processed_by": query.from_user.id,
                    "rejection_reason": "Invalid proof"
                }
            }
        )
        
        user_task_history.insert_one({
            "user_id": submission['user_id'],
            "task_id": submission['task_id'],
            "task_name": submission['task_name'],
            "amount": submission['amount'],
            "status": "rejected",
            "completed_at": datetime.now()
        })
        
        await query.edit_message_text("❌ Submission rejected!")
        
        # Notify user
        try:
            await context.bot.send_message(
                submission['user_id'],
                f"❌ *Task Rejected*\n\n"
                f"Your submission for '{submission['task_name']}' has been rejected.\n"
                f"Reason: Invalid proof provided.\n\n"
                f"Please submit again with valid proof.",
                parse_mode="Markdown"
            )
        except:
            pass

async def pending_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    
    withdrawals = list(withdrawals_collection.find({"status": "pending"}).sort("requested_at", -1))
    
    if not withdrawals:
        await update.message.reply_text("No pending withdrawals!")
        return
    
    for wd in withdrawals:
        keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_wd_{wd['withdrawal_id']}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"reject_wd_{wd['withdrawal_id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            f"💸 *Withdrawal Request*\n\n"
            f"User: {wd.get('name', 'Unknown')} (@{wd.get('username', 'Unknown')})\n"
            f"Amount: {wd['amount']} INR\n"
            f"Method: {wd['method']}\n"
            f"Details: {wd['details']}\n"
            f"Requested: {wd['requested_at'].strftime('%Y-%m-%d %H:%M')}"
        )
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")

async def handle_withdrawal_decision(update: Update, context: ContextTypes.DEFAULT_TYPE, withdrawal_id, decision):
    query = update.callback_query
    await query.answer()
    
    withdrawal = withdrawals_collection.find_one({"withdrawal_id": withdrawal_id})
    if not withdrawal:
        await query.edit_message_text("❌ Withdrawal not found!")
        return
    
    if decision == "approve":
        withdrawals_collection.update_one(
            {"withdrawal_id": withdrawal_id},
            {
                "$set": {
                    "status": "approved",
                    "processed_at": datetime.now(),
                    "processed_by": query.from_user.id
                }
            }
        )
        
        # Update user total withdrawn
        users_collection.update_one(
            {"user_id": withdrawal['user_id']},
            {"$inc": {"total_withdrawn": withdrawal['amount']}}
        )
        
        await query.edit_message_text(f"✅ Withdrawal approved! Amount: {withdrawal['amount']} INR")
        
        # Notify user
        try:
            await context.bot.send_message(
                withdrawal['user_id'],
                f"✅ *Withdrawal Approved!*\n\n"
                f"Amount: {withdrawal['amount']} INR\n"
                f"Method: {withdrawal['method']}\n\n"
                f"Amount will be sent to your provided details shortly.",
                parse_mode="Markdown"
            )
        except:
            pass
            
    else:  # reject
        withdrawals_collection.update_one(
            {"withdrawal_id": withdrawal_id},
            {
                "$set": {
                    "status": "rejected",
                    "processed_at": datetime.now(),
                    "processed_by": query.from_user.id,
                    "rejection_reason": "Invalid details"
                }
            }
        )
        
        # Refund the amount
        update_user_balance(withdrawal['user_id'], withdrawal['amount'])
        
        await query.edit_message_text("❌ Withdrawal rejected! Amount refunded to user.")
        
        # Notify user
        try:
            await context.bot.send_message(
                withdrawal['user_id'],
                f"❌ *Withdrawal Rejected*\n\n"
                f"Amount: {withdrawal['amount']} INR\n"
                f"Reason: Invalid details provided.\n\n"
                f"Amount has been refunded to your balance.",
                parse_mode="Markdown"
            )
        except:
            pass

async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    
    context.user_data['admin_action'] = 'add_task'
    context.user_data['task_step'] = 1
    await update.message.reply_text(
        "📝 *Add New Task*\n\n"
        "Please send the task name:",
        parse_mode="Markdown"
    )

async def add_visit_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    
    context.user_data['admin_action'] = 'add_visit_task'
    context.user_data['task_step'] = 1
    await update.message.reply_text(
        "🔗 *Add New Visit Task*\n\n"
        "Please send the task name:",
        parse_mode="Markdown"
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    
    context.user_data['admin_action'] = 'broadcast'
    await update.message.reply_text(
        "📢 *Send Broadcast Message*\n\n"
        "Please send the message you want to broadcast to all users:",
        parse_mode="Markdown"
    )

async def task_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    
    tasks = list(tasks_collection.find())
    
    if not tasks:
        await update.message.reply_text("No tasks found!")
        return
    
    message = "📊 *Task Analytics*\n\n"
    for task in tasks:
        message += f"📌 *{task['name']}*\n"
        message += f"   Reward: {task['amount']} INR\n"
        message += f"   Completions: {task.get('total_completions', 0)}\n"
        message += f"   Total Spent: {task.get('total_spent', 0)} INR\n"
        message += f"   Status: {task['status']}\n\n"
    
    await update.message.reply_text(message, parse_mode="Markdown")

# --- Handle Admin Task Creation Steps ---
async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    
    if not context.user_data.get('admin_action'):
        return
    
    action = context.user_data['admin_action']
    
    if action == 'add_task':
        step = context.user_data.get('task_step', 1)
        
        if step == 1:
            context.user_data['task_name'] = text
            context.user_data['task_step'] = 2
            await update.message.reply_text("📝 Send task description:")
            
        elif step == 2:
            context.user_data['task_description'] = text
            context.user_data['task_step'] = 3
            await update.message.reply_text("💰 Send task reward amount (in INR):")
            
        elif step == 3:
            try:
                amount = float(text)
                context.user_data['task_amount'] = amount
                context.user_data['task_step'] = 4
                await update.message.reply_text("🔗 Send task link:")
            except:
                await update.message.reply_text("❌ Please send a valid number!")
                
        elif step == 4:
            context.user_data['task_link'] = text
            context.user_data['task_step'] = 5
            await update.message.reply_text("📸 Send task image (optional) - Send 'skip' to skip:")
            
        elif step == 5:
            image_id = None
            if text.lower() != 'skip' and update.message.photo:
                image_id = update.message.photo[-1].file_id
            elif text.lower() != 'skip':
                await update.message.reply_text("Please send a photo or type 'skip'")
                return
            
            # Create task
            task_id = f"task_{datetime.now().timestamp()}"
            task = {
                "task_id": task_id,
                "name": context.user_data['task_name'],
                "description": context.user_data['task_description'],
                "amount": context.user_data['task_amount'],
                "link": context.user_data['task_link'],
                "image_id": image_id,
                "status": "active",
                "expires_at": datetime.now() + timedelta(days=30),
                "total_completions": 0,
                "total_spent": 0,
                "created_at": datetime.now()
            }
            
            tasks_collection.insert_one(task)
            
            await update.message.reply_text(
                f"✅ *Task Created Successfully!*\n\n"
                f"Name: {task['name']}\n"
                f"Reward: {task['amount']} INR\n"
                f"Link: {task['link']}",
                parse_mode="Markdown"
            )
            
            # Clear context
            context.user_data.pop('admin_action', None)
            context.user_data.pop('task_step', None)
            
    elif action == 'add_visit_task':
        step = context.user_data.get('task_step', 1)
        
        if step == 1:
            context.user_data['task_name'] = text
            context.user_data['task_step'] = 2
            await update.message.reply_text("💰 Send task reward amount (in INR):")
            
        elif step == 2:
            try:
                amount = float(text)
                context.user_data['task_amount'] = amount
                context.user_data['task_step'] = 3
                await update.message.reply_text("⏱️ Send visit time required (in seconds):")
            except:
                await update.message.reply_text("❌ Please send a valid number!")
                
        elif step == 3:
            try:
                visit_time = int(text)
                context.user_data['visit_time'] = visit_time
                context.user_data['task_step'] = 4
                await update.message.reply_text("🔗 Send website link:")
            except:
                await update.message.reply_text("❌ Please send a valid number!")
                
        elif step == 4:
            context.user_data['task_link'] = text
            context.user_data['task_step'] = 5
            await update.message.reply_text("📸 Send task image (optional) - Send 'skip' to skip:")
            
        elif step == 5:
            image_id = None
            if text.lower() != 'skip' and update.message.photo:
                image_id = update.message.photo[-1].file_id
            elif text.lower() != 'skip':
                await update.message.reply_text("Please send a photo or type 'skip'")
                return
            
            # Create visit task
            task_id = f"visit_{datetime.now().timestamp()}"
            task = {
                "task_id": task_id,
                "name": context.user_data['task_name'],
                "amount": context.user_data['task_amount'],
                "visit_time": context.user_data['visit_time'],
                "link": context.user_data['task_link'],
                "image_id": image_id,
                "status": "active",
                "expires_at": datetime.now() + timedelta(days=30),
                "total_completions": 0,
                "total_spent": 0,
                "created_at": datetime.now()
            }
            
            visit_tasks_collection.insert_one(task)
            
            await update.message.reply_text(
                f"✅ *Visit Task Created Successfully!*\n\n"
                f"Name: {task['name']}\n"
                f"Reward: {task['amount']} INR\n"
                f"Time: {task['visit_time']} seconds\n"
                f"Link: {task['link']}",
                parse_mode="Markdown"
            )
            
            # Clear context
            context.user_data.pop('admin_action', None)
            context.user_data.pop('task_step', None)
            
    elif action == 'broadcast':
        # Broadcast to all users
        users = users_collection.find()
        sent = 0
        failed = 0
        
        await update.message.reply_text("📢 Broadcasting message to all users...")
        
        for user in users:
            try:
                await context.bot.send_message(user['user_id'], text, parse_mode="Markdown")
                sent += 1
                await asyncio.sleep(0.05)  # Avoid flooding
            except:
                failed += 1
        
        await update.message.reply_text(
            f"✅ *Broadcast Complete!*\n\n"
            f"Sent: {sent} users\n"
            f"Failed: {failed} users",
            parse_mode="Markdown"
        )
        
        context.user_data.pop('admin_action', None)

# --- Main Message Handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    
    # Check for admin action
    if context.user_data.get('admin_action'):
        await handle_admin_input(update, context)
        return
    
    # Check for withdrawal details
    if context.user_data.get('awaiting_withdrawal_details'):
        await handle_withdrawal_details(update, context)
        return
    
    if context.user_data.get('awaiting_withdrawal_amount'):
        await process_withdrawal_amount(update, context)
        return
    
    # Admin Panel Secret Trigger
    if text == ADMIN_TRIGGER:
        # Set as admin
        users_collection.update_one(
            {"user_id": chat_id},
            {"$set": {"is_admin": True}},
            upsert=True
        )
        reply_markup = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
        await update.message.reply_text("⚡ *Admin Panel Activated*", reply_markup=reply_markup, parse_mode="Markdown")
        return
    
    if text == '🔙 Exit Admin':
        reply_markup = ReplyKeyboardMarkup(USER_KEYBOARD, resize_keyboard=True)
        await update.message.reply_text("Back to User Menu.", reply_markup=reply_markup)
        return
    
    # Check if it's a screenshot submission
    if context.user_data.get('awaiting_screenshot') and update.message.photo:
        await handle_screenshot(update, context)
        return
    
    if text == '📝 Tasks':
        await show_tasks(update, context)
    elif text == '🔗 Visit & Earn':
        await show_visit_tasks(update, context)
    elif text == '💰 My Balance':
        user = get_user(chat_id)
        bal = user.get('balance', 0.0)
        await update.message.reply_text(f"💰 *Your Current Balance:* {bal:.2f} INR", parse_mode="Markdown")
    elif text == '💸 Withdraw':
        await withdraw(update, context)
    elif text == '📊 My Stats':
        user = get_user(chat_id)
        stats = (
            f"📊 *User Statistics*\n\n"
            f"👤 Name: {user.get('name')}\n"
            f"💰 Balance: {user.get('balance', 0):.2f} INR\n"
            f"👥 Total Referrals: {user.get('referrals', 0)}\n"
            f"📝 Tasks Completed: {user.get('tasks_done', 0)}\n"
            f"🔗 Visit Tasks Done: {user.get('visit_tasks_done', 0)}\n"
            f"💵 Total Earned: {user.get('total_earned', 0):.2f} INR\n"
            f"💸 Total Withdrawn: {user.get('total_withdrawn', 0):.2f} INR"
        )
        await update.message.reply_text(stats, parse_mode="Markdown")
    elif text == '👥 Referral Program':
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={chat_id}"
        await update.message.reply_text(
            f"👥 *Referral Program*\n\n"
            f"Invite your friends and earn 2 INR per referral!\n\n"
            f"✨ *Your Referral Link:*\n`{ref_link}`\n\n"
            f"📊 Total Referrals: {get_user(chat_id).get('referrals', 0)}\n"
            f"💰 Total Earned from Referrals: {get_user(chat_id).get('referrals', 0) * 2} INR",
            parse_mode="Markdown"
        )
    elif text == '📜 Task History':
        await task_history(update, context)
    elif text == '💳 Withdrawal History':
        await withdrawal_history(update, context)
    elif text == '❓ Help':
        help_text = (
            "❓ *Help Guide*\n\n"
            "📝 *Tasks:* Complete tasks and submit screenshots\n"
            "🔗 *Visit & Earn:* Visit websites for specified time\n"
            "👥 *Referral:* Invite friends to earn 2 INR each\n"
            "💰 *Withdraw:* Minimum withdrawal varies by method\n\n"
            "*Support:* Contact @support for assistance"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")
    elif text == 'ℹ️ About':
        about_text = (
            "ℹ️ *About This Bot*\n\n"
            "🤖 Version: 2.0\n"
            "💰 Earn money by completing tasks\n"
            "👥 Referral program active\n"
            "✅ Instant payments\n\n"
            "*Features:*\n"
            "• Task completion\n"
            "• Visit & earn\n"
            "• Referral rewards\n"
            "• Multiple withdrawal methods"
        )
        await update.message.reply_text(about_text, parse_mode="Markdown")
    
    # Admin panel options
    elif is_admin(chat_id):
        if text == '📊 Dashboard':
            await admin_dashboard(update, context)
        elif text == '📋 Pending Submissions':
            await pending_submissions(update, context)
        elif text == '💸 Withdrawal Requests':
            await pending_withdrawals(update, context)
        elif text == '➕ Add Task':
            await add_task(update, context)
        elif text == '➕ Add Visit Task':
            await add_visit_task(update, context)
        elif text == '📢 Broadcast':
            await broadcast(update, context)
        elif text == '📊 Task Analytics':
            await task_analytics(update, context)
        elif text == '👥 User Stats':
            total_users = users_collection.count_documents({})
            active_today = users_collection.count_documents({"joined_date": {"$gt": datetime.now() - timedelta(days=1)}})
            await update.message.reply_text(
                f"👥 *User Statistics*\n\n"
                f"Total Users: {total_users}\n"
                f"New Today: {active_today}",
                parse_mode="Markdown"
            )
        elif text == '💰 Financial Stats':
            total_earned = users_collection.aggregate([{"$group": {"_id": None, "total": {"$sum": "$total_earned"}}}]).next().get('total', 0)
            total_withdrawn = users_collection.aggregate([{"$group": {"_id": None, "total": {"$sum": "$total_withdrawn"}}}]).next().get('total', 0)
            platform_balance = total_earned - total_withdrawn
            await update.message.reply_text(
                f"💰 *Financial Statistics*\n\n"
                f"Total Earned: {total_earned:.2f} INR\n"
                f"Total Withdrawn: {total_withdrawn:.2f} INR\n"
                f"Platform Balance: {platform_balance:.2f} INR",
                parse_mode="Markdown"
            )
        elif text == '📜 All Tasks':
            tasks = list(tasks_collection.find())
            if not tasks:
                await update.message.reply_text("No tasks found!")
                return
            msg = "*All Tasks*\n\n"
            for task in tasks:
                msg += f"📌 {task['name']} - {task['amount']} INR\n"
            await update.message.reply_text(msg, parse_mode="Markdown")

# --- Callback Query Handler ---
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("start_task_"):
        task_id = data.replace("start_task_", "")
        await start_task(update, context, task_id)
    elif data.startswith("start_visit_"):
        task_id = data.replace("start_visit_", "")
        await start_visit_task(update, context, task_id)
    elif data == "complete_visit":
        await complete_visit_task(update, context)
    elif data.startswith("approve_sub_"):
        submission_id = data.replace("approve_sub_", "")
        await handle_submission_decision(update, context, submission_id, "approve")
    elif data.startswith("reject_sub_"):
        submission_id = data.replace("reject_sub_", "")
        await handle_submission_decision(update, context, submission_id, "reject")
    elif data.startswith("approve_wd_"):
        withdrawal_id = data.replace("approve_wd_", "")
        await handle_withdrawal_decision(update, context, withdrawal_id, "approve")
    elif data.startswith("reject_wd_"):
        withdrawal_id = data.replace("reject_wd_", "")
        await handle_withdrawal_decision(update, context, withdrawal_id, "reject")
    elif data.startswith("view_sub_"):
        submission_id = data.replace("view_sub_", "")
        submission = task_submissions.find_one({"submission_id": submission_id})
        if submission:
            keyboard = [
                [InlineKeyboardButton("✅ Approve", callback_data=f"approve_sub_{submission_id}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"reject_sub_{submission_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            message = f"📋 *Submission Details*\n\nUser: {submission.get('username')}\nTask: {submission['task_name']}\nAmount: {submission['amount']} INR"
            if submission.get('screenshot_id'):
                try:
                    await query.message.reply_photo(photo=submission['screenshot_id'], caption=message, reply_markup=reply_markup, parse_mode="Markdown")
                except:
                    await query.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")
            else:
                await query.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")
    elif data.startswith("withdraw_method_"):
        method = data.replace("withdraw_method_", "")
        await process_withdrawal(update, context, method)
    elif data == "task_next":
        context.user_data['task_page'] = context.user_data.get('task_page', 0) + 1
        await query.message.delete()
        await show_tasks(update, context)
    elif data == "task_prev":
        context.user_data['task_page'] = max(0, context.user_data.get('task_page', 0) - 1)
        await query.message.delete()
        await show_tasks(update, context)

# --- Run the Bot ---
if __name__ == '__main__':
    # Start Flask in background for Railway
    threading.Thread(target=run_flask, daemon=True).start()
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setadmin", set_admin))
    
    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    
    # Callback query handler
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    
    print("🚀 Bot is running with MongoDB...")
    print("✅ All features active:")
    print("   - Task System with Screenshot Verification")
    print("   - Visit & Earn System")
    print("   - Referral Program (2 INR per referral)")
    print("   - Multiple Withdrawal Methods")
    print("   - Admin Panel")
    print("   - Task History & Withdrawal History")
    
    app.run_polling()