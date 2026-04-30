# main.py - Professional Telegram Earning Bot (Railway/Railpack Ready)
import telebot
from telebot import types
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from datetime import datetime, timedelta
import time
import random
import string
import os
import sys
import logging
from bson import ObjectId
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# Railway environment variables (with fallbacks)
API_TOKEN = os.environ.get('API_TOKEN', '8384600981:AAFOkWJEw0zPqouHrwFUYw9LI7m-eLBp1KE')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Vansh@000')
MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb+srv://Vansh:Vansh000@cluster0.tqmuzxc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
DB_NAME = os.environ.get('DB_NAME', 'telegram_earning_bot')
PORT = int(os.environ.get('PORT', 8080))

# Global variables
ADMIN_USER_ID = None
bot = None
mongo_client = None
db = None

# --- MongoDB Connection ---
def connect_mongodb():
    """Connect to MongoDB with retry logic"""
    global mongo_client, db
    
    for attempt in range(3):
        try:
            logger.info(f"Connecting to MongoDB (attempt {attempt + 1}/3)...")
            
            mongo_client = MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=15000,
                connectTimeoutMS=15000,
                socketTimeoutMS=15000,
                retryWrites=True,
                w='majority'
            )
            
            # Test connection
            mongo_client.admin.command('ping')
            db = mongo_client[DB_NAME]
            
            logger.info("✅ MongoDB Connected Successfully!")
            return True
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"MongoDB Connection Failed (attempt {attempt + 1}): {e}")
            if attempt < 2:
                time.sleep(5)
            else:
                logger.critical("❌ Could not connect to MongoDB!")
                return False

# --- Initialize Collections ---
users_col = None
tasks_col = None
visit_tasks_col = None
withdrawals_col = None
completed_tasks_col = None
completed_visits_col = None
submissions_col = None
referrals_col = None

def init_collections():
    """Initialize database collections"""
    global users_col, tasks_col, visit_tasks_col, withdrawals_col
    global completed_tasks_col, completed_visits_col, submissions_col, referrals_col
    
    users_col = db['users']
    tasks_col = db['tasks']
    visit_tasks_col = db['visit_tasks']
    withdrawals_col = db['withdrawal_requests']
    completed_tasks_col = db['completed_tasks']
    completed_visits_col = db['completed_visits']
    submissions_col = db['task_submissions']
    referrals_col = db['referrals']
    
    # Create indexes
    try:
        users_col.create_index('user_id', unique=True, sparse=True)
        users_col.create_index('referral_code', sparse=True)
        logger.info("✅ Collections initialized")
    except Exception as e:
        logger.warning(f"Index creation: {e}")

