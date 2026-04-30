# main.py - Professional Telegram Earning Bot with MongoDB (Railway Ready)
import telebot
from telebot import types
from pymongo import MongoClient
from datetime import datetime, timedelta
import time
import random
import string
import os
import sys
from bson import ObjectId

# --- CONFIGURATION ---
# Railway will inject environment variables
API_TOKEN = os.environ.get('API_TOKEN', '8384600981:AAFOkWJEw0zPqouHrwFUYw9LI7m-eLBp1KE')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Vansh@000')
MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb+srv://Vansh:Vansh000@cluster0.tqmuzxc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
DB_NAME = os.environ.get('DB_NAME', 'telegram_earning_bot')

# Global variable for admin tracking
ADMIN_USER_ID = None
bot = None

# --- MongoDB Connection with Retry Logic ---
def connect_mongodb(max_retries=3):
    """Connect to MongoDB with retry logic"""
    for attempt in range(max_retries):
        try:
            print(f"🔄 MongoDB Connection Attempt {attempt + 1}/{max_retries}")
            print(f"📡 URI: {MONGODB_URI.replace('Vansh000', '******')}")
            
            client = MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=15000,
                connectTimeoutMS=15000,
                socketTimeoutMS=15000,
                retryWrites=True,
                w='majority'
            )
            
            # Test connection
            client.admin.command('ping')
            db = client[DB_NAME]
            print("✅ Connected to MongoDB successfully!")
            return client, db
            
        except Exception as e:
            print(f"❌ MongoDB Connection Error (Attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                print(f"⏳ Retrying in 5 seconds...")
                time.sleep(5)
            else:
                print("❌ Failed to connect to MongoDB after all attempts")
                raise e

# Initialize MongoDB connection
try:
    mongo_client, db = connect_mongodb()
    print(f"✅ Database '{DB_NAME}' selected")
except Exception as e:
    print(f"❌ Fatal MongoDB Error: {e}")
    sys.exit(1)

# --- Initialize Collections ---
users_collection = db['users']
tasks_collection = db['tasks']
visit_tasks_collection = db['visit_tasks']
withdrawal_requests_collection = db['withdrawal_requests']
completed_tasks_collection = db['completed_tasks']
completed_visits_collection = db['completed_visits']
task_submissions_collection = db['task_submissions']
referrals_collection = db['referrals']

# Create indexes for better performance
def create_indexes():
    """Create database indexes with error handling"""
    try:
        users_collection.create_index('user_id', unique=True, sparse=True)
        users_collection.create_index('referral_code', sparse=True)
        tasks_collection.create_index('type')
        withdrawal_requests_collection.create_index([('user_id', 1), ('status', 1)])
        task_submissions_collection.create_index([('user_id', 1), ('status', 1)])
        print("✅ Database indexes created/verified")
    except Exception as e:
        print(f"⚠️ Index creation warning (non-critical): {e}")

create_indexes()

# --- Initialize Telegram Bot ---
def initialize_bot():
    """Initialize Telegram Bot with error handling"""
    try:
        bot = telebot.TeleBot(API_TOKEN, threaded=False)
        print(f"✅ Telegram Bot initialized successfully!")
        return bot
    except Exception as e:
        print(f"❌ Telegram Bot initialization error: {e}")
        sys.exit(1)

bot = initialize_bot()

# --- Helper Functions ---
def generate_referral_code():
    """Generate unique referral code"""
    max_attempts = 10
    for _ in range(max_attempts):
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not users_collection.find_one({'referral_code': code}):
            return code
    # Fallback to longer code if collisions
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

def get_user(user_id):
    """Get user from database safely"""
    try:
        user = users_collection.find_one({'user_id': str(user_id)})
        if user and '_id' in user:
            user['_id'] = str(user['_id'])
        return user
    except Exception as e:
        print(f"Error getting user {user_id}: {e}")
        return None

def update_user_balance(user_id, amount, operation='add'):
    """Update user balance with validation"""
    try:
        user = get_user(user_id)
        if not user:
            return False
        
        current_balance = float(user.get('balance', 0))
        
        if operation == 'add':
            new_balance = current_balance + amount
        elif operation == 'subtract':
            if current_balance < amount:
                return False
            new_balance = current_balance - amount
        else:
            return False
        
        # Round to 2 decimal places
        new_balance = round(new_balance, 2)
        
        users_collection.update_one(
            {'user_id': str(user_id)},
            {'$set': {'balance': new_balance}}
        )
        return True
    except Exception as e:
        print(f"Error updating balance for user {user_id}: {e}")
        return False

def add_transaction(user_id, amount, trans_type, description):
    """Add transaction record safely"""
    try:
        transaction = {
            'amount': amount,
            'type': trans_type,
            'description': description,
            'date': datetime.now(),
            'status': 'completed'
        }
        
        users_collection.update_one(
            {'user_id': str(user_id)},
            {'$push': {'transactions': transaction}}
        )
        return True
    except Exception as e:
        print(f"Error adding transaction for user {user_id}: {e}")
        return False

def format_balance(balance):
    """Format balance with ₹ symbol"""
    try:
        return f"₹{float(balance):.2f}"
    except:
        return f"₹0.00"

def is_admin(message):
    """Check if user is admin"""
    return message.chat.id == ADMIN_USER_ID

# --- Keyboards ---
def main_keyboard():
    """Create main menu keyboard"""
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton('📝 Tasks')
    btn2 = types.KeyboardButton('🔗 Visit Tasks')
    btn3 = types.KeyboardButton('💰 Balance')
    btn4 = types.KeyboardButton('💸 Withdraw')
    btn5 = types.KeyboardButton('👥 Refer & Earn')
    btn6 = types.KeyboardButton('📢 Advertisement')
    btn7 = types.KeyboardButton('📊 My Stats')
    btn8 = types.KeyboardButton('ℹ️ About')
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8)
    return markup

def admin_keyboard():
    """Create admin panel keyboard"""
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton('📊 Total Users')
    btn2 = types.KeyboardButton('💰 Total Balance')
    btn3 = types.KeyboardButton('📝 Manage Tasks')
    btn4 = types.KeyboardButton('🔗 Manage Visit Tasks')
    btn5 = types.KeyboardButton('💸 Withdrawal Requests')
    btn6 = types.KeyboardButton('📋 Task Submissions')
    btn7 = types.KeyboardButton('👥 Referral Stats')
    btn8 = types.KeyboardButton('📢 Broadcast Message')
    btn9 = types.KeyboardButton('🔙 Back to Menu')
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9)
    return markup

