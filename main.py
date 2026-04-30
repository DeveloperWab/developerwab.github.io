import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuration ---
TOKEN = "8384600981:AAHhAm-cD1qjiav6UikKsII4FGNsAwzon2o"
ADMIN_TRIGGER = "Vansh@000"

# --- Keyboard Layouts ---
USER_KEYBOARD = [
    ['📝 Tasks', '🔗 Visit & Earn'],
    ['💰 My Balance', '💸 Withdraw'],
    ['👥 Referral Program', '📊 My Stats'],
    ['❓ Help', 'ℹ️ About']
]

ADMIN_KEYBOARD = [
    ['📊 Dashboard', '👥 User Stats'],
    ['💰 Financial Stats', '💸 Withdrawal Requests'],
    ['📋 Pending Submissions', '📢 Broadcast'],
    ['➕ Add Task', '➕ Add Visit Task'],
    ['🔙 Exit Admin']
]

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = ReplyKeyboardMarkup(USER_KEYBOARD, resize_keyboard=True)
    await update.message.reply_text(
        "👋 Welcome to the Bot!\nNiche diye gaye buttons ka use karein.",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # Hidden Admin Panel Activation
    if text == ADMIN_TRIGGER:
        reply_markup = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
        await update.message.reply_text(
            "⚡ *Admin Panel Activated*",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return

    # Exit Admin Panel
    if text == '🔙 Exit Admin':
        reply_markup = ReplyKeyboardMarkup(USER_KEYBOARD, resize_keyboard=True)
        await update.message.reply_text("Back to User Menu.", reply_markup=reply_markup)
        return

    # User Button Responses (Simple Placeholders)
    responses = {
        '📝 Tasks': "📋 Yaha aapke daily tasks show honge.",
        '🔗 Visit & Earn': "🔗 Website visit karke paise kamayein.",
        '💰 My Balance': "💰 Aapka balance: 0.00 INR",
        '💸 Withdraw': "💸 Minimum withdrawal: 100 INR",
        '👥 Referral Program': "👥 Apne doston ko invite karein aur earn karein.",
        '📊 My Stats': "📊 Aapne abhi tak 0 tasks complete kiye hain.",
        '❓ Help': "❓ Kisi bhi sahayata ke liye @admin se sampark karein.",
        'ℹ️ About': "ℹ️ Ye ek earning bot hai jo Railway par hosted hai."
    }

    if text in responses:
        await update.message.reply_text(responses[text])
    elif any(text in row for row in ADMIN_KEYBOARD):
        await update.message.reply_text(f"⚙️ Admin Function: {text} (Feature coming soon)")

# --- Main App ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Bot is running...")
    app.run_polling()
