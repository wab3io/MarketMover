from dotenv import load_dotenv
import os
import discord
from discord.ext import commands, tasks
from discord import Intents
import requests
import json
import asyncio
import time
import random
from pytz import timezone
from flask import Flask
from threading import Thread

# Bot setup
load_dotenv()  # Use default Replit .env loading
BOT_TOKEN = os.getenv("BOT_TOKEN")
print(f"Loaded BOT_TOKEN: {BOT_TOKEN}")  # Debug token loading
if not BOT_TOKEN:
    print("Error: BOT_TOKEN is not loaded. Check .env file and path.")

intents = Intents.default()
intents.message_content = True  # Allows the bot to read message content
intents.members = True  # Enable server members intent (if needed)
intents.presences = True  # Enable presence intent (if needed)

bot = commands.Bot(command_prefix="!", intents=intents)

# Game data
players = {}
bets = {}  # {user_id: {category: {"points": int, "direction": str, "timestamp": float}}}
current_assets = {}  # Store assets {category: asset}
current_messages = {}  # Track multiple messages {category: message}
CHANNEL_ID = {}  # Dictionary to store channel IDs per guild

# Mock data for stocks and forex (since free APIs are limited)
stocks = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "WMT"]
forex = ["EUR/USD", "USD/JPY", "GBP/USD", "AUD/USD", "CHF/USD", "CAD/USD", "NZD/USD", "EUR/JPY"]

print(f"Current working dictionary: {os.getcwd()}")  # Debug directory

# Load or initialize players.json
def load_players():
    try:
        with open("players.json", "a+") as f:  # Use relative path for Replit
            f.seek(0)  # Move to start of file
            content = f.read().strip()
            if not content:  # If empty, initialize with empty dict
                return {}
            return json.loads(content)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print("Warning: players.json contains invalid JSON, initializing empty.")
        return {}

# Save players.json
def save_players(players):
    print("Attempting to save players...")
    try:
        with open("players.json", "w") as f:  # Use relative path for Replit
            json.dump(players, f)
        print(f"Players saved to players.json: {players}")
    except Exception as e:
        print(f"Error saving players.json: {e}")

# Fetch random crypto from top 10
def get_random_crypto():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 10}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        coins = response.json()
        if not coins:
            print("No coins returned from API")
            return {"name": "BTC", "symbol": "BTC", "current_price": 30000}  # Fallback
        return random.choice(coins)
    except Exception as e:
        print(f"Error fetching trending crypto: {e}")
        return {"name": "BTC", "symbol": "BTC", "current_price": 30000}  # Fallback

# Get random stock
def get_random_stock():
    stock = random.choice(stocks)
    return {"name": stock, "symbol": stock, "current_price": round(random.uniform(100, 1000), 2)}

# Get random forex
def get_random_forex():
    pair = random.choice(forex)
    return {"name": pair, "symbol": pair, "current_price": round(random.uniform(0.8, 1.5), 4)}

# Get default channel in each server
def get_default_channel(guild):
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            return channel
    return None

# Get daily assets (one random from each category)
def get_daily_assets():
    return {
        "crypto": get_random_crypto(),
        "stock": get_random_stock(),
        "forex": get_random_forex()
    }

# Web server for keep-alive
app = Flask('')

@app.route('/')
def home():
    return "Bot is running"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Bot ready event
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    global players
    players = load_players()
    print(f"Loaded players: {players}")
    # Start fresh with no initial players beyond load
    print(f"Before save, players: {players}")  # Debug
    save_players(players)  # Save initial state
    keep_alive()  # Start web server
    print("Bot is ready and waiting for scheduled posts at 6:30 AM PT...")

# Game loop (posts at 6:30 AM and 2:00 PM PT, weekdays only)
async def game_loop():
    while True:
        pacific = timezone('America/Los_Angeles')
        now = pacific.localize(time.localtime())  # Use PT timezone
        # Skip weekends (Saturday=5, Sunday=6 in weekday numbering)
        if 0 <= now.weekday() <= 4:  # Monday to Friday
            if now.hour == 6 and now.minute == 30:  # 6:30 AM PT
                await post_assets()
            elif now.hour == 14 and now.minute == 0:  # 2:00 PM PT
                await check_results()
        await asyncio.sleep(60)  # Check every minute

# Post new assets (separate posts with mentions in title)
async def post_assets():
    global current_assets, current_messages, bets
    bets = {}  # Reset bets
    current_assets = get_daily_assets()
    if not all(current_assets.values()):
        return
    for guild in bot.guilds:  # Post in all servers where the bot is added
        guild_id = guild.id
        channel = bot.get_channel(CHANNEL_ID.get(guild_id)) if CHANNEL_ID.get(guild_id) and bot.get_channel(CHANNEL_ID.get(guild_id)) else await get_default_channel(guild)
        if channel:
            for category, asset in current_assets.items():
                mention = "@Crypto" if category == "crypto" else "@Stocks" if category == "stock" else "@FOREX"
                embed = discord.Embed(
                    title=f"Daily {mention} Prediction",
                    description=f"Will {asset['name']} ({asset['symbol']}) go 📈 or 📉 by 2:00 PM PT?\n"
                                f"Posted at 6:30 AM PT. React with 📈 or 📉 to predict for free! Win 10 points per correct answer. "
                                f"Use `!bet <points> <up/down> {category}` to wager your points, or `!leverage <points> {category}` to increase your bet.",
                    color=0x00ff00
                )
                current_messages[category] = await channel.send(embed=embed)
                await current_messages[category].add_reaction("📈")  # Stock up emoji
                await current_messages[category].add_reaction("📉")  # Stock down emoji
        else:
            print(f"No suitable channel found in guild {guild.name} (ID: {guild.id})")