def withdrawal_methods_keyboard():
    """Create withdrawal methods inline keyboard"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn1 = types.InlineKeyboardButton('💳 UPI (Min ₹50)', callback_data='withdraw_upi')
    btn2 = types.InlineKeyboardButton('🏦 Bank Transfer (Min ₹100)', callback_data='withdraw_bank')
    btn3 = types.InlineKeyboardButton('₿ Bitcoin (Min ₹200)', callback_data='withdraw_crypto')
    markup.add(btn1, btn2, btn3)
    return markup

# --- Start Command ---
@bot.message_handler(commands=['start'])
def start(message):
    """Handle /start command"""
    try:
        user_id = str(message.from_user.id)
        username = message.from_user.username or "No username"
        first_name = message.from_user.first_name or "User"
        
        # Check if user exists
        user = get_user(user_id)
        
        # Handle referral code
        referral_code = None
        if len(message.text.split()) > 1:
            referral_code = message.text.split()[1]
        
        if not user:
            # Create new user
            new_referral_code = generate_referral_code()
            
            user_data = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'balance': 0.0,
                'total_earned': 0.0,
                'total_withdrawn': 0.0,
                'referral_code': new_referral_code,
                'referred_by': None,
                'referral_earnings': 0.0,
                'total_referrals': 0,
                'joined_date': datetime.now(),
                'transactions': [],
                'withdrawal_requests': [],
                'completed_tasks': [],
                'completed_visits': [],
                'is_active': True,
                'last_active': datetime.now()
            }
            
            # Process referral
            if referral_code:
                referrer = users_collection.find_one({'referral_code': referral_code})
                if referrer and referrer['user_id'] != user_id:
                    user_data['referred_by'] = referrer['user_id']
                    
                    # Give referral bonus
                    referral_bonus = 2.0
                    update_user_balance(referrer['user_id'], referral_bonus, 'add')
                    users_collection.update_one(
                        {'user_id': referrer['user_id']},
                        {'$inc': {'total_referrals': 1, 'referral_earnings': referral_bonus}}
                    )
                    
                    add_transaction(referrer['user_id'], referral_bonus, 'referral', 
                                  f'New referral: {first_name}')
                    
                    # Notify referrer
                    try:
                        bot.send_message(
                            int(referrer['user_id']), 
                            f"🎉 *New Referral!*\n\n"
                            f"{first_name} joined using your referral link!\n"
                            f"You earned ₹{referral_bonus:.2f}\n\n"
                            f"Total Referrals: {referrer.get('total_referrals', 0) + 1}",
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        print(f"Could not notify referrer: {e}")
            
            # Save new user
            users_collection.insert_one(user_data)
            
            # Welcome message
            welcome_msg = f"""🎉 *Welcome to Earning Bot, {first_name}!*

💡 *How to Earn Money:*
✅ Complete Tasks - Earn per task
🔗 Visit Websites - Earn per visit
👥 Refer Friends - Earn ₹2/referral
💸 Instant Withdrawals

🔑 *Your Referral Code:* `{new_referral_code}`
📊 Share this code with friends to earn ₹2 each!

🎯 Start earning now by using the buttons below!

⚠️ *Rules:*
• One account per person
• Complete tasks honestly
• Fake submissions = Ban
• Be patient for withdrawals"""
            
            bot.send_message(
                message.chat.id, 
                welcome_msg, 
                reply_markup=main_keyboard(), 
                parse_mode='Markdown'
            )
        else:
            # Update last active
            users_collection.update_one(
                {'user_id': user_id},
                {'$set': {'last_active': datetime.now()}}
            )
            
            # Welcome back message
            welcome_back_msg = f"""👋 *Welcome Back, {first_name}!*

💰 Balance: {format_balance(user.get('balance', 0))}
👥 Referrals: {user.get('total_referrals', 0)}

Continue earning by completing tasks!"""
            
            bot.send_message(
                message.chat.id, 
                welcome_back_msg, 
                reply_markup=main_keyboard(), 
                parse_mode='Markdown'
            )
            
    except Exception as e:
        print(f"Error in start command: {e}")
        try:
            bot.send_message(
                message.chat.id, 
                "❌ An error occurred. Please try again or contact support.",
                reply_markup=main_keyboard()
            )
        except:
            pass

# --- Balance Check ---
@bot.message_handler(func=lambda message: message.text == '💰 Balance')
def check_balance(message):
    """Check user balance"""
    try:
        user = get_user(message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ User not found. Please use /start")
            return
        
        balance = user.get('balance', 0)
        total_earned = user.get('total_earned', 0)
        total_withdrawn = user.get('total_withdrawn', 0)
        referral_earnings = user.get('referral_earnings', 0)
        total_referrals = user.get('total_referrals', 0)
        
        msg = f"""💰 *Your Wallet*

💵 Available Balance: {format_balance(balance)}
📈 Total Earned: {format_balance(total_earned)}
💸 Total Withdrawn: {format_balance(total_withdrawn)}

👥 *Referral Stats*
🎁 Referral Code: `{user.get('referral_code', 'N/A')}`
👤 Total Referrals: {total_referrals}
🎁 Referral Earnings: {format_balance(referral_earnings)}

📝 Tasks Completed: {len(user.get('completed_tasks', []))}
🔗 Visits Completed: {len(user.get('completed_visits', []))}

💡 Keep earning by completing more tasks!"""
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')
    except Exception as e:
        print(f"Error in balance check: {e}")
        bot.send_message(message.chat.id, "❌ Error fetching balance. Please try again.")

# --- My Stats ---
@bot.message_handler(func=lambda message: message.text == '📊 My Stats')
def my_stats(message):
    """Show user statistics"""
    try:
        user = get_user(message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ User not found. Use /start")
            return
        
        joined_date = user.get('joined_date')
        if isinstance(joined_date, str):
            joined_date = datetime.fromisoformat(joined_date)
        
        last_active = user.get('last_active')
        if isinstance(last_active, str):
            last_active = datetime.fromisoformat(last_active)
        
        msg = f"""📊 *Your Statistics*

👤 Username: @{user.get('username', 'N/A')}
🆔 User ID: `{user['user_id']}`
📅 Joined: {joined_date.strftime('%d %b %Y') if joined_date else 'Unknown'}
🕐 Last Active: {last_active.strftime('%d %b %Y %H:%M') if last_active else 'N/A'}

💰 *Financial Stats*
Balance: {format_balance(user.get('balance', 0))}
Total Earned: {format_balance(user.get('total_earned', 0))}
Total Withdrawn: {format_balance(user.get('total_withdrawn', 0))}

👥 *Referral Network*
Your Code: `{user.get('referral_code', 'N/A')}`
Total Referrals: {user.get('total_referrals', 0)}
Referral Earnings: {format_balance(user.get('referral_earnings', 0))}
Referred By: {user.get('referred_by', 'None')}

📈 *Activity*
📝 Tasks Done: {len(user.get('completed_tasks', []))}
🔗 Visits Done: {len(user.get('completed_visits', []))}

🚀 Share your referral code with friends!"""
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')
    except Exception as e:
        print(f"Error in stats: {e}")
        bot.send_message(message.chat.id, "❌ Error loading stats. Please try again.")

# --- Refer & Earn ---
@bot.message_handler(func=lambda message: message.text == '👥 Refer & Earn')
def refer_earn(message):
    """Show referral program details"""
    try:
        user = get_user(message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ User not found. Use /start")
            return
        
        bot_username = bot.get_me().username
        bot_link = f"https://t.me/{bot_username}?start={user['referral_code']}"
        
        msg = f"""👥 *Refer & Earn Program*

