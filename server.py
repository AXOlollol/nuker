from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import discord
from discord.ext import commands
import asyncio
import aiohttp
import threading
import json
import os
from typing import Dict, List

app = Flask(__name__)
CORS(app)

# Store active bot instances
active_bots: Dict[str, commands.Bot] = {}
bot_servers: Dict[str, List] = {}

class BotManager:
    def __init__(self):
        self.active_tasks = {}
    
    async def get_bot_servers(self, token: str):
        """Get all servers where the bot is a member"""
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        
        bot = commands.Bot(command_prefix='!', intents=intents)
        
        servers = []
        
        @bot.event
        async def on_ready():
            print(f"Bot {bot.user} is ready!")
            
            for guild in bot.guilds:
                # Check if bot has administrator permissions
                bot_member = guild.get_member(bot.user.id)
                if bot_member:
                    permissions = bot_member.guild_permissions
                    has_admin = permissions.administrator
                    
                    servers.append({
                        'id': str(guild.id),
                        'name': guild.name,
                        'icon': str(guild.icon.url) if guild.icon else None,
                        'hasAdmin': has_admin,
                        'member_count': guild.member_count
                    })
            
            # Store servers for this token
            bot_servers[token] = servers
            await bot.close()
        
        try:
            await bot.start(token)
        except Exception as e:
            print(f"Error: {e}")
            return []
        
        return servers
    
    async def run_confession_tool(self, token: str, guild_id: str, message: str, message_count: int, use_mentions: bool):
        """Run the confession tool on a specific server"""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        
        bot = commands.Bot(command_prefix='!', intents=intents)
        
        # Custom ClientSession to ignore rate limits
        class NoRateLimitSession(aiohttp.ClientSession):
            pass
        
        @bot.event
        async def on_connect():
            bot.http.session = NoRateLimitSession()
        
        @bot.event
        async def on_ready():
            print(f"Confession tool bot {bot.user} is ready!")
            
            guild = bot.get_guild(int(guild_id))
            if not guild:
                print(f"Guild {guild_id} not found")
                await bot.close()
                return
            
            # Replace .m with @everyone if mentions are enabled
            final_message = message
            if use_mentions:
                final_message = message.replace(".m", "@everyone")
            
            # Get all text channels
            channels = [channel for channel in guild.channels if isinstance(channel, discord.TextChannel)]
            total_channels = len(channels)
            
            print(f"Found {total_channels} channels. Sending {message_count} messages to each.")
            
            # Send messages to all channels
            sent_messages = 0
            failed_messages = 0
            
            all_tasks = []
            for i, channel in enumerate(channels, 1):
                print(f"[{i}/{total_channels}] Queuing messages for channel: {channel.name}")
                
                # Check if we have permission to send messages in this channel
                if channel.permissions_for(guild.get_member(bot.user.id)).send_messages:
                    for _ in range(message_count):
                        try:
                            task = asyncio.create_task(channel.send(final_message))
                            all_tasks.append(task)
                        except Exception as e:
                            print(f"Failed to create task for {channel.name}: {e}")
                            failed_messages += 1
            
            # Wait for all tasks to complete
            if all_tasks:
                results = await asyncio.gather(*all_tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, Exception):
                        failed_messages += 1
                    else:
                        sent_messages += 1
            
            print(f"Summary: Sent {sent_messages} messages, Failed: {failed_messages}")
            await bot.close()
        
        try:
            await bot.start(token)
        except Exception as e:
            print(f"Error running bot: {e}")

bot_manager = BotManager()

def run_async(coro):
    """Run async function in a new event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/servers', methods=['POST'])
def get_servers():
    data = request.json
    token = data.get('token')
    
    if not token:
        return jsonify({'error': 'No token provided'}), 400
    
    try:
        servers = run_async(bot_manager.get_bot_servers(token))
        return jsonify({'servers': servers})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/run-tool', methods=['POST'])
def run_tool():
    data = request.json
    token = data.get('token')
    guild_id = data.get('guild_id')
    message = data.get('message')
    message_count = data.get('message_count', 5)
    use_mentions = data.get('use_mentions', False)
    
    if not all([token, guild_id, message]):
        return jsonify({'error': 'Missing required parameters'}), 400
    
    # Run in background thread
    def run_async_tool():
        run_async(bot_manager.run_confession_tool(token, guild_id, message, message_count, use_mentions))
    
    thread = threading.Thread(target=run_async_tool)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'Tool started successfully'})

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, port=5000)