# Handle reactions (per category, no channel confirmation, free prediction)
@bot.event
async def on_reaction_add(reaction, user):
    print(f"Reaction: {reaction.emoji}, Message ID: {reaction.message.id}, Messages: {current_messages}")
    if user.bot:
        return
    category = next((cat for cat, msg in current_messages.items() if msg.id == reaction.message.id), None)
    if not category:
        return
    user_id = str(user.id)
    if user_id not in bets:
        bets[user_id] = {}
    if category in bets[user_id]:
        print(f"{user.name} tried to change vote on {category}, selection locked")
        return  # Prevent changing vote
    if user_id not in players:
        players[user_id] = {"points": 100, "name": user.name}
    direction = "up" if reaction.emoji == "📈" else "down" if reaction.emoji == "📉" else None
    if direction is None:
        return  # Ignore other reactions
    bets[user_id][category] = {"points": 0, "direction": direction, "timestamp": time.time()}  # No cost
    save_players(players)  # Save to ensure player exists
    print(f"{user.name} predicted {direction} on {category} for free at {time.ctime()}, Current balance: {players[user_id]['points']}")

# Bet command (wager accumulated points)
@bot.command()
async def bet(ctx, points: int, direction: str, category: str):
    if not current_assets:
        await ctx.send("No active predictions. Please wait for the daily post at 6:30 AM PT.")
        return
    if direction.lower() not in ["up", "down"]:
        await ctx.send("Direction must be 'up' or 'down'.")
        return
    if points < 0 or points > players.get(str(ctx.author.id), {"points": 0})["points"]:
        await ctx.send("Invalid bet amount or insufficient points.")
        return
    category = category.lower()
    if category not in ["crypto", "stock", "forex"]:
        await ctx.send("Category must be 'crypto', 'stock', or 'forex'.")
        return
    user_id = str(ctx.author.id)
    if user_id not in players:
        players[user_id] = {"points": 100, "name": ctx.author.name}
    if user_id not in bets:
        bets[user_id] = {}
    if category in bets[user_id]:
        await ctx.send("You’ve already placed a bet for this category today.")
        return
    bets[user_id][category] = {"points": points, "direction": direction.lower(), "timestamp": time.time()}
    players[user_id]["points"] -= points  # Deduct wager
    if players[user_id]["points"] < 0:  # Prevent negative points
        players[user_id]["points"] = 0
    save_players(players)
    await ctx.send(f"{ctx.author.name} wagered {points} points on {category} ({direction}) at {time.ctime()}, New balance: {players[user_id]['points']}")
    print(f"{ctx.author.name} wagered {points} points on {category} ({direction}) at {time.ctime()}, New balance: {players[user_id]['points']}")

# Predict command (free prediction)
@bot.command()
async def predict(ctx, direction: str, category: str):
    if not current_assets:
        await ctx.send("No active predictions. Please wait for the daily post at 6:30 AM PT.")
        return
    direction = direction.lower()
    if direction not in ["up", "down"]:
        await ctx.send("Direction must be 'up' or 'down'.")
        return
    category = category.lower()
    if category not in ["crypto", "stock", "forex"]:
        await ctx.send("Category must be 'crypto', 'stock', or 'forex'.")
        return
    user_id = str(ctx.author.id)
    if user_id not in players:
        players[user_id] = {"points": 100, "name": ctx.author.name}
    if user_id not in bets:
        bets[user_id] = {}
    if category in bets[user_id]:
        await ctx.send("You’ve already made a prediction for this category today.")
        return
    bets[user_id][category] = {"points": 0, "direction": direction, "timestamp": time.time()}  # No cost
    save_players(players)  # Save to ensure player exists
    await ctx.send(f"{ctx.author.name} predicted {direction} on {category} for free at {time.ctime()}, Current balance: {players[user_id]['points']}")
    print(f"{ctx.author.name} predicted {direction} on {category} for free at {time.ctime()}, Current balance: {players[user_id]['points']}")