💰 Earn ₹2 for each friend who joins!

📌 *How It Works:*
1️⃣ Share your referral link
2️⃣ Friend joins using your link
3️⃣ You get ₹2 instantly
4️⃣ No limit on referrals!

🔑 *Your Referral Code:*
`{user['referral_code']}`

🔗 *Your Referral Link:*
{bot_link}

📊 *Your Performance:*
✅ Total Referrals: {user.get('total_referrals', 0)}
💵 Total Earned: {format_balance(user.get('referral_earnings', 0))}

📢 *Tips for Success:*
• Share on social media
• Post in groups
• Tell your friends
• Create YouTube videos

Start sharing now! 🚀"""
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown', disable_web_page_preview=True)
    except Exception as e:
        print(f"Error in refer: {e}")
        bot.send_message(message.chat.id, "❌ Error loading referral info. Please try again.")

# --- Tasks Menu ---
@bot.message_handler(func=lambda message: message.text == '📝 Tasks')
def show_tasks(message):
    """Show available tasks"""
    try:
        tasks = list(tasks_collection.find({'active': True}).limit(10))
        
        if not tasks:
            bot.send_message(
                message.chat.id, 
                "📝 *No Tasks Available*\n\nCheck back later for new tasks!",
                parse_mode='Markdown'
            )
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for task in tasks:
            btn_text = f"{task['title']} - {format_balance(task['amount'])}"
            callback_data = f"task_{task['_id']}"
            btn = types.InlineKeyboardButton(btn_text, callback_data=callback_data)
            markup.add(btn)
        
        bot.send_message(
            message.chat.id, 
            "📝 *Available Tasks*\n\nComplete these tasks to earn money:\nClick on a task to view details.",
            parse_mode='Markdown', 
            reply_markup=markup
        )
    except Exception as e:
        print(f"Error in tasks: {e}")
        bot.send_message(message.chat.id, "❌ Error loading tasks. Please try again.")

# --- Handle Task Selection ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('task_') and not call.data.startswith('task_submit_'))
def handle_task(call):
    """Show task details"""
    try:
        task_id = call.data.split('_')[1]
        
        # Validate ObjectId
        try:
            task_obj_id = ObjectId(task_id)
        except:
            bot.answer_callback_query(call.id, "❌ Invalid task!")
            return
        
        task = tasks_collection.find_one({'_id': task_obj_id})
        
        if not task:
            bot.answer_callback_query(call.id, "❌ Task not found!")
            return
        
        # Check if user already completed this task
        user = get_user(call.from_user.id)
        if task_id in user.get('completed_tasks', []):
            bot.answer_callback_query(call.id, "✅ You already completed this task!")
            return
        
        task_msg = f"""📝 *{task['title']}*

💰 Reward: {format_balance(task['amount'])}

📋 *Description:*
{task.get('description', 'Complete the task')}

🔗 *Task Link:*
{task.get('link', 'No link provided')}

✅ *Steps to Complete:*
1. Click the link above
2. Complete the required action
3. Take a screenshot
4. Submit using the button below

⚠️ *Important:*
• Follow instructions carefully
• Fake submissions = Account Ban
• One submission per task
• Wait for admin approval"""
        
        markup = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton(
            "📸 Submit Screenshot", 
            callback_data=f"task_submit_{task_id}"
        )
        btn2 = types.InlineKeyboardButton(
            "🔙 Back to Tasks", 
            callback_data="back_to_tasks"
        )
        markup.add(btn1, btn2)
        
        try:
            bot.edit_message_text(
                task_msg, 
                call.message.chat.id, 
                call.message.message_id,
                parse_mode='Markdown', 
                reply_markup=markup,
                disable_web_page_preview=True
            )
        except:
            bot.send_message(
                call.message.chat.id,
                task_msg,
                parse_mode='Markdown',
                reply_markup=markup,
                disable_web_page_preview=True
            )
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        print(f"Error in task handler: {e}")
        bot.answer_callback_query(call.id, "❌ Error loading task. Please try again.")

# --- Submit Task Screenshot ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('task_submit_'))
def submit_task_request(call):
    """Request screenshot from user"""
    try:
        task_id = call.data.split('_')[2]
        
        try:
            task_obj_id = ObjectId(task_id)
        except:
            bot.answer_callback_query(call.id, "❌ Invalid task!")
            return
        
        task = tasks_collection.find_one({'_id': task_obj_id})
        
        if not task:
            bot.answer_callback_query(call.id, "❌ Task not found!")
            return
        
        bot.answer_callback_query(call.id)
        
        msg = bot.send_message(
            call.message.chat.id,
            f"📸 *Submit Screenshot for:* {task['title']}\n\n"
            "Please send the screenshot now.\n"
            "Make sure it clearly shows the completed action.\n\n"
            "Type 'cancel' to cancel.",
            parse_mode='Markdown'
        )
        
        bot.register_next_step_handler(msg, process_task_screenshot, task_id)
        
    except Exception as e:
        print(f"Error in screenshot request: {e}")
        bot.answer_callback_query(call.id, "❌ Error. Please try again.")

def process_task_screenshot(message, task_id):
    """Process task screenshot submission"""
    try:
        if message.text and message.text.lower() == 'cancel':
            bot.send_message(message.chat.id, "❌ Submission cancelled.", reply_markup=main_keyboard())
            return
        
        if not message.photo:
            bot.send_message(
                message.chat.id,
                "❌ Please send a valid screenshot photo!\n"
                "Try submitting the task again from the Tasks menu."
            )
            return
        
        # Get the highest quality photo
        photo_file_id = message.photo[-1].file_id
        
        # Get task details
        task = tasks_collection.find_one({'_id': ObjectId(task_id)})
        if not task:
            bot.send_message(message.chat.id, "❌ Task not found!")
            return
        
        # Save submission
        submission = {
            'user_id': str(message.from_user.id),
            'username': message.from_user.username or "Unknown",
            'first_name': message.from_user.first_name or "User",
            'task_id': task_id,
            'task_title': task['title'],
            'task_amount': task['amount'],
            'screenshot': photo_file_id,
            'status': 'pending',
            'submitted_at': datetime.now(),
            'reviewed_at': None,
            'reviewed_by': None
        }
        
        result = task_submissions_collection.insert_one(submission)
        
        # Send confirmation to user
        bot.send_message(
            message.chat.id,
            f"✅ *Task Submitted Successfully!*\n\n"
            f"📝 Task: {task['title']}\n"
            f"💰 Reward: {format_balance(task['amount'])}\n"
            f"🆔 Submission ID: `{result.inserted_id}`\n\n"
            f"⏳ Status: Pending Review\n\n"
            f"Your submission will be reviewed by admin.\n"
            f"You'll receive the reward once approved.\n\n"
            f"⚠️ Review may take up to 24 hours.",
            parse_mode='Markdown',
            reply_markup=main_keyboard()
        )
        
        # Notify admin if available
        if ADMIN_USER_ID:
            try:
                admin_msg = f"📋 *New Task Submission*\n\n"
                admin_msg += f"👤 User: @{message.from_user.username}\n"
                admin_msg += f"🆔 User ID: `{message.from_user.id}`\n"
                admin_msg += f"📝 Task: {task['title']}\n"
                admin_msg += f"💰 Reward: {format_balance(task['amount'])}\n"
                admin_msg += f"🕐 Time: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                admin_msg += f"Use admin panel to review!"
                
                bot.send_message(ADMIN_USER_ID, admin_msg, parse_mode='Markdown')
            except Exception as e:
                print(f"Could not notify admin: {e}")
        
    except Exception as e:
        print(f"Error processing screenshot: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Error submitting task. Please try again.",
            reply_markup=main_keyboard()
        )

# --- Visit Tasks ---
@bot.message_handler(func=lambda message: message.text == '🔗 Visit Tasks')
def show_visit_tasks(message):
    """Show visit tasks"""
    try:
        tasks = list(visit_tasks_collection.find({'active': True}).limit(10))
        
        if not tasks:
            bot.send_message(
                message.chat.id,
                "🔗 *No Visit Tasks Available*\n\nCheck back later!",
                parse_mode='Markdown'
            )
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for task in tasks:
            btn_text = f"{task['title']} - {format_balance(task['amount'])} ({task['time_required']}s)"
            callback_data = f"visit_{task['_id']}"
            btn = types.InlineKeyboardButton(btn_text, callback_data=callback_data)
            markup.add(btn)
        
        bot.send_message(
            message.chat.id,
            "🔗 *Visit & Earn*\n\nVisit websites and stay for the required time to earn!\nClick on a task to start.",
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception as e:
        print(f"Error in visit tasks: {e}")
        bot.send_message(message.chat.id, "❌ Error loading visit tasks.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('visit_'))
def handle_visit_task(call):
    """Handle visit task selection"""
    try:
        task_id = call.data.split('_')[1]
        
        try:
            task_obj_id = ObjectId(task_id)
        except:
            bot.answer_callback_query(call.id, "❌ Invalid task!")
            return
        
        task = visit_tasks_collection.find_one({'_id': task_obj_id})
        
        if not task:
            bot.answer_callback_query(call.id, "❌ Task not found!")
            return
        
        user_id = str(call.from_user.id)
        
        # Check 24-hour cooldown
        recent = completed_visits_collection.find_one({
            'user_id': user_id,
            'task_id': task_id,
            'completed_at': {'$gte': datetime.now() - timedelta(hours=24)}
        })
        
        if recent:
            time_diff = datetime.now() - recent['completed_at']
            hours_left = 24 - (time_diff.total_seconds() / 3600)
            minutes_left = int(hours_left * 60)
            
            bot.answer_callback_query(
                call.id,
                f"⏰ You can do this task again in {int(hours_left)}h {minutes_left % 60}m!"
            )
            return
        
        # Show task details with timer
        visit_msg = f"""🔗 *{task['title']}*

