from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import asyncio
import aiohttp
import threading
import json
import os

app = Flask(__name__)
CORS(app)

class DiscordAPI:
    def __init__(self):
        self.base_url = "https://discord.com/api/v10"
    
    def get_bot_servers(self, token):
        """Get servers where bot is member using Discord API"""
        headers = {
            'Authorization': f'Bot {token}'
        }
        
        try:
            response = requests.get(f'{self.base_url}/users/@me/guilds', headers=headers)
            
            if response.status_code == 200:
                guilds = response.json()
                servers = []
                
                for guild in guilds:
                    # Check if bot has administrator permissions
                    has_admin = (int(guild['permissions']) & 0x8) == 0x8
                    
                    servers.append({
                        'id': guild['id'],
                        'name': guild['name'],
                        'icon': f"https://cdn.discordapp.com/icons/{guild['id']}/{guild['icon']}.png" if guild['icon'] else None,
                        'hasAdmin': has_admin,
                        'member_count': 'N/A'  # This requires additional API call
                    })
                
                return servers
            else:
                raise Exception(f"API Error: {response.status_code} - {response.text}")
                
        except Exception as e:
            raise Exception(f"Failed to fetch servers: {str(e)}")
    
    def get_guild_channels(self, token, guild_id):
        """Get channels from a guild"""
        headers = {
            'Authorization': f'Bot {token}'
        }
        
        try:
            response = requests.get(f'{self.base_url}/guilds/{guild_id}/channels', headers=headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"API Error: {response.status_code}")
                
        except Exception as e:
            raise Exception(f"Failed to fetch channels: {str(e)}")

discord_api = DiscordAPI()

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
        servers = discord_api.get_bot_servers(token)
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
    def run_tool_async():
        asyncio.run(execute_confession_tool(token, guild_id, message, message_count, use_mentions))
    
    thread = threading.Thread(target=run_tool_async)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'Tool started successfully'})

async def execute_confession_tool(token, guild_id, message, message_count, use_mentions):
    """Execute the confession tool using aiohttp"""
    headers = {
        'Authorization': f'Bot {token}',
        'Content-Type': 'application/json'
    }
    
    # Replace .m with @everyone if mentions are enabled
    final_message = message
    if use_mentions:
        final_message = message.replace(".m", "@everyone")
    
    try:
        # Get guild channels
        async with aiohttp.ClientSession() as session:
            # Get channels
            async with session.get(f'https://discord.com/api/v10/guilds/{guild_id}/channels', headers=headers) as resp:
                if resp.status == 200:
                    channels = await resp.json()
                    
                    # Filter text channels
                    text_channels = [channel for channel in channels if channel['type'] == 0]
                    
                    print(f"Found {len(text_channels)} text channels")
                    
                    # Send messages to each channel
                    sent_count = 0
                    failed_count = 0
                    
                    for channel in text_channels:
                        channel_id = channel['id']
                        channel_name = channel['name']
                        
                        # Check if we have permission to send messages
                        permissions = channel.get('permissions', 0)
                        can_send = (permissions & 0x800) == 0x800  # SEND_MESSAGES permission
                        
                        if can_send:
                            for i in range(message_count):
                                try:
                                    payload = {
                                        'content': final_message
                                    }
                                    
                                    async with session.post(
                                        f'https://discord.com/api/v10/channels/{channel_id}/messages',
                                        headers=headers,
                                        json=payload
                                    ) as msg_resp:
                                        if msg_resp.status == 200:
                                            sent_count += 1
                                            print(f"Sent message {i+1}/{message_count} to #{channel_name}")
                                        else:
                                            failed_count += 1
                                            print(f"Failed to send message to #{channel_name}: {msg_resp.status}")
                                            
                                except Exception as e:
                                    failed_count += 1
                                    print(f"Error sending to #{channel_name}: {e}")
                        else:
                            print(f"No permission to send messages in #{channel_name}")
                    
                    print(f"Completed: {sent_count} sent, {failed_count} failed")
                    
                else:
                    print(f"Failed to get channels: {resp.status}")
                    
    except Exception as e:
        print(f"Error in confession tool: {e}")

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, port=5000)
