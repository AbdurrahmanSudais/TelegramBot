import logging
import json
from datetime import datetime, timedelta
from telegram import Update, ChatMember, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError
import sqlite3
import asyncio

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class GroupManagerBot:
    def __init__(self, token):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.db_name = "group_stats.db"
        self.init_database()
        self.setup_handlers()
    
    def init_database(self):
        """Initialize SQLite database for storing group statistics"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Table for storing group statistics
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_stats (
                group_id INTEGER,
                date TEXT,
                member_count INTEGER,
                messages_count INTEGER DEFAULT 0,
                PRIMARY KEY (group_id, date)
            )
        ''')
        
        # Table for storing user activity
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_activity (
                user_id INTEGER,
                group_id INTEGER,
                username TEXT,
                first_name TEXT,
                last_message DATE,
                message_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, group_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def setup_handlers(self):
        """Setup command and message handlers"""
        # Command handlers
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("lock", self.lock_group))
        self.app.add_handler(CommandHandler("unlock", self.unlock_group))
        self.app.add_handler(CommandHandler("mute", self.mute_user))
        self.app.add_handler(CommandHandler("unmute", self.unmute_user))
        self.app.add_handler(CommandHandler("ban", self.ban_user))
        self.app.add_handler(CommandHandler("kick", self.kick_user))
        self.app.add_handler(CommandHandler("help", self.help_command))
        
        # Message handler for tracking activity
        self.app.add_handler(MessageHandler(filters.ALL, self.track_activity))
    
    async def is_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if user is admin in the group"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            return member.status in ['administrator', 'creator']
        except TelegramError:
            return False
    
    async def is_bot_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if bot has admin privileges"""
        chat_id = update.effective_chat.id
        bot_id = context.bot.id
        
        try:
            member = await context.bot.get_chat_member(chat_id, bot_id)
            return member.status == 'administrator'
        except TelegramError:
            return False
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        await update.message.reply_text(
            "🤖 Group Manager Bot is now active!\n\n"
            "I can help you manage this group and provide statistics.\n"
            "Use /help to see available commands."
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command showing all available commands"""
        help_text = """
🔧 **Group Manager Bot Commands**

📊 **Statistics:**
/stats - Show group statistics

🔒 **Group Management (Admin Only):**
/lock - Lock the group (only admins can send messages)
/unlock - Unlock the group (everyone can send messages)

👥 **User Management (Admin Only):**
/mute @username - Mute a user
/unmute @username - Unmute a user
/ban @username - Ban a user from the group
/kick @username - Kick a user from the group

ℹ️ **Other:**
/help - Show this help message

**Note:** Admin commands require both you and the bot to have administrator privileges.
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show group statistics"""
        chat = update.effective_chat
        chat_id = chat.id
        
        if chat.type == 'private':
            await update.message.reply_text("This command only works in groups!")
            return
        
        try:
            # Get member count
            member_count = await context.bot.get_chat_member_count(chat_id)
            
            # Get admin count
            admins = await context.bot.get_chat_administrators(chat_id)
            admin_count = len(admins)
            
            # Get database stats
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            # Get today's message count
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute('''
                SELECT messages_count FROM group_stats 
                WHERE group_id = ? AND date = ?
            ''', (chat_id, today))
            
            result = cursor.fetchone()
            today_messages = result[0] if result else 0
            
            # Get active users (users who sent messages today)
            cursor.execute('''
                SELECT COUNT(*) FROM user_activity 
                WHERE group_id = ? AND last_message = ?
            ''', (chat_id, today))
            
            active_users = cursor.fetchone()[0]
            
            conn.close()
            
            stats_text = f"""
📊 **Group Statistics for {chat.title}**

👥 **Members:** {member_count}
👑 **Admins:** {admin_count}
📱 **Active Users Today:** {active_users}
💬 **Messages Today:** {today_messages}

📅 **Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            await update.message.reply_text(stats_text, parse_mode='Markdown')
            
        except TelegramError as e:
            await update.message.reply_text(f"❌ Error getting statistics: {str(e)}")
    
    async def lock_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lock the group - only admins can send messages"""
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can use this command!")
            return
        
        if not await self.is_bot_admin(update, context):
            await update.message.reply_text("❌ I need admin privileges to lock the group!")
            return
        
        try:
            # Set permissions to restrict normal users
            permissions = ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False
            )
            
            await context.bot.set_chat_permissions(update.effective_chat.id, permissions)
            await update.message.reply_text("🔒 Group has been locked! Only admins can send messages.")
            
        except TelegramError as e:
            await update.message.reply_text(f"❌ Failed to lock group: {str(e)}")
    
    async def unlock_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Unlock the group - everyone can send messages"""
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can use this command!")
            return
        
        if not await self.is_bot_admin(update, context):
            await update.message.reply_text("❌ I need admin privileges to unlock the group!")
            return
        
        try:
            # Set permissions to allow normal users
            permissions = ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False
            )
            
            await context.bot.set_chat_permissions(update.effective_chat.id, permissions)
            await update.message.reply_text("🔓 Group has been unlocked! Everyone can send messages.")
            
        except TelegramError as e:
            await update.message.reply_text(f"❌ Failed to unlock group: {str(e)}")
    
    async def mute_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mute a specific user"""
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can use this command!")
            return
        
        if not await self.is_bot_admin(update, context):
            await update.message.reply_text("❌ I need admin privileges to mute users!")
            return
        
        # Get user from reply or mention
        user_to_mute = None
        if update.message.reply_to_message:
            user_to_mute = update.message.reply_to_message.from_user
        elif context.args and context.args[0].startswith('@'):
            username = context.args[0][1:]  # Remove @ symbol
            # Note: You'd need to implement user lookup by username
            await update.message.reply_text("Please reply to a message or provide user ID")
            return
        else:
            await update.message.reply_text("Please reply to a message from the user you want to mute or use @username")
            return
        
        if user_to_mute:
            try:
                # Mute user for 1 hour (you can adjust this)
                until_date = datetime.now() + timedelta(hours=1)
                await context.bot.restrict_chat_member(
                    update.effective_chat.id,
                    user_to_mute.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until_date
                )
                
                await update.message.reply_text(f"🔇 User {user_to_mute.first_name} has been muted for 1 hour.")
                
            except TelegramError as e:
                await update.message.reply_text(f"❌ Failed to mute user: {str(e)}")
    
    async def unmute_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Unmute a specific user"""
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can use this command!")
            return
        
        if not await self.is_bot_admin(update, context):
            await update.message.reply_text("❌ I need admin privileges to unmute users!")
            return
        
        user_to_unmute = None
        if update.message.reply_to_message:
            user_to_unmute = update.message.reply_to_message.from_user
        else:
            await update.message.reply_text("Please reply to a message from the user you want to unmute")
            return
        
        if user_to_unmute:
            try:
                # Restore normal permissions
                permissions = ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
                
                await context.bot.restrict_chat_member(
                    update.effective_chat.id,
                    user_to_unmute.id,
                    permissions=permissions
                )
                
                await update.message.reply_text(f"🔊 User {user_to_unmute.first_name} has been unmuted.")
                
            except TelegramError as e:
                await update.message.reply_text(f"❌ Failed to unmute user: {str(e)}")
    
    async def ban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ban a user from the group"""
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can use this command!")
            return
        
        if not await self.is_bot_admin(update, context):
            await update.message.reply_text("❌ I need admin privileges to ban users!")
            return
        
        user_to_ban = None
        if update.message.reply_to_message:
            user_to_ban = update.message.reply_to_message.from_user
        else:
            await update.message.reply_text("Please reply to a message from the user you want to ban")
            return
        
        if user_to_ban:
            try:
                await context.bot.ban_chat_member(update.effective_chat.id, user_to_ban.id)
                await update.message.reply_text(f"🚫 User {user_to_ban.first_name} has been banned from the group.")
                
            except TelegramError as e:
                await update.message.reply_text(f"❌ Failed to ban user: {str(e)}")
    
    async def kick_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Kick a user from the group"""
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can use this command!")
            return
        
        if not await self.is_bot_admin(update, context):
            await update.message.reply_text("❌ I need admin privileges to kick users!")
            return
        
        user_to_kick = None
        if update.message.reply_to_message:
            user_to_kick = update.message.reply_to_message.from_user
        else:
            await update.message.reply_text("Please reply to a message from the user you want to kick")
            return
        
        if user_to_kick:
            try:
                await context.bot.ban_chat_member(update.effective_chat.id, user_to_kick.id)
                await context.bot.unban_chat_member(update.effective_chat.id, user_to_kick.id)
                await update.message.reply_text(f"👢 User {user_to_kick.first_name} has been kicked from the group.")
                
            except TelegramError as e:
                await update.message.reply_text(f"❌ Failed to kick user: {str(e)}")
    
    async def track_activity(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Track user activity and message counts"""
        if update.effective_chat.type == 'private':
            return  # Don't track private messages
        
        user = update.effective_user
        chat = update.effective_chat
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Update database with user activity and message count
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Update user activity
        cursor.execute('''
            INSERT OR REPLACE INTO user_activity 
            (user_id, group_id, username, first_name, last_message, message_count)
            VALUES (?, ?, ?, ?, ?, COALESCE((
                SELECT message_count FROM user_activity 
                WHERE user_id = ? AND group_id = ?
            ), 0) + 1)
        ''', (user.id, chat.id, user.username, user.first_name, today, user.id, chat.id))
        
        # Update group stats
        cursor.execute('''
            INSERT OR REPLACE INTO group_stats (group_id, date, member_count, messages_count)
            VALUES (?, ?, (
                SELECT COALESCE(member_count, 0) FROM group_stats 
                WHERE group_id = ? AND date = ?
            ), COALESCE((
                SELECT messages_count FROM group_stats 
                WHERE group_id = ? AND date = ?
            ), 0) + 1)
        ''', (chat.id, today, chat.id, today, chat.id, today))
        
        conn.commit()
        conn.close()
    
    def run(self):
        """Start the bot"""
        print("🤖 Starting Group Manager Bot...")
        print("Bot is running. Press Ctrl+C to stop.")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

# Main execution
if __name__ == '__main__':
    import os
    
    # Get bot token from environment variable (for Railway deployment)
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    if not BOT_TOKEN:
        print("❌ Please set BOT_TOKEN environment variable")
        exit(1)
    
    bot = GroupManagerBot(BOT_TOKEN)
    
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ An error occurred: {e}")