💰 Reward: {format_balance(task['amount'])}
⏱️ Time Required: {task['time_required']} seconds
📝 Description: {task.get('description', 'Visit the website')}

🔗 *Website Link:*
{task['link']}

⚠️ *Important Instructions:*
1️⃣ Click the link and stay on the website
2️⃣ Wait for {task['time_required']} seconds
3️⃣ Don't close the browser
4️⃣ Complete any captcha if shown
5️⃣ Then click "Complete Visit" below

⏰ The timer starts when you click the link!"""
        
        markup = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton(
            "✅ Complete Visit", 
            callback_data=f"complete_visit_{task_id}"
        )
        btn2 = types.InlineKeyboardButton(
            "🔙 Back", 
            callback_data="back_to_visits"
        )
        markup.add(btn1, btn2)
        
        # Store visit start time
        users_collection.update_one(
            {'user_id': user_id},
            {'$set': {f'visit_start_{task_id}': datetime.now()}}
        )
        
        try:
            bot.edit_message_text(
                visit_msg,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=markup,
                disable_web_page_preview=True
            )
        except:
            bot.send_message(
                call.message.chat.id,
                visit_msg,
                parse_mode='Markdown',
                reply_markup=markup,
                disable_web_page_preview=True
            )
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        print(f"Error in visit task: {e}")
        bot.answer_callback_query(call.id, "❌ Error. Please try again.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('complete_visit_'))
def complete_visit(call):
    """Complete visit task"""
    try:
        task_id = call.data.split('_')[2]
        user_id = str(call.from_user.id)
        
        task = visit_tasks_collection.find_one({'_id': ObjectId(task_id)})
        
        if not task:
            bot.answer_callback_query(call.id, "❌ Task not found!")
            return
        
        # Check if time requirement is met
        user = get_user(user_id)
        start_time = user.get(f'visit_start_{task_id}')
        
        if not start_time:
            bot.answer_callback_query(call.id, "❌ Please start the visit task first!")
            return
        
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        
        time_elapsed = (datetime.now() - start_time).total_seconds()
        
        if time_elapsed >= task['time_required']:
            # Reward user
            amount = task['amount']
            update_user_balance(user_id, amount, 'add')
            add_transaction(user_id, amount, 'visit_task', f'Completed: {task["title"]}')
            
            # Update user stats
            users_collection.update_one(
                {'user_id': user_id},
                {
                    '$inc': {'total_earned': amount},
                    '$push': {'completed_visits': task_id},
                    '$unset': {f'visit_start_{task_id}': ''}
                }
            )
            
            # Record completion
            completed_visits_collection.insert_one({
                'user_id': user_id,
                'task_id': task_id,
                'task_title': task['title'],
                'completed_at': datetime.now(),
                'amount': amount
            })
            
            bot.answer_callback_query(call.id, f"✅ Completed! Earned {format_balance(amount)}!")
            
            try:
                bot.edit_message_text(
                    f"✅ *Visit Completed!*\n\n"
                    f"You earned {format_balance(amount)}!\n"
                    f"Task: {task['title']}\n\n"
                    f"🕐 You can do this task again after 24 hours.",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
            except:
                bot.send_message(
                    call.message.chat.id,
                    f"✅ *Visit Completed!*\n\n"
                    f"You earned {format_balance(amount)}!\n"
                    f"Task: {task['title']}\n\n"
                    f"🕐 You can do this task again after 24 hours.",
                    parse_mode='Markdown'
                )
        else:
            remaining = int(task['time_required'] - time_elapsed)
            bot.answer_callback_query(
                call.id,
                f"⏰ Please wait {remaining} more seconds!"
            )
            
    except Exception as e:
        print(f"Error completing visit: {e}")
        bot.answer_callback_query(call.id, "❌ Error. Please try again.")

# --- Callback for Back Buttons ---
@bot.callback_query_handler(func=lambda call: call.data in ['back_to_tasks', 'back_to_visits'])
def handle_back_callback(call):
    """Handle back button callbacks"""
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        
        if call.data == 'back_to_tasks':
            show_tasks(call.message)
        else:
            show_visit_tasks(call.message)
    except Exception as e:
        print(f"Error in back callback: {e}")

# --- Withdrawal System ---
@bot.message_handler(func=lambda message: message.text == '💸 Withdraw')
def withdrawal_menu(message):
    """Show withdrawal menu"""
    try:
        user = get_user(message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ User not found. Use /start")
            return
        
        balance = user.get('balance', 0)
        
        # Check pending withdrawal
        pending = withdrawal_requests_collection.find_one({
            'user_id': str(message.from_user.id),
            'status': 'pending'
        })
        
        if pending:
            bot.send_message(
                message.chat.id,
                f"⚠️ *You have a pending withdrawal request!*\n\n"
                f"Amount: {format_balance(pending['amount'])}\n"
                f"Method: {pending['method'].upper()}\n\n"
                f"Please wait for it to be processed before requesting another.",
                parse_mode='Markdown'
            )
            return
        
        if balance < 50:
            bot.send_message(
                message.chat.id,
                f"❌ *Insufficient Balance*\n\n"
                f"Your balance: {format_balance(balance)}\n"
                f"Minimum withdrawal: ₹50\n\n"
                f"Complete more tasks to withdraw!",
                parse_mode='Markdown'
            )
            return
        
        msg = f"""💸 *Withdraw Your Earnings*