# Leverage command (increase wager)
@bot.command()
async def leverage(ctx, points: int, category: str):
    if not current_assets:
        await ctx.send("No active predictions. Please wait for the daily post at 6:30 AM PT.")
        return
    user_id = str(ctx.author.id)
    if user_id not in players:
        players[user_id] = {"points": 100, "name": ctx.author.name}
    current_points = players[user_id]["points"]
    if points <= 0 or points > current_points:
        await ctx.send("Invalid leverage amount or insufficient points.")
        return
    category = category.lower()
    if category not in ["crypto", "stock", "forex"]:
        await ctx.send("Category must be 'crypto', 'stock', or 'forex'.")
        return
    if user_id not in bets or category not in bets[user_id]:
        await ctx.send("No active bet to leverage for this category.")
        return
    initial_points = bets[user_id][category]["points"]
    total_wager = initial_points + points
    if total_wager > current_points:
        await ctx.send(f"{ctx.author.name} tried to exceed current points on {category}")
        return
    players[user_id]["points"] -= points
    if players[user_id]["points"] < 0:
        players[user_id]["points"] = 0
    bets[user_id][category]["points"] = total_wager
    save_players(players)
    await ctx.send(f"{ctx.author.name} leveraged {points} points on {category} at {time.ctime()}, New balance: {players[user_id]['points']}, Total wager: {total_wager}")
    print(f"{ctx.author.name} leveraged {points} points on {category} at {time.ctime()}, New balance: {players[user_id]['points']}, Total wager: {total_wager}")

# Set channel command
@bot.command()
async def setchannel(ctx):
    global CHANNEL_ID
    guild_id = ctx.guild.id
    CHANNEL_ID[guild_id] = ctx.channel.id
    await ctx.send(f"Channel set to {ctx.channel.name} (ID: {CHANNEL_ID[guild_id]}) for this server.")

# Check results (award 10 points per correct answer, honor wagers)
async def check_results():
    global current_assets, current_messages, bets
    if not current_assets:
        return
    for guild in bot.guilds:  # Check results in all servers
        guild_id = guild.id
        channel = bot.get_channel(CHANNEL_ID.get(guild_id)) if CHANNEL_ID.get(guild_id) and bot.get_channel(CHANNEL_ID.get(guild_id)) else await get_default_channel(guild)
        if channel:
            results = {}
            for category, asset in current_assets.items():
                old_price = asset["current_price"]
                new_price = old_price + random.uniform(-50, 50) if isinstance(old_price, (int, float)) else old_price  # Mock price change
                direction = "up" if new_price > old_price else "down"
                results[category] = {"direction": direction, "old_price": old_price, "new_price": new_price}
            for category in ["crypto", "stock", "forex"]:
                embed = discord.Embed(
                    title=f"Results for {category.capitalize()}",
                    description=f"{current_assets[category]['name']} went {results[category]['direction']}!\n"
                                f"Old price: ${results[category]['old_price']:.2f}, New price: ${results[category]['new_price']:.2f}",
                    color=0x0000ff
                )
                winners = []
                for user_id, user_bets in bets.items():
                    if category in user_bets:
                        bet = user_bets[category]
                        # Enforce 7.5-hour window (27,000 seconds) for game schedule
                        if time.time() - bet["timestamp"] > 27000:
                            continue
                        multiplier = 1 if bet["direction"] == results[category]["direction"] else 0  # 1 for correct, 0 for incorrect
                        points_won = bet["points"] * multiplier + 10 if multiplier else 0  # 10 points for correct, wager returned if incorrect
                        players[user_id]["points"] += points_won
                        if players[user_id]["points"] < 0:  # Prevent negative points
                            players[user_id]["points"] = 0
                        result = f"+{points_won} points" if points_won > 0 else "0 points"
                        winners.append(f"{players[user_id]['name']}: {result}")
                        print(f"{user_id} on {category}: Bet {bet['points']} on {bet['direction']}, Result {results[category]['direction']}, Points won {points_won}, New balance: {players[user_id]['points']}")
                save_players(players)
                if winners:
                    embed.add_field(name="Results", value="\n".join(winners), inline=False)
                else:
                    embed.add_field(name="Results", value="No bets placed.", inline=False)
                await channel.send(embed=embed)
    current_assets = {}
    current_messages = {}
    bets = {}

# Leaderboard command
@bot.command()
async def leaderboard(ctx):
    sorted_players = sorted(players.items(), key=lambda x: x[1]["points"], reverse=True)
    print(f"Leaderboard players: {sorted_players}")  # Debug
    embed = discord.Embed(title="Leaderboard", color=0xffff00)
    if not sorted_players:
        embed.description = "No players yet!"
    for i, (user_id, data) in enumerate(sorted_players[:5], 1):
        embed.add_field(name=f"{i}. {data['name']}", value=f"{data['points']} points", inline=False)
    await ctx.send(embed=embed)

# Support command with donation link (your actual addresses)
@bot.command()
async def support(ctx):
    await ctx.send("Support Market Mover! Time is money—tip to keep the markets moving. Donate:\n- Bitcoin (BTC): bc1qdpugyzg3jv8s88qs0xpt6gh4kewnh8ek3udgpe\n- USDC on ETH: 0x4F3a5C130d1aa7dE39BEe1Ff455039eCEeD7682")

# Start bot
bot.run(BOT_TOKEN)