# --- Health Check Server (Required for Railway) ---
class HealthHandler(BaseHTTPRequestHandler):
    """HTTP Health Check Handler for Railway"""
    
    def do_GET(self):
        if self.path in ['/', '/health']:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            status = {
                "status": "healthy",
                "bot": "running",
                "mongodb": "connected" if mongo_client else "disconnected",
                "timestamp": datetime.now().isoformat()
            }
            self.wfile.write(str(status).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress HTTP logs"""
        pass

def start_health_server():
    """Start health check HTTP server"""
    try:
        server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
        logger.info(f"🏥 Health server running on port {PORT}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Health server error: {e}")

# --- Helper Functions ---
def generate_ref_code():
    """Generate unique referral code"""
    for _ in range(10):
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not users_col.find_one({'referral_code': code}):
            return code
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

def get_user(user_id):
    """Get user from database"""
    try:
        return users_col.find_one({'user_id': str(user_id)})
    except Exception as e:
        logger.error(f"Get user error: {e}")
        return None

def update_balance(user_id, amount, operation='add'):
    """Update user balance"""
    try:
        user = get_user(user_id)
        if not user:
            return False
        
        current = float(user.get('balance', 0))
        new_balance = round(current + amount if operation == 'add' else current - amount, 2)
        
        if new_balance < 0:
            return False
        
        users_col.update_one(
            {'user_id': str(user_id)},
            {'$set': {'balance': new_balance}}
        )
        return True
    except Exception as e:
        logger.error(f"Update balance error: {e}")
        return False

def add_transaction(user_id, amount, tx_type, desc):
    """Add transaction record"""
    try:
        users_col.update_one(
            {'user_id': str(user_id)},
            {'$push': {
                'transactions': {
                    'amount': amount,
                    'type': tx_type,
                    'description': desc,
                    'date': datetime.now(),
                    'status': 'completed'
                }
            }}
        )
    except Exception as e:
        logger.error(f"Add transaction error: {e}")

def fmt_balance(amount):
    """Format balance with ₹"""
    try:
        return f"₹{float(amount):.2f}"
    except:
        return "₹0.00"

# --- Keyboards ---
def main_menu():
    """Main menu keyboard"""
    kb = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    kb.add(
        types.KeyboardButton('📝 Tasks'),
        types.KeyboardButton('🔗 Visit Tasks'),
        types.KeyboardButton('💰 Balance'),
        types.KeyboardButton('💸 Withdraw'),
        types.KeyboardButton('👥 Refer & Earn'),
        types.KeyboardButton('📢 Advertisement'),
        types.KeyboardButton('📊 My Stats'),
        types.KeyboardButton('ℹ️ About')
    )
    return kb

def admin_menu():
    """Admin panel keyboard"""
    kb = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    kb.add(
        types.KeyboardButton('📊 Total Users'),
        types.KeyboardButton('💰 Total Balance'),
        types.KeyboardButton('📝 Manage Tasks'),
        types.KeyboardButton('🔗 Manage Visit Tasks'),
        types.KeyboardButton('💸 Withdrawal Requests'),
        types.KeyboardButton('📋 Task Submissions'),
        types.KeyboardButton('📢 Broadcast Message'),
        types.KeyboardButton('🔙 Back to Menu')
    )
    return kb

def withdraw_keyboard():
    """Withdrawal methods keyboard"""
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton('💳 UPI (Min ₹50)', callback_data='wd_upi'),
        types.InlineKeyboardButton('🏦 Bank Transfer (Min ₹100)', callback_data='wd_bank'),
        types.InlineKeyboardButton('₿ Bitcoin (Min ₹200)', callback_data='wd_crypto')
    )
    return kb

# --- Command Handlers ---
@bot.message_handler(commands=['start'])
def cmd_start(message):
    """Handle /start command"""
    try:
        user_id = str(message.from_user.id)
        username = message.from_user.username or "NoUsername"
        first_name = message.from_user.first_name or "User"
        
        user = get_user(user_id)
        
        # Check for referral
        ref_code = None
        parts = message.text.split()
        if len(parts) > 1:
            ref_code = parts[1]
        
        if not user:
            # Create new user
            new_code = generate_ref_code()
            
            user_data = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'balance': 0.0,
                'total_earned': 0.0,
                'total_withdrawn': 0.0,
                'referral_code': new_code,
                'referred_by': None,
                'referral_earnings': 0.0,
                'total_referrals': 0,
                'joined_date': datetime.now(),
                'last_active': datetime.now(),
                'transactions': [],
                'completed_tasks': [],
                'completed_visits': [],
                'is_active': True
            }
            
            # Process referral
            if ref_code:
                referrer = users_col.find_one({'referral_code': ref_code})
                if referrer and referrer['user_id'] != user_id:
                    user_data['referred_by'] = referrer['user_id']
                    
                    # Credit referrer
                    bonus = 2.0
                    update_balance(referrer['user_id'], bonus, 'add')
                    add_transaction(referrer['user_id'], bonus, 'referral', f'New user: {first_name}')
                    
                    users_col.update_one(
                        {'user_id': referrer['user_id']},
                        {'$inc': {'total_referrals': 1, 'referral_earnings': bonus}}
                    )
                    
                    # Notify referrer
                    try:
                        bot.send_message(
                            int(referrer['user_id']),
                            f"🎉 *New Referral!*\n\n"
                            f"{first_name} joined using your link!\n"
                            f"💰 You earned ₹{bonus:.2f}\n\n"
                            f"Total Referrals: {referrer.get('total_referrals', 0) + 1}",
                            parse_mode='Markdown'
                        )
                    except:
                        pass
            
            users_col.insert_one(user_data)
            
            # Welcome message
            msg = f"""🎉 *Welcome {first_name}!*

💰 *Earn Money Easily:*
✅ Complete Tasks & Earn
🔗 Visit Websites & Earn
👥 Refer Friends - ₹2 each
💸 Instant Withdrawals

🔑 *Your Referral Code:*
`{new_code}`

📤 Share with friends to earn!

⚠️ *Rules:*
• One account per person
• Complete tasks honestly
• Fake submissions = Ban

Start earning now! 🚀"""
            
            bot.send_message(message.chat.id, msg, parse_mode='Markdown', reply_markup=main_menu())
        else:
            # Update last active
            users_col.update_one(
                {'user_id': user_id},
                {'$set': {'last_active': datetime.now()}}
            )
            
            msg = f"""👋 *Welcome Back {first_name}!*

💰 Balance: {fmt_balance(user.get('balance', 0))}
👥 Referrals: {user.get('total_referrals', 0)}

Start earning! 📝"""
            
            bot.send_message(message.chat.id, msg, parse_mode='Markdown', reply_markup=main_menu())
            
    except Exception as e:
        logger.error(f"Start error: {e}")
        bot.send_message(message.chat.id, "❌ Error occurred. Please try /start again.")

# --- Balance Handler ---
@bot.message_handler(func=lambda m: m.text == '💰 Balance')
def show_balance(message):
    """Show user balance"""
    try:
        user = get_user(message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ Use /start first!")
            return
        
        bal = user.get('balance', 0)
        earned = user.get('total_earned', 0)
        withdrawn = user.get('total_withdrawn', 0)
        ref_earn = user.get('referral_earnings', 0)
        ref_count = user.get('total_referrals', 0)
        tasks_done = len(user.get('completed_tasks', []))
        visits_done = len(user.get('completed_visits', []))
        
        msg = f"""💰 *Your Wallet*

💵 Balance: {fmt_balance(bal)}
📈 Total Earned: {fmt_balance(earned)}
💸 Withdrawn: {fmt_balance(withdrawn)}

👥 *Referral Stats*
👤 Referrals: {ref_count}
🎁 Referral Earnings: {fmt_balance(ref_earn)}
🔑 Code: `{user.get('referral_code', 'N/A')}`

📊 *Activity*
✅ Tasks Done: {tasks_done}
🔗 Visits Done: {visits_done}

Keep earning! 💪"""
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Balance error: {e}")
        bot.send_message(message.chat.id, "❌ Error loading balance.")

# --- Stats Handler ---
@bot.message_handler(func=lambda m: m.text == '📊 My Stats')
def show_stats(message):
    """Show detailed stats"""
    try:
        user = get_user(message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ Use /start first!")
            return
        
        joined = user.get('joined_date')
        if isinstance(joined, str):
            joined = datetime.fromisoformat(joined)
        
        last = user.get('last_active')
        if isinstance(last, str):
            last = datetime.fromisoformat(last)
        
        msg = f"""📊 *Your Statistics*

👤 @{user.get('username', 'N/A')}
🆔 `{user['user_id']}`
📅 Joined: {joined.strftime('%d %b %Y') if joined else 'N/A'}
🕐 Last Active: {last.strftime('%d %b %Y, %H:%M') if last else 'N/A'}

💰 *Financial*
Balance: {fmt_balance(user.get('balance', 0))}
Earned: {fmt_balance(user.get('total_earned', 0))}
Withdrawn: {fmt_balance(user.get('total_withdrawn', 0))}

👥 *Referral Network*
Code: `{user.get('referral_code', 'N/A')}`
Referrals: {user.get('total_referrals', 0)}
Ref Earnings: {fmt_balance(user.get('referral_earnings', 0))}
Referred By: {user.get('referred_by', 'None')}

📈 *Activity*
Tasks: {len(user.get('completed_tasks', []))}
Visits: {len(user.get('completed_visits', []))}

🚀 Share your code to earn more!"""
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Stats error: {e}")
        bot.send_message(message.chat.id, "❌ Error loading stats.")

# --- Referral Handler ---
@bot.message_handler(func=lambda m: m.text == '👥 Refer & Earn')
def show_referral(message):
    """Show referral program"""
    try:
        user = get_user(message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ Use /start first!")
            return
        
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user['referral_code']}"
        
        msg = f"""👥 *Refer & Earn*

💰 Earn ₹2 per referral!

📌 *How:*
1️⃣ Share your link
2️⃣ Friend joins
3️⃣ You get ₹2 instantly!

🔑 *Your Code:* `{user['referral_code']}`
🔗 *Your Link:*
{ref_link}

📊 *Your Stats:*
✅ Referrals: {user.get('total_referrals', 0)}
💵 Earned: {fmt_balance(user.get('referral_earnings', 0))}

📢 Share on social media for more!"""
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown', disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Referral error: {e}")
        bot.send_message(message.chat.id, "❌ Error loading referral info.")

# --- Tasks Handler ---
@bot.message_handler(func=lambda m: m.text == '📝 Tasks')
def show_tasks(message):
    """Show available tasks"""
    try:
        tasks = list(tasks_col.find({'active': True}).limit(10))
        
        if not tasks:
            bot.send_message(message.chat.id, "📝 No tasks available. Check back later!")
            return
        
        kb = types.InlineKeyboardMarkup(row_width=1)
        for task in tasks:
            btn = types.InlineKeyboardButton(
                f"{task['title']} - {fmt_balance(task['amount'])}",
                callback_data=f"task_{task['_id']}"
            )
            kb.add(btn)
        
        bot.send_message(
            message.chat.id,
            "📝 *Available Tasks*\n\nClick a task to view details & submit.",
            parse_mode='Markdown',
            reply_markup=kb
        )
    except Exception as e:
        logger.error(f"Tasks error: {e}")
        bot.send_message(message.chat.id, "❌ Error loading tasks.")

# --- Visit Tasks Handler ---
@bot.message_handler(func=lambda m: m.text == '🔗 Visit Tasks')
def show_visit_tasks(message):
    """Show visit tasks"""
    try:
        tasks = list(visit_tasks_col.find({'active': True}).limit(10))
        
        if not tasks:
            bot.send_message(message.chat.id, "🔗 No visit tasks available. Check back!")
            return
        
        kb = types.InlineKeyboardMarkup(row_width=1)
        for task in tasks:
            btn = types.InlineKeyboardButton(
                f"{task['title']} - {fmt_balance(task['amount'])} ({task['time_required']}s)",
                callback_data=f"visit_{task['_id']}"
            )
            kb.add(btn)
        
        bot.send_message(
            message.chat.id,
            "🔗 *Visit & Earn*\n\nVisit websites, stay for required time, earn money!",
            parse_mode='Markdown',
            reply_markup=kb
        )
    except Exception as e:
        logger.error(f"Visit tasks error: {e}")
        bot.send_message(message.chat.id, "❌ Error loading visit tasks.")

# --- Task Callback Handler ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('task_'))
def handle_task_callback(call):
    """Handle task selection"""
    try:
        task_id = call.data.split('_')[1]
        
        try:
            task_obj_id = ObjectId(task_id)
        except:
            bot.answer_callback_query(call.id, "❌ Invalid task!")
            return
        
        task = tasks_col.find_one({'_id': task_obj_id})
        if not task:
            bot.answer_callback_query(call.id, "❌ Task not found!")
            return
        
        user = get_user(call.from_user.id)
        if task_id in user.get('completed_tasks', []):
            bot.answer_callback_query(call.id, "✅ Already completed!")
            return
        
        msg = f"""📝 *{task['title']}*

💰 Reward: {fmt_balance(task['amount'])}
📋 {task.get('description', 'Complete the task')}

🔗 *Link:* {task.get('link', 'No link')}

✅ *Steps:*
1. Click the link
2. Complete the action
3. Take screenshot
4. Submit below

⚠️ Fake submissions = Ban!"""
        
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📸 Submit Screenshot", callback_data=f"submit_{task_id}"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="back_tasks"))
        
        try:
            bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, 
                                parse_mode='Markdown', reply_markup=kb, disable_web_page_preview=True)
        except:
            bot.send_message(call.message.chat.id, msg, parse_mode='Markdown', 
                           reply_markup=kb, disable_web_page_preview=True)
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"Task callback error: {e}")
        bot.answer_callback_query(call.id, "❌ Error. Try again.")

# --- Submit Screenshot Handler ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('submit_'))
def request_screenshot(call):
    """Request screenshot from user"""
    try:
        task_id = call.data.split('_')[1]
        
        try:
            ObjectId(task_id)
        except:
            bot.answer_callback_query(call.id, "❌ Invalid task!")
            return
        
        task = tasks_col.find_one({'_id': ObjectId(task_id)})
        if not task:
            bot.answer_callback_query(call.id, "❌ Task not found!")
            return
        
        bot.answer_callback_query(call.id)
        
        msg = bot.send_message(
            call.message.chat.id,
            f"📸 *Screenshot for:* {task['title']}\n\n"
            "Send the screenshot now.\n"
            "Type 'cancel' to cancel.",
            parse_mode='Markdown'
        )
        
        bot.register_next_step_handler(msg, save_screenshot, task_id)
        
    except Exception as e:
        logger.error(f"Screenshot request error: {e}")
        bot.answer_callback_query(call.id, "❌ Error.")

def save_screenshot(message, task_id):
    """Save screenshot submission"""
    try:
        if message.text and message.text.lower() == 'cancel':
            bot.send_message(message.chat.id, "❌ Cancelled.", reply_markup=main_menu())
            return
        
        if not message.photo:
            bot.send_message(message.chat.id, "❌ Send a photo screenshot!")
            return
        
        task = tasks_col.find_one({'_id': ObjectId(task_id)})
        if not task:
            bot.send_message(message.chat.id, "❌ Task not found!")
            return
        
        photo_id = message.photo[-1].file_id
        
        submission = {
            'user_id': str(message.from_user.id),
            'username': message.from_user.username or "Unknown",
            'first_name': message.from_user.first_name or "User",
            'task_id': task_id,
            'task_title': task['title'],
            'task_amount': task['amount'],
            'screenshot': photo_id,
            'status': 'pending',
            'submitted_at': datetime.now()
        }
        
        submissions_col.insert_one(submission)
        
        bot.send_message(
            message.chat.id,
            f"✅ *Submitted!*\n\n"
            f"Task: {task['title']}\n"
            f"Reward: {fmt_balance(task['amount'])}\n\n"
            f"⏳ Pending admin approval.\n"
            f"You'll be notified when approved.",
            parse_mode='Markdown',
            reply_markup=main_menu()
        )
        
        # Notify admin
        if ADMIN_USER_ID:
            try:
                bot.send_message(
                    ADMIN_USER_ID,
                    f"📋 New submission from @{message.from_user.username}\n"
                    f"Task: {task['title']}"
                )
            except:
                pass
                
    except Exception as e:
        logger.error(f"Save screenshot error: {e}")
        bot.send_message(message.chat.id, "❌ Error saving submission.")

# --- Visit Task Callback ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('visit_'))
def handle_visit_callback(call):
    """Handle visit task selection"""
    try:
        task_id = call.data.split('_')[1]
        
        try:
            task_obj_id = ObjectId(task_id)
        except:
            bot.answer_callback_query(call.id, "❌ Invalid task!")
            return
        
        task = visit_tasks_col.find_one({'_id': task_obj_id})
        if not task:
            bot.answer_callback_query(call.id, "❌ Task not found!")
            return
        
        user_id = str(call.from_user.id)
        
        # Check 24h cooldown
        recent = completed_visits_col.find_one({
            'user_id': user_id,
            'task_id': task_id,
            'completed_at': {'$gte': datetime.now() - timedelta(hours=24)}
        })
        
        if recent:
            bot.answer_callback_query(call.id, "⏰ Wait 24h before repeating!")
            return
        
        # Store start time
        users_col.update_one(
            {'user_id': user_id},
            {'$set': {f'visit_start_{task_id}': datetime.now()}}
        )
        
        msg = f"""🔗 *{task['title']}*

💰 Reward: {fmt_balance(task['amount'])}
⏱️ Time: {task['time_required']} seconds

🔗 *Link:* {task['link']}

⚠️ Stay on site for {task['time_required']}s then click complete!"""
        
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Complete Visit", callback_data=f"done_{task_id}"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="back_visits"))
        
        try:
            bot.edit_message_text(msg, call.message.chat.id, call.message.message_id,
                                parse_mode='Markdown', reply_markup=kb, disable_web_page_preview=True)
        except:
            bot.send_message(call.message.chat.id, msg, parse_mode='Markdown',
                           reply_markup=kb, disable_web_page_preview=True)
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"Visit callback error: {e}")
        bot.answer_callback_query(call.id, "❌ Error.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('done_'))
def complete_visit_handler(call):
    """Complete visit task"""
    try:
        task_id = call.data.split('_')[1]
        user_id = str(call.from_user.id)
        
        task = visit_tasks_col.find_one({'_id': ObjectId(task_id)})
        if not task:
            bot.answer_callback_query(call.id, "❌ Task not found!")
            return
        
        user = get_user(user_id)
        start_time = user.get(f'visit_start_{task_id}')
        
        if not start_time:
            bot.answer_callback_query(call.id, "❌ Start the task first!")
            return
        
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        if elapsed >= task['time_required']:
            amount = task['amount']
            update_balance(user_id, amount, 'add')
            add_transaction(user_id, amount, 'visit', f'Visit: {task["title"]}')
            
            users_col.update_one(
                {'user_id': user_id},
                {
                    '$inc': {'total_earned': amount},
                    '$push': {'completed_visits': task_id},
                    '$unset': {f'visit_start_{task_id}': ''}
                }
            )
            
            completed_visits_col.insert_one({
                'user_id': user_id,
                'task_id': task_id,
                'task_title': task['title'],
                'completed_at': datetime.now(),
                'amount': amount
            })
            
            bot.answer_callback_query(call.id, f"✅ Earned {fmt_balance(amount)}!")
            
            try:
                bot.edit_message_text(
                    f"✅ *Completed!*\n\nEarned {fmt_balance(amount)}!\n"
                    f"Come back after 24h.",
                    call.message.chat.id, call.message.message_id,
                    parse_mode='Markdown'
                )
            except:
                pass
        else:
            remaining = int(task['time_required'] - elapsed)
            bot.answer_callback_query(call.id, f"⏰ Wait {remaining}s more!")
            
    except Exception as e:
        logger.error(f"Complete visit error: {e}")
        bot.answer_callback_query(call.id, "❌ Error.")

# --- Back Buttons ---
@bot.callback_query_handler(func=lambda call: call.data in ['back_tasks', 'back_visits'])
def handle_back(call):
    """Handle back button"""
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        
        if call.data == 'back_tasks':
            show_tasks(call.message)
        else:
            show_visit_tasks(call.message)
    except:
        pass

# --- Withdrawal System ---
@bot.message_handler(func=lambda m: m.text == '💸 Withdraw')
def withdraw_menu(message):
    """Show withdrawal menu"""
    try:
        user = get_user(message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ Use /start first!")
            return
        
        bal = user.get('balance', 0)
        
        # Check pending
        pending = withdrawals_col.find_one({
            'user_id': str(message.from_user.id),
            'status': 'pending'
        })
        
        if pending:
            bot.send_message(message.chat.id, 
                           f"⚠️ *Pending Withdrawal*\n\n"
                           f"Amount: {fmt_balance(pending['amount'])}\n"
                           f"Please wait for processing.",
                           parse_mode='Markdown')
            return
        
        if bal < 50:
            bot.send_message(message.chat.id,
                           f"❌ *Insufficient Balance*\n\n"
                           f"Balance: {fmt_balance(bal)}\n"
                           f"Minimum: ₹50\n\n"
                           f"Complete tasks to earn!",
                           parse_mode='Markdown')
            return
        
        msg = f"""💸 *Withdraw*

💰 Balance: {fmt_balance(bal)}

📋 *Methods:*
• UPI: Min ₹50
• Bank: Min ₹100
• Bitcoin: Min ₹200

⚠️ Processing: 24-48h"""

        bot.send_message(message.chat.id, msg, parse_mode='Markdown', 
                       reply_markup=withdraw_keyboard())
        
    except Exception as e:
        logger.error(f"Withdraw menu error: {e}")
        bot.send_message(message.chat.id, "❌ Error.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('wd_'))
def withdraw_method(call):
    """Handle withdrawal method"""
    try:
        method = call.data.split('_')[1]
        user = get_user(call.from_user.id)
        bal = user.get('balance', 0)
        
        mins = {'upi': 50, 'bank': 100, 'crypto': 200}
        names = {'upi': 'UPI', 'bank': 'Bank Transfer', 'crypto': 'Bitcoin'}
        
        min_amt = mins.get(method, 50)
        method_name = names.get(method, method.upper())
        
        if bal < min_amt:
            bot.answer_callback_query(call.id, f"Min ₹{min_amt} for {method_name}!")
            return
        
        bot.answer_callback_query(call.id)
        
        msg = bot.send_message(
            call.message.chat.id,
            f"💸 *{method_name} Withdrawal*\n\n"
            f"Balance: {fmt_balance(bal)}\n"
            f"Minimum: ₹{min_amt}\n\n"
            f"Enter amount (or 'cancel'):",
            parse_mode='Markdown'
        )
        
        bot.register_next_step_handler(msg, process_amount, method, min_amt)
        
    except Exception as e:
        logger.error(f"Withdraw method error: {e}")
        bot.answer_callback_query(call.id, "❌ Error.")

def process_amount(message, method, min_amt):
    """Process withdrawal amount"""
    try:
        if message.text and message.text.lower() == 'cancel':
            bot.send_message(message.chat.id, "❌ Cancelled.", reply_markup=main_menu())
            return
        
        try:
            amt = float(message.text)
        except:
            bot.send_message(message.chat.id, "❌ Enter a valid number!")
            return
        
        if amt < min_amt:
            bot.send_message(message.chat.id, f"❌ Minimum is ₹{min_amt}!")
            return
        
        user = get_user(message.from_user.id)
        if amt > user.get('balance', 0):
            bot.send_message(message.chat.id, "❌ Insufficient balance!")
            return
        
        # Ask for details
        prompts = {
            'upi': "📱 Enter your UPI ID:\nExample: name@okhdfcbank",
            'bank': "🏦 Enter bank details:\n\nName\nAccount No\nIFSC\nBank Name",
            'crypto': "₿ Enter Bitcoin wallet address:"
        }
        
        msg = bot.send_message(message.chat.id, prompts.get(method, "Enter details:"))
        bot.register_next_step_handler(msg, save_withdrawal, method, amt)
        
    except Exception as e:
        logger.error(f"Process amount error: {e}")
        bot.send_message(message.chat.id, "❌ Error.")

def save_withdrawal(message, method, amt):
    """Save withdrawal request"""
    try:
        if message.text and message.text.lower() == 'cancel':
            bot.send_message(message.chat.id, "❌ Cancelled.", reply_markup=main_menu())
            return
        
        details = message.text
        
        # Deduct balance
        update_balance(message.from_user.id, amt, 'subtract')
        add_transaction(message.from_user.id, -amt, 'withdrawal', f'Withdrawal via {method.upper()}')
        
        users_col.update_one(
            {'user_id': str(message.from_user.id)},
            {'$inc': {'total_withdrawn': amt}}
        )
        
        # Save request
        request = {
            'user_id': str(message.from_user.id),
            'username': message.from_user.username or "Unknown",
            'first_name': message.from_user.first_name or "User",
            'amount': amt,
            'method': method,
            'account_details': details,
            'status': 'pending',
            'requested_at': datetime.now()
        }
        
        withdrawals_col.insert_one(request)
        
        bot.send_message(
            message.chat.id,
            f"✅ *Withdrawal Submitted!*\n\n"
            f"Amount: {fmt_balance(amt)}\n"
            f"Method: {method.upper()}\n\n"
            f"⏳ Processing: 24-48h\n"
            f"Use /check_withdrawal to track.",
            parse_mode='Markdown',
            reply_markup=main_menu()
        )
        
    except Exception as e:
        logger.error(f"Save withdrawal error: {e}")
        bot.send_message(message.chat.id, "❌ Error saving request.")

@bot.message_handler(commands=['check_withdrawal'])
def check_withdrawal(message):
    """Check withdrawal status"""
    try:
        requests = list(
            withdrawals_col.find({'user_id': str(message.from_user.id)})
            .sort('requested_at', -1)
            .limit(5)
        )
        
        if not requests:
            bot.send_message(message.chat.id, "No withdrawal requests found.")
            return
        
        msg = "💸 *Your Withdrawals*\n\n"
        emojis = {'pending': '⏳', 'approved': '✅', 'rejected': '❌'}
        
        for req in requests:
            emoji = emojis.get(req['status'], '❓')
            req_date = req['requested_at']
            if isinstance(req_date, str):
                req_date = datetime.fromisoformat(req_date)
            
            msg += f"{emoji} {req['method'].upper()} - {fmt_balance(req['amount'])}\n"
            msg += f"   Status: {req['status'].upper()}\n"
            msg += f"   Date: {req_date.strftime('%d/%m/%Y')}\n\n"
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Check withdrawal error: {e}")
        bot.send_message(message.chat.id, "❌ Error.")

# --- Admin Panel ---
@bot.message_handler(func=lambda m: m.text == ADMIN_PASSWORD)
def admin_login(message):
    """Activate admin panel"""
    global ADMIN_USER_ID
    ADMIN_USER_ID = message.chat.id
    
    bot.send_message(
        message.chat.id,
        "✅ *Admin Panel Activated!*\n\nManage bot from buttons below.",
        parse_mode='Markdown',
        reply_markup=admin_menu()
    )

@bot.message_handler(func=lambda m: m.text == '🔙 Back to Menu')
def admin_logout(message):
    """Deactivate admin panel"""
    global ADMIN_USER_ID
    
    if message.chat.id == ADMIN_USER_ID:
        ADMIN_USER_ID = None
        bot.send_message(message.chat.id, "👋 Admin session ended.", reply_markup=main_menu())
    else:
        bot.send_message(message.chat.id, "Main menu.", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == '📊 Total Users')
def admin_users(message):
    """Show user statistics"""
    if message.chat.id != ADMIN_USER_ID:
        return
    
    try:
        total = users_col.count_documents({})
        active = users_col.count_documents({
            'last_active': {'$gte': datetime.now() - timedelta(hours=24)}
        })
        
        bot.send_message(
            message.chat.id,
            f"📊 *User Statistics*\n\n👥 Total: {total}\n🟢 Active 24h: {active}\n🔴 Inactive: {total - active}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Admin users error: {e}")

@bot.message_handler(func=lambda m: m.text == '💰 Total Balance')
def admin_balance(message):
    """Show financial statistics"""
    if message.chat.id != ADMIN_USER_ID:
        return
    
    try:
        pipeline = [{'$group': {
            '_id': None,
            'balance': {'$sum': '$balance'},
            'earned': {'$sum': '$total_earned'},
            'withdrawn': {'$sum': '$total_withdrawn'}
        }}]
        
        result = list(users_col.aggregate(pipeline))
        if result:
            stats = result[0]
            msg = f"""💰 *Financial Overview*

💵 User Balance: {fmt_balance(stats.get('balance', 0))}
📈 Total Earned: {fmt_balance(stats.get('earned', 0))}
💸 Total Withdrawn: {fmt_balance(stats.get('withdrawn', 0))}
📊 System Profit: {fmt_balance(stats.get('earned', 0) - stats.get('withdrawn', 0))}"""
        else:
            msg = "No data available."
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Admin balance error: {e}")

@bot.message_handler(func=lambda m: m.text == '💸 Withdrawal Requests')
def admin_withdrawals(message):
    """View pending withdrawals"""
    if message.chat.id != ADMIN_USER_ID:
        return
    
    try:
        pending = list(withdrawals_col.find({'status': 'pending'}).limit(10))
        
        if not pending:
            bot.send_message(message.chat.id, "✅ No pending requests!")
            return
        
        for req in pending:
            kb = types.InlineKeyboardMarkup(row_width=2)
            kb.add(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"aprv_{req['_id']}"),
                types.InlineKeyboardButton("❌ Reject", callback_data=f"rjct_{req['_id']}")
            )
            
            req_date = req['requested_at']
            if isinstance(req_date, str):
                req_date = datetime.fromisoformat(req_date)
            
            msg = f"""💸 *Withdrawal Request*

👤 @{req.get('username', 'Unknown')}
🆔 `{req['user_id']}`
💰 {fmt_balance(req['amount'])}
📱 {req['method'].upper()}
📝 `{req['account_details']}`
📅 {req_date.strftime('%d/%m/%Y %H:%M')}"""
            
            bot.send_message(message.chat.id, msg, parse_mode='Markdown', reply_markup=kb)
            
    except Exception as e:
        logger.error(f"Admin withdrawals error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('aprv_'))
def approve_withdrawal(call):
    """Approve withdrawal"""
    if call.message.chat.id != ADMIN_USER_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized!")
        return
    
    try:
        req_id = call.data.split('_')[1]
        
        withdrawals_col.update_one(
            {'_id': ObjectId(req_id)},
            {'$set': {'status': 'approved', 'processed_at': datetime.now()}}
        )
        
        req = withdrawals_col.find_one({'_id': ObjectId(req_id)})
        
        if req:
            try:
                bot.send_message(
                    int(req['user_id']),
                    f"✅ *Withdrawal Approved!*\n\n"
                    f"{fmt_balance(req['amount'])} sent via {req['method'].upper()}.",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        bot.answer_callback_query(call.id, "✅ Approved!")
        bot.edit_message_text("✅ *Approved*", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Approve error: {e}")
        bot.answer_callback_query(call.id, "❌ Error.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('rjct_'))
def reject_withdrawal(call):
    """Reject withdrawal"""
    if call.message.chat.id != ADMIN_USER_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized!")
        return
    
    try:
        req_id = call.data.split('_')[1]
        req = withdrawals_col.find_one({'_id': ObjectId(req_id)})
        
        if req:
            # Refund
            update_balance(req['user_id'], req['amount'], 'add')
            
            withdrawals_col.update_one(
                {'_id': ObjectId(req_id)},
                {'$set': {'status': 'rejected', 'processed_at': datetime.now()}}
            )
            
            try:
                bot.send_message(
                    int(req['user_id']),
                    f"❌ *Withdrawal Rejected*\n\n"
                    f"{fmt_balance(req['amount'])} refunded.\n"
                    f"Check details and retry.",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        bot.answer_callback_query(call.id, "❌ Rejected!")
        bot.edit_message_text("❌ *Rejected*", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Reject error: {e}")
        bot.answer_callback_query(call.id, "❌ Error.")

@bot.message_handler(func=lambda m: m.text == '📋 Task Submissions')
def admin_submissions(message):
    """View pending submissions"""
    if message.chat.id != ADMIN_USER_ID:
        return
    
    try:
        subs = list(submissions_col.find({'status': 'pending'}).limit(10))
        
        if not subs:
            bot.send_message(message.chat.id, "✅ No pending submissions!")
            return
        
        for sub in subs:
            kb = types.InlineKeyboardMarkup(row_width=2)
            kb.add(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"asub_{sub['_id']}"),
                types.InlineKeyboardButton("❌ Reject", callback_data=f"rsub_{sub['_id']}")
            )
            
            sub_date = sub['submitted_at']
            if isinstance(sub_date, str):
                sub_date = datetime.fromisoformat(sub_date)
            
            caption = f"""📋 *Submission*

👤 @{sub.get('username', 'Unknown')}
📝 {sub.get('task_title', 'Unknown')}
💰 {fmt_balance(sub.get('task_amount', 0))}
📅 {sub_date.strftime('%d/%m/%Y %H:%M')}"""
            
            try:
                bot.send_photo(message.chat.id, sub['screenshot'], caption=caption,
                             parse_mode='Markdown', reply_markup=kb)
            except:
                bot.send_message(message.chat.id, caption + "\n\n⚠️ Screenshot unavailable",
                               parse_mode='Markdown', reply_markup=kb)
                
    except Exception as e:
        logger.error(f"Submissions error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('asub_'))
def approve_submission(call):
    """Approve task submission"""
    if call.message.chat.id != ADMIN_USER_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized!")
        return
    
    try:
        sub_id = call.data.split('_')[1]
        sub = submissions_col.find_one({'_id': ObjectId(sub_id)})
        
        if sub:
            task = tasks_col.find_one({'_id': ObjectId(sub['task_id'])})
            
            if task:
                amt = task['amount']
                update_balance(sub['user_id'], amt, 'add')
                add_transaction(sub['user_id'], amt, 'task', f"Task: {task['title']}")
                
                users_col.update_one(
                    {'user_id': sub['user_id']},
                    {
                        '$inc': {'total_earned': amt},
                        '$push': {'completed_tasks': sub['task_id']}
                    }
                )
                
                try:
                    bot.send_message(
                        int(sub['user_id']),
                        f"✅ *Task Approved!*\n\n{task['title']}\nEarned: {fmt_balance(amt)}",
                        parse_mode='Markdown'
                    )
                except:
                    pass
            
            submissions_col.update_one(
                {'_id': ObjectId(sub_id)},
                {'$set': {'status': 'approved'}}
            )
        
        bot.answer_callback_query(call.id, "✅ Approved!")
        try:
            bot.edit_message_caption("✅ Approved", call.message.chat.id, call.message.message_id)
        except:
            pass
        
    except Exception as e:
        logger.error(f"Approve sub error: {e}")
        bot.answer_callback_query(call.id, "❌ Error.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('rsub_'))
def reject_submission(call):
    """Reject task submission"""
    if call.message.chat.id != ADMIN_USER_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized!")
        return
    
    try:
        sub_id = call.data.split('_')[1]
        sub = submissions_col.find_one({'_id': ObjectId(sub_id)})
        
        if sub:
            submissions_col.update_one(
                {'_id': ObjectId(sub_id)},
                {'$set': {'status': 'rejected'}}
            )
            
            try:
                bot.send_message(
                    int(sub['user_id']),
                    f"❌ *Task Rejected*\n\n{sub.get('task_title', 'Unknown')}\n"
                    "Complete correctly and resubmit.",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        bot.answer_callback_query(call.id, "❌ Rejected!")
        try:
            bot.edit_message_caption("❌ Rejected", call.message.chat.id, call.message.message_id)
        except:
            pass
        
    except Exception as e:
        logger.error(f"Reject sub error: {e}")
        bot.answer_callback_query(call.id, "❌ Error.")

# --- Advertisement & About ---
@bot.message_handler(func=lambda m: m.text in ['📢 Advertisement', 'ℹ️ About'])
def info_handlers(message):
    """Handle info buttons"""
    if message.text == '📢 Advertisement':
        total = users_col.count_documents({})
        msg = f"""📢 *Advertise With Us*

👥 Our Users: {total}+
📈 Active: Daily active users

💰 *Packages:*
• Broadcast: ₹500
• Pinned 24h: ₹1000
• Featured Task: ₹2000

📞 Contact: @Admin"""
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')
    
    elif message.text == 'ℹ️ About':
        msg = """ℹ️ *About Earning Bot*

💰 Version 2.0

✨ *Features:*
• Earn from tasks
• Earn from visits
• Refer & earn ₹2 each
• Multiple withdrawals

⚠️ *Rules:*
• One account only
• Honest work only
• No fake submissions

📞 Support: @Admin"""
        
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')

# --- Error Handler ---
@bot.message_handler(func=lambda m: True)
def catch_all(message):
    """Catch unknown messages"""
    if not message.text or not message.text.startswith('/'):
        bot.send_message(
            message.chat.id,
            "❓ Use the buttons below or /start",
            reply_markup=main_menu()
        )

# --- Main Execution ---
if __name__ == '__main__':
    print("="*50)
    print("🤖 Earning Bot v2.0 Starting...")
    print(f"📡 Environment: Railway/Railpack")
    print("="*50)
    
    # Step 1: Connect to MongoDB
    if not connect_mongodb():
        print("❌ Failed to connect to MongoDB. Exiting...")
        sys.exit(1)
    
    # Step 2: Initialize collections
    init_collections()
    
    # Step 3: Initialize Telegram Bot
    try:
        bot = telebot.TeleBot(API_TOKEN, threaded=False)
        print("✅ Telegram Bot initialized")
    except Exception as e:
        print(f"❌ Bot init error: {e}")
        sys.exit(1)
    
    # Step 4: Start Health Check Server (Railway Requirement)
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    print(f"🏥 Health server started on port {PORT}")
    
    # Step 5: Remove webhook and start polling
    try:
        bot.remove_webhook()
        print("✅ Webhook removed")
    except:
        pass
    
    print("✅ Bot is now running!")
    print("="*50)
    
    # Step 6: Start bot with retry logic
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        try:
            print(f"🔄 Starting bot polling (attempt {retry_count + 1})")
            bot.infinity_polling(timeout=30, long_polling_timeout=15)
        except Exception as e:
            retry_count += 1
            print(f"❌ Bot error (attempt {retry_count}): {e}")
            
            if retry_count < max_retries:
                wait = min(retry_count * 10, 60)
                print(f"⏳ Retrying in {wait} seconds...")
                time.sleep(wait)
            else:
                print("❌ Max retries reached!")
                sys.exit(1)