💰 Available Balance: {format_balance(balance)}

📋 *Withdrawal Methods:*
• 💳 UPI: Min ₹50
• 🏦 Bank Transfer: Min ₹100
• ₿ Bitcoin: Min ₹200

⚠️ *Important:*
• Processing Time: 24-48 hours
• No processing fees
• One request at a time
• Check details before submitting

Select your preferred method:"""
        
        bot.send_message(
            message.chat.id,
            msg,
            parse_mode='Markdown',
            reply_markup=withdrawal_methods_keyboard()
        )
    except Exception as e:
        print(f"Error in withdrawal menu: {e}")
        bot.send_message(message.chat.id, "❌ Error loading withdrawal menu.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('withdraw_'))
def process_withdrawal_method(call):
    """Process withdrawal method selection"""
    try:
        method = call.data.split('_')[1]
        user = get_user(call.from_user.id)
        
        if not user:
            bot.answer_callback_query(call.id, "❌ User not found!")
            return
        
        balance = user.get('balance', 0)
        
        min_amounts = {'upi': 50, 'bank': 100, 'crypto': 200}
        method_names = {'upi': 'UPI', 'bank': 'Bank Transfer', 'crypto': 'Bitcoin'}
        
        min_amount = min_amounts.get(method, 50)
        method_name = method_names.get(method, method.upper())
        
        if balance < min_amount:
            bot.answer_callback_query(
                call.id,
                f"❌ Minimum withdrawal for {method_name} is ₹{min_amount}"
            )
            return
        
        bot.answer_callback_query(call.id)
        
        msg = bot.send_message(
            call.message.chat.id,
            f"💸 *{method_name} Withdrawal*\n\n"
            f"💰 Available Balance: {format_balance(balance)}\n"
            f"📊 Minimum: ₹{min_amount}\n\n"
            f"👇 Please enter the amount you want to withdraw:\n\n"
            f"Type 'cancel' to cancel.",
            parse_mode='Markdown'
        )
        
        bot.register_next_step_handler(msg, process_withdrawal_amount, method, min_amount)
        
    except Exception as e:
        print(f"Error in withdrawal method: {e}")
        bot.answer_callback_query(call.id, "❌ Error. Please try again.")

def process_withdrawal_amount(message, method, min_amount):
    """Process withdrawal amount"""
    try:
        if message.text and message.text.lower() == 'cancel':
            bot.send_message(
                message.chat.id,
                "❌ Withdrawal cancelled.",
                reply_markup=main_keyboard()
            )
            return
        
        try:
            amount = float(message.text)
        except ValueError:
            bot.send_message(message.chat.id, "❌ Please enter a valid number!")
            return
        
        if amount < min_amount:
            bot.send_message(
                message.chat.id,
                f"❌ Minimum withdrawal for this method is ₹{min_amount}!"
            )
            return
        
        user = get_user(message.from_user.id)
        
        if amount > user.get('balance', 0):
            bot.send_message(
                message.chat.id,
                f"❌ Insufficient balance! Your balance: {format_balance(user['balance'])}"
            )
            return
        
        # Ask for account details based on method
        if method == 'upi':
            msg = bot.send_message(
                message.chat.id,
                "📱 Please enter your UPI ID:\n"
                "Example: yourname@okhdfcbank"
            )
            bot.register_next_step_handler(msg, save_withdrawal_request, method, amount)
            
        elif method == 'bank':
            msg = bot.send_message(
                message.chat.id,
                "🏦 Please enter your bank details in this format:\n\n"
                "Account Holder Name\n"
                "Account Number\n"
                "IFSC Code\n"
                "Bank Name\n\n"
                "Example:\n"
                "John Doe\n"
                "1234567890\n"
                "HDFC0001234\n"
                "HDFC Bank"
            )
            bot.register_next_step_handler(msg, save_withdrawal_request, method, amount)
            
        else:  # crypto
            msg = bot.send_message(
                message.chat.id,
                "₿ Please enter your Bitcoin wallet address:"
            )
            bot.register_next_step_handler(msg, save_withdrawal_request, method, amount)
            
    except Exception as e:
        print(f"Error in withdrawal amount: {e}")
        bot.send_message(message.chat.id, "❌ Error processing amount. Please try again.")

def save_withdrawal_request(message, method, amount):
    """Save withdrawal request"""
    try:
        if message.text and message.text.lower() == 'cancel':
            bot.send_message(message.chat.id, "❌ Withdrawal cancelled.")
            return
        
        account_details = message.text
        
        # Create withdrawal request
        request_data = {
            'user_id': str(message.from_user.id),
            'username': message.from_user.username or "Unknown",
            'first_name': message.from_user.first_name or "User",
            'amount': amount,
            'method': method,
            'account_details': account_details,
            'status': 'pending',
            'requested_at': datetime.now(),
            'processed_at': None,
            'remarks': ''
        }
        
        result = withdrawal_requests_collection.insert_one(request_data)
        
        # Deduct balance
        update_user_balance(message.from_user.id, amount, 'subtract')
        users_collection.update_one(
            {'user_id': str(message.from_user.id)},
            {'$inc': {'total_withdrawn': amount}}
        )
        
        add_transaction(
            message.from_user.id,
            -amount,
            'withdrawal',
            f'Withdrawal via {method.upper()}'
        )
        
        bot.send_message(
            message.chat.id,
            f"✅ *Withdrawal Request Submitted!*\n\n"
            f"💰 Amount: {format_balance(amount)}\n"
            f"📱 Method: {method.upper()}\n"
            f"🆔 Request ID: `{result.inserted_id}`\n"
            f"📅 Date: {datetime.now().strftime('%d %b %Y, %I:%M %p')}\n\n"
            f"⏳ Status: Pending\n\n"
            f"Your request will be processed within 24-48 hours.\n"
            f"Use /check_withdrawal to track status.",
            parse_mode='Markdown',
            reply_markup=main_keyboard()
        )
        
        # Notify admin
        if ADMIN_USER_ID:
            try:
                admin_msg = f"💸 *New Withdrawal Request*\n\n"
                admin_msg += f"👤 User: @{message.from_user.username}\n"
                admin_msg += f"🆔 User ID: `{message.from_user.id}`\n"
                admin_msg += f"💰 Amount: {format_balance(amount)}\n"
                admin_msg += f"📱 Method: {method.upper()}\n"
                admin_msg += f"📝 Details: {account_details}\n"
                admin_msg += f"🕐 Time: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                
                bot.send_message(ADMIN_USER_ID, admin_msg, parse_mode='Markdown')
            except Exception as e:
                print(f"Could not notify admin: {e}")
        
    except Exception as e:
        print(f"Error saving withdrawal: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Error submitting withdrawal. Please try again.",
            reply_markup=main_keyboard()
        )

@bot.message_handler(commands=['check_withdrawal'])
def check_withdrawal_status(message):
    """Check withdrawal status"""
    try:
        requests = list(
            withdrawal_requests_collection.find({'user_id': str(message.from_user.id)})
            .sort('requested_at', -1)
            .limit(5)
        )
        
        if not requests:
            bot.send_message(message.chat.id, "📝 No withdrawal requests found!")
            return
        
        msg = "💸 *Your Recent Withdrawals*\n\n"
        
        for req in requests:
            status_emoji = {'pending': '⏳', 'approved': '✅', 'rejected': '❌'}
            emoji = status_emoji.get(req['status'], '❓')
            
            req_date = req['requested_at']
            if isinstance(req_date, str):
                req_date = datetime.fromisoformat(req_date)
            
            msg += f"{emoji} *{req['method'].upper()}*\n"
            msg += f"   Amount: {format_balance(req['amount'])}\n"
            msg += f"   Status: {req['status'].upper()}\n"
            msg += f"   Date: {req_date.strftime('%d/%m/%Y')}\n"
            
            if req.get('remarks'):
                msg += f"   Note: {req['remarks']}\n"
            
            msg += "\n"
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Error checking withdrawals: {e}")
        bot.send_message(message.chat.id, "❌ Error checking withdrawal status.")

# --- Admin Panel ---
@bot.message_handler(func=lambda message: message.text == ADMIN_PASSWORD)
def activate_admin(message):
    """Activate admin panel"""
    global ADMIN_USER_ID
    ADMIN_USER_ID = message.chat.id
    
    bot.send_message(
        message.chat.id,
        "✅ *Admin Panel Activated!*\n\n"
        "Welcome Admin! Use the buttons below to manage the bot.\n\n"
        "⚠️ Keep your admin session secure!",
        parse_mode='Markdown',
        reply_markup=admin_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == '🔙 Back to Menu')
def back_to_menu(message):
    """Return to main menu"""
    global ADMIN_USER_ID
    if is_admin(message):
        ADMIN_USER_ID = None
        bot.send_message(
            message.chat.id,
            "👋 Admin session ended. Returning to user menu...",
            reply_markup=main_keyboard()
        )
    else:
        bot.send_message(
            message.chat.id,
            "Returning to main menu...",
            reply_markup=main_keyboard()
        )

@bot.message_handler(func=lambda message: message.text == '📊 Total Users' and is_admin(message))
def admin_total_users(message):
    """Show total users statistics"""
    try:
        total = users_collection.count_documents({})
        active_24h = users_collection.count_documents({
            'last_active': {'$gte': datetime.now() - timedelta(hours=24)}
        })
        
        # Calculate total balance safely
        pipeline = [
            {'$group': {'_id': None, 'total_balance': {'$sum': '$balance'}}}
        ]
        result = list(users_collection.aggregate(pipeline))
        total_balance = result[0]['total_balance'] if result else 0
        
        msg = f"""📊 *Bot Statistics*

👥 *User Stats*
• Total Users: {total}
• Active Today: {active_24h}
• Inactive: {total - active_24h}

💰 *Financial Stats*
• Total User Balance: {format_balance(total_balance)}
• Average Balance: {format_balance(total_balance/total if total > 0 else 0)}

📈 *Growth*
• Users Today: Check analytics
• New Users: Use /stats for details"""
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')
    except Exception as e:
        print(f"Error in admin stats: {e}")
        bot.send_message(message.chat.id, "❌ Error loading statistics.")

@bot.message_handler(func=lambda message: message.text == '💰 Total Balance' and is_admin(message))
def admin_total_balance(message):
    """Show total balance statistics"""
    try:
        pipeline = [
            {
                '$group': {
                    '_id': None,
                    'total_balance': {'$sum': '$balance'},
                    'total_earned': {'$sum': '$total_earned'},
                    'total_withdrawn': {'$sum': '$total_withdrawn'},
                    'total_referral': {'$sum': '$referral_earnings'}
                }
            }
        ]
        result = list(users_collection.aggregate(pipeline))
        
        if result:
            stats = result[0]
            total_balance = stats.get('total_balance', 0)
            total_earned = stats.get('total_earned', 0)
            total_withdrawn = stats.get('total_withdrawn', 0)
            total_referral = stats.get('total_referral', 0)
        else:
            total_balance = total_earned = total_withdrawn = total_referral = 0
        
        pending_withdrawals = withdrawal_requests_collection.count_documents({'status': 'pending'})
        
        msg = f"""💰 *Financial Overview*

💵 *Balance Summary*
• Total User Balance: {format_balance(total_balance)}
• Total Earned: {format_balance(total_earned)}
• Total Withdrawn: {format_balance(total_withdrawn)}
• Referral Payouts: {format_balance(total_referral)}

📊 *Profit Analysis*
• System Revenue: {format_balance(total_earned)}
• User Withdrawals: {format_balance(total_withdrawn)}
• Net Profit/Loss: {format_balance(total_earned - total_withdrawn)}

📋 *Pending*
• Pending Withdrawals: {pending_withdrawals}"""
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')
    except Exception as e:
        print(f"Error in balance stats: {e}")
        bot.send_message(message.chat.id, "❌ Error loading statistics.")

@bot.message_handler(func=lambda message: message.text == '💸 Withdrawal Requests' and is_admin(message))
def admin_withdrawals(message):
    """View withdrawal requests"""
    try:
        pending = list(withdrawal_requests_collection.find({'status': 'pending'}).limit(10))
        
        if not pending:
            bot.send_message(message.chat.id, "✅ No pending withdrawal requests!")
            return
        
        for req in pending:
            markup = types.InlineKeyboardMarkup(row_width=2)
            btn1 = types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_wd_{req['_id']}")
            btn2 = types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_wd_{req['_id']}")
            markup.add(btn1, btn2)
            
            req_date = req['requested_at']
            if isinstance(req_date, str):
                req_date = datetime.fromisoformat(req_date)
            
            msg = f"""💸 *Withdrawal Request*

👤 User: @{req.get('username', 'Unknown')}
🆔 User ID: `{req['user_id']}`
💰 Amount: {format_balance(req['amount'])}
📱 Method: {req['method'].upper()}
📝 Details: `{req['account_details']}`
📅 Requested: {req_date.strftime('%d/%m/%Y %H:%M')}
🆔 Request ID: `{req['_id']}`"""
            
            bot.send_message(message.chat.id, msg, parse_mode='Markdown', reply_markup=markup)
            
    except Exception as e:
        print(f"Error in admin withdrawals: {e}")
        bot.send_message(message.chat.id, "❌ Error loading withdrawal requests.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_wd_'))
def approve_withdrawal(call):
    """Approve withdrawal request"""
    if not is_admin(call.message):
        bot.answer_callback_query(call.id, "❌ Unauthorized!")
        return
    
    try:
        request_id = call.data.split('_')[2]
        
        withdrawal_requests_collection.update_one(
            {'_id': ObjectId(request_id)},
            {
                '$set': {
                    'status': 'approved',
                    'processed_at': datetime.now()
                }
            }
        )
        
        req = withdrawal_requests_collection.find_one({'_id': ObjectId(request_id)})
        
        if req:
            try:
                bot.send_message(
                    int(req['user_id']),
                    f"✅ *Withdrawal Approved!*\n\n"
                    f"Amount: {format_balance(req['amount'])}\n"
                    f"Method: {req['method'].upper()}\n\n"
                    f"Your payment has been processed.\n"
                    f"Thank you for using our service! 🙏",
                    parse_mode='Markdown'
                )
            except Exception as e:
                print(f"Could not notify user: {e}")
        
        bot.answer_callback_query(call.id, "✅ Withdrawal approved!")
        bot.edit_message_text(
            "✅ *Withdrawal Approved*",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        print(f"Error approving withdrawal: {e}")
        bot.answer_callback_query(call.id, "❌ Error. Please try again.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_wd_'))
def reject_withdrawal(call):
    """Reject withdrawal request"""
    if not is_admin(call.message):
        bot.answer_callback_query(call.id, "❌ Unauthorized!")
        return
    
    try:
        request_id = call.data.split('_')[2]
        req = withdrawal_requests_collection.find_one({'_id': ObjectId(request_id)})
        
        if req:
            # Refund the amount
            update_user_balance(req['user_id'], req['amount'], 'add')
            
            withdrawal_requests_collection.update_one(
                {'_id': ObjectId(request_id)},
                {
                    '$set': {
                        'status': 'rejected',
                        'processed_at': datetime.now(),
                        'remarks': 'Invalid details or policy violation'
                    }
                }
            )
            
            try:
                bot.send_message(
                    int(req['user_id']),
                    f"❌ *Withdrawal Rejected*\n\n"
                    f"Amount: {format_balance(req['amount'])}\n"
                    f"Method: {req['method'].upper()}\n\n"
                    f"Amount has been refunded to your wallet.\n"
                    f"Please check your details and try again.\n\n"
                    f"Contact support if needed.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                print(f"Could not notify user: {e}")
        
        bot.answer_callback_query(call.id, "❌ Withdrawal rejected!")
        bot.edit_message_text(
            "❌ *Withdrawal Rejected*",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        print(f"Error rejecting withdrawal: {e}")
        bot.answer_callback_query(call.id, "❌ Error. Please try again.")

@bot.message_handler(func=lambda message: message.text == '📋 Task Submissions' and is_admin(message))
def admin_submissions(message):
    """View task submissions"""
    try:
        submissions = list(task_submissions_collection.find({'status': 'pending'}).limit(10))
        
        if not submissions:
            bot.send_message(message.chat.id, "✅ No pending task submissions!")
            return
        
        for sub in submissions:
            markup = types.InlineKeyboardMarkup(row_width=2)
            btn1 = types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_sub_{sub['_id']}")
            btn2 = types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_sub_{sub['_id']}")
            markup.add(btn1, btn2)
            
            sub_date = sub['submitted_at']
            if isinstance(sub_date, str):
                sub_date = datetime.fromisoformat(sub_date)
            
            caption = f"""📋 *Task Submission*

👤 User: @{sub.get('username', 'Unknown')}
🆔 User ID: `{sub['user_id']}`
📝 Task: {sub.get('task_title', 'Unknown')}
💰 Reward: {format_balance(sub.get('task_amount', 0))}
📅 Submitted: {sub_date.strftime('%d/%m/%Y %H:%M')}
🆔 Submission ID: `{sub['_id']}`"""
            
            try:
                bot.send_photo(
                    message.chat.id,
                    sub['screenshot'],
                    caption=caption,
                    parse_mode='Markdown',
                    reply_markup=markup
                )
            except Exception as e:
                bot.send_message(
                    message.chat.id,
                    f"{caption}\n\n⚠️ Screenshot not available",
                    parse_mode='Markdown',
                    reply_markup=markup
                )
                
    except Exception as e:
        print(f"Error in admin submissions: {e}")
        bot.send_message(message.chat.id, "❌ Error loading submissions.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_sub_'))
def approve_submission(call):
    """Approve task submission"""
    if not is_admin(call.message):
        bot.answer_callback_query(call.id, "❌ Unauthorized!")
        return
    
    try:
        submission_id = call.data.split('_')[2]
        submission = task_submissions_collection.find_one({'_id': ObjectId(submission_id)})
        
        if not submission:
            bot.answer_callback_query(call.id, "❌ Submission not found!")
            return
        
        # Get task details
        task = tasks_collection.find_one({'_id': ObjectId(submission['task_id'])})
        
        if task:
            # Add reward
            amount = task['amount']
            update_user_balance(submission['user_id'], amount, 'add')
            add_transaction(submission['user_id'], amount, 'task', f'Task: {task["title"]}')
            
            # Update user stats
            users_collection.update_one(
                {'user_id': submission['user_id']},
                {
                    '$inc': {'total_earned': amount},
                    '$push': {'completed_tasks': submission['task_id']}
                }
            )
            
            # Record completion
            completed_tasks_collection.insert_one({
                'user_id': submission['user_id'],
                'task_id': submission['task_id'],
                'completed_at': datetime.now(),
                'amount': amount
            })
            
            # Notify user
            try:
                bot.send_message(
                    int(submission['user_id']),
                    f"✅ *Task Approved!*\n\n"
                    f"Task: {task['title']}\n"
                    f"Reward: {format_balance(amount)}\n\n"
                    f"Keep completing tasks to earn more!",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        # Update submission status
        task_submissions_collection.update_one(
            {'_id': ObjectId(submission_id)},
            {'$set': {'status': 'approved', 'reviewed_at': datetime.now()}}
        )
        
        bot.answer_callback_query(call.id, "✅ Task approved!")
        
        try:
            bot.edit_message_caption(
                "✅ *Approved*\nTask approved and user rewarded!",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown'
            )
        except:
            pass
        
    except Exception as e:
        print(f"Error approving submission: {e}")
        bot.answer_callback_query(call.id, "❌ Error. Please try again.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_sub_'))
def reject_submission(call):
    """Reject task submission"""
    if not is_admin(call.message):
        bot.answer_callback_query(call.id, "❌ Unauthorized!")
        return
    
    try:
        submission_id = call.data.split('_')[2]
        submission = task_submissions_collection.find_one({'_id': ObjectId(submission_id)})
        
        if not submission:
            bot.answer_callback_query(call.id, "❌ Submission not found!")
            return
        
        task_submissions_collection.update_one(
            {'_id': ObjectId(submission_id)},
            {'$set': {'status': 'rejected', 'reviewed_at': datetime.now()}}
        )
        
        # Notify user
        try:
            bot.send_message(
                int(submission['user_id']),
                f"❌ *Task Submission Rejected*\n\n"
                f"Task: {submission.get('task_title', 'Unknown')}\n\n"
                f"Please complete the task correctly and resubmit.\n"
                f"Make sure to follow all instructions.",
                parse_mode='Markdown'
            )
        except:
            pass
        
        bot.answer_callback_query(call.id, "❌ Task rejected!")
        
        try:
            bot.edit_message_caption(
                "❌ *Rejected*\nSubmission was rejected.",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown'
            )
        except:
            pass
        
    except Exception as e:
        print(f"Error rejecting submission: {e}")
        bot.answer_callback_query(call.id, "❌ Error. Please try again.")

@bot.message_handler(func=lambda message: message.text == '📢 Broadcast Message' and is_admin(message))
def admin_broadcast(message):
    """Send broadcast message"""
    msg = bot.send_message(
        message.chat.id,
        "📢 *Broadcast Message*\n\n"
        "Send the message you want to broadcast to all users.\n"
        "Type 'cancel' to cancel.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    """Process broadcast message"""
    if not is_admin(message):
        return
    
    if message.text and message.text.lower() == 'cancel':
        bot.send_message(message.chat.id, "❌ Broadcast cancelled.")
        return
    
    # Ask for confirmation
    markup = types.InlineKeyboardMarkup()
    btn1 = types.InlineKeyboardButton("✅ Send", callback_data="confirm_broadcast")
    btn2 = types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")
    markup.add(btn1, btn2)
    
    # Store broadcast message temporarily
    bot.send_message(
        message.chat.id,
        f"📢 *Confirm Broadcast*\n\n"
        f"The following message will be sent to ALL users:\n\n"
        f"{message.text}\n\n"
        f"Are you sure?",
        parse_mode='Markdown',
        reply_markup=markup
    )
    
    # Store message text in handler data
    bot.register_next_step_handler(message, lambda m: None)

@bot.message_handler(func=lambda message: message.text in ['📢 Advertisement', 'ℹ️ About'])
def info_handlers(message):
    """Handle advertisement and about sections"""
    if message.text == '📢 Advertisement':
        total_users = users_collection.count_documents({})
        msg = f"""📢 *Advertise With Us*

Promote your business to our active users!

📊 *Our Reach:*
👥 Total Members: {total_users}+
📈 Daily Active Users: 1000+
🌍 Global Audience

💰 *Advertising Packages:*
• 📨 Broadcast Message: ₹500
• 📌 Pinned Message (24h): ₹1000
• ⭐ Featured Task: ₹2000
• 🎯 Custom Campaign: Contact us

✨ *Benefits:*
• Direct user engagement
• Instant delivery
• Targeted audience
• Analytics provided

📞 *Contact for Booking:*
@Admin_Username

Grow your business with us! 🚀"""
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')
        
    elif message.text == 'ℹ️ About':
        msg = f"""ℹ️ *About Earning Bot*

💰 *Version 2.0 - Professional*

✨ *Features:*
• Earn by completing tasks
• Earn by visiting websites
• Referral program (₹2/referral)
• Multiple withdrawal options
• 24/7 automated system
• Instant notifications

📋 *How It Works:*
1. Complete tasks
2. Earn money
3. Withdraw earnings
4. Refer friends for bonus

⚠️ *Rules:*
• One account per person
• Fake submissions = Ban
• Be honest and patient
• Follow task instructions

🔒 *Privacy & Security:*
• Your data is encrypted
• Never shared with third parties
• Secure payment processing

📊 *Statistics:*
• 99.9% Uptime
• Instant payments
• 24/7 support

📞 *Support:*
Contact @Admin for help
Response within 24 hours

Thank you for choosing our bot! ❤️"""
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')

# --- Error Handler ---
@bot.message_handler(func=lambda message: True)
def handle_unknown(message):
    """Handle unknown messages"""
    if message.text and message.text.startswith('/'):
        return  # Let other command handlers work
    
    bot.send_message(
        message.chat.id,
        "❓ I didn't understand that command.\n"
        "Please use the buttons below or /start",
        reply_markup=main_keyboard()
    )

# --- Health Check Endpoint for Railway ---
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"healthy","bot":"running"}')
        else:
            self.send_response(404)
            self.end_headers()

def run_health_server():
    """Run health check server for Railway"""
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"✅ Health check server running on port {port}")
    server.serve_forever()

# --- Main Execution ---
if __name__ == '__main__':
    print("🤖 Earning Bot v2.0 Starting...")
    print("="*50)
    
    # Print environment info
    print(f"📡 Railway Environment: {'Yes' if 'RAILWAY_ENVIRONMENT' in os.environ else 'No'}")
    print(f"🔑 Token Present: {'Yes' if API_TOKEN else 'No'}")
    print(f"💾 MongoDB Connected: {'Yes' if mongo_client else 'No'}")
    print("="*50)
    
    # Start health check server in background
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    # Remove webhook and start polling
    try:
        bot.remove_webhook()
        print("✅ Webhook removed, starting polling...")
    except Exception as e:
        print(f"⚠️ Webhook removal note: {e}")
    
    # Start bot with retry logic
    max_retries = 5
    for attempt in range(max_retries):
        try:
            print(f"🔄 Starting bot polling (Attempt {attempt + 1}/{max_retries})")
            bot.infinity_polling(timeout=30, long_polling_timeout=15)
        except Exception as e:
            print(f"❌ Bot Error (Attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10
                print(f"⏳ Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print("❌ All retry attempts failed!")
                raise e