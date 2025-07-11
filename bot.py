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
from pytz import timezone, UTC, all_timezones
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
import logging
import signal

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
EXCHANGE_RATE_KEY = os.getenv("EXCHANGE_RATE_KEY")
OWNER_ID = int(os.getenv("OWNER_ID", 0))  # Your Discord ID as int

if not BOT_TOKEN:
    logger.error("BOT_TOKEN not found in .env")
if not ALPHA_VANTAGE_KEY:
    logger.warning("ALPHA_VANTAGE_KEY not found; stock prices will use mock data")
if not EXCHANGE_RATE_KEY:
    logger.warning("EXCHANGE_RATE_KEY not found; forex rates will use mock data")
if not OWNER_ID:
    logger.warning("OWNER_ID not found; admin commands disabled")

intents = Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)  # Custom help

# Game data
players = {}
bets = {}  # {user_id: {category: {"points": int, "direction": str, "timestamp": float}}}
current_assets = {}  # {category: asset}
current_messages = {}  # {category: message}
last_post_time = None
POST_COOLDOWN_MINUTES = 5

# Persistent files
PLAYERS_FILE = "players.json"
CONFIG_FILE = "config.json"

# Load players
def load_players() -> dict:
    try:
        with open(PLAYERS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Save players
def save_players(players: dict) -> None:
    try:
        with open(PLAYERS_FILE, "w") as f:
            json.dump(players, f)
        logger.info("Players saved")
    except Exception as e:
        logger.error(f"Error saving players: {e}")

# Load config
def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"CHANNEL_ID": {}, "ALERT_CHANNEL_ID": {}, "SERVER_TIMEZONES": {}}

# Save config
def save_config(config: dict) -> None:
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)
        logger.info("Config saved")
    except Exception as e:
        logger.error(f"Error saving config: {e}")

# Get default channel
def get_default_channel(guild: discord.Guild) -> discord.TextChannel | None:
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            return channel
    return None

# Fetch real stock
def get_random_stock() -> dict:
    stocks = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "WMT"]
    symbol = random.choice(stocks)
    if ALPHA_VANTAGE_KEY:
        try:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_VANTAGE_KEY}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()['Global Quote']
            price = float(data['05. price'])
            return {"name": symbol, "symbol": symbol, "current_price": price}
        except Exception as e:
            logger.error(f"Alpha Vantage error: {e}")
    # Fallback mock
    return {"name": symbol, "symbol": symbol, "current_price": round(random.uniform(100, 1000), 2)}

# Fetch real forex
def get_random_forex() -> dict:
    pairs = ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD", "NZDUSD", "EURJPY"]
    pair = random.choice(pairs)
    base, quote = pair[:3], pair[3:]
    if EXCHANGE_RATE_KEY:
        try:
            url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_RATE_KEY}/latest/{base}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            rate = data['conversion_rates'][quote]
            return {"name": pair, "symbol": pair, "current_price": rate}
        except Exception as e:
            logger.error(f"ExchangeRate-API error: {e}")
    # Fallback mock
    return {"name": pair, "symbol": pair, "current_price": round(random.uniform(0.8, 1.5), 4)}

# Fetch real crypto (Coingecko, free)
def get_random_crypto() -> dict:
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=10"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        coins = response.json()
        return random.choice(coins)
    except Exception as e:
        logger.error(f"Coingecko error: {e}")
        return {"name": "BTC", "symbol": "BTC", "current_price": 30000}

# Get daily assets
def get_daily_assets() -> dict:
    return {
        "crypto": get_random_crypto(),
        "stock": get_random_stock(),
        "forex": get_random_forex()
    }

# Fetch new price for results
def fetch_new_price(asset: dict, category: str) -> float:
    if category == "crypto":
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={asset['id']}&vs_currencies=usd"
        try:
            response = requests.get(url, timeout=10)
            return response.json()[asset['id']]['usd']
        except Exception:
            return asset['current_price'] + random.uniform(-50, 50)  # Fallback
    elif category == "stock":
        if ALPHA_VANTAGE_KEY:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={asset['symbol']}&apikey={ALPHA_VANTAGE_KEY}"
            try:
                response = requests.get(url, timeout=10)
                return float(response.json()['Global Quote']['05. price'])
            except Exception:
                pass
        return asset['current_price'] + random.uniform(-50, 50)
    elif category == "forex":
        base, quote = asset['symbol'][:3], asset['symbol'][3:]
        if EXCHANGE_RATE_KEY:
            url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_RATE_KEY}/latest/{base}"
            try:
                response = requests.get(url, timeout=10)
                return response.json()['conversion_rates'][quote]
            except Exception:
                pass
        return asset['current_price'] + random.uniform(-0.1, 0.1)

# Web server for keep-alive
app = Flask('')

@app.route('/')
def home():
    return "Bot is running"

def run():
    app.run(host='0.0.0.0', port=8080, use_reloader=False)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Bot ready event
@bot.event
async def on_ready():
    global last_post_time, config
    logger.info(f"Logged in as {bot.user}")
    global players
    players = load_players()
    config = load_config()
    global CHANNEL_ID, ALERT_CHANNEL_ID, SERVER_TIMEZONES
    CHANNEL_ID = config["CHANNEL_ID"]
    ALERT_CHANNEL_ID = config["ALERT_CHANNEL_ID"]
    SERVER_TIMEZONES = config["SERVER_TIMEZONES"]
    keep_alive()
    last_post_time = None
    logger.info("Initial last_post_time reset to None")
    bot.loop.create_task(game_loop())
    # Notify if channels unset
    for guild in bot.guilds:
        if guild.id not in CHANNEL_ID or guild.id not in ALERT_CHANNEL_ID:
            default_channel = get_default_channel(guild)
            if default_channel:
                await default_channel.send("You need to set the channel using !setchannel and !setbotalert.")
    # Restart notification
    for guild in bot.guilds:
        alert_channel = bot.get_channel(ALERT_CHANNEL_ID.get(guild.id))
        if alert_channel:
            await alert_channel.send("Bot has restarted.")

# On guild join onboarding
@bot.event
async def on_guild_join(guild):
    default_channel = get_default_channel(guild)
    if default_channel:
        await default_channel.send("Welcome to Market Mover Bot! Setup:\n1. !setchannel in desired post channel.\n2. !setbotalert in alert channel.\n3. !settimezone <tz> (e.g., America/Phoenix).\nUse !help for commands.")

# Disconnect event
@bot.event
async def on_disconnect():
    logger.info("Bot disconnected")
    for guild in bot.guilds:
        alert_channel = bot.get_channel(ALERT_CHANNEL_ID.get(guild.id))
        if alert_channel:
            await alert_channel.send("Bot disconnected, attempting to reconnect.")

# Resume event
@bot.event
async def on_resume():
    logger.info("Bot resumed")
    for guild in bot.guilds:
        alert_channel = bot.get_channel(ALERT_CHANNEL_ID.get(guild.id))
        if alert_channel:
            await alert_channel.send("Bot is back online.")

# Signal handler for shutdown
def shutdown_handler(signum, frame):
    logger.info("Shutdown signal received")
    asyncio.run(send_shutdown_alert())
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

async def send_shutdown_alert():
    for guild in bot.guilds:
        alert_channel = bot.get_channel(ALERT_CHANNEL_ID.get(guild.id))
        if alert_channel:
            await alert_channel.send("Bot is shutting down.")

# Game loop
async def game_loop():
    while True:
        now = datetime.now(UTC)
        if 0 <= now.weekday() <= 4:
            post_time = now.replace(hour=6, minute=30, second=0, microsecond=0)
            if now >= post_time and (last_post_time is None or (now - last_post_time) > timedelta(minutes=POST_COOLDOWN_MINUTES)):
                await post_assets()
                last_post_time = now
            results_time = now.replace(hour=14, minute=0, second=0, microsecond=0)
            if now >= results_time and (last_post_time is not None and (now - last_post_time) > timedelta(hours=7)):
                await check_results()
        await asyncio.sleep(60)

# Post assets
async def post_assets():
    global current_assets, current_messages, bets
    bets = {}
    current_assets = get_daily_assets()
    logger.info(f"Current assets: {current_assets}")
    for guild in bot.guilds:
        channel_id = CHANNEL_ID.get(guild.id)
        channel = bot.get_channel(channel_id) if channel_id else get_default_channel(guild)
        if not channel or not channel.permissions_for(guild.me).send_messages:
            logger.warning(f"No valid channel in {guild.name}")
            continue
        tz_str = SERVER_TIMEZONES.get(guild.id, 'UTC')
        try:
            tz = timezone(tz_str)
        except:
            tz = UTC
            logger.warning(f"Invalid timezone for {guild.name}, using UTC")
        post_local = datetime.now(tz).strftime("%I:%M %p %Z")
        results_local = (datetime.now(UTC) + timedelta(hours=7.5)).astimezone(tz).strftime("%I:%M %p %Z")
        for category, asset in current_assets.items():
            role = discord.utils.get(guild.roles, name=category.capitalize())
            mention = role.mention if role else f"@{category.capitalize()}"
            embed = discord.Embed(
                title=f"Daily {mention} Prediction",
                description=f"Will {asset['name']} ({asset['symbol']}) go 📈 or 📉 by {results_local}?\nPosted at {post_local}. React to predict free (win 10 points). !bet/!leverage for wagers.",
                color=0x00ff00
            )
            msg = await channel.send(embed=embed)
            await msg.add_reaction("📈")
            await msg.add_reaction("📉")
            current_messages[category] = msg
            # Notify subscribers
            for user_id, data in players.items():
                if category in data.get('subscriptions', []):
                    user = guild.get_member(int(user_id))
                    if user:
                        await user.send(f"New {category} prediction in {guild.name}: {asset['name']}")

# Reaction handler
@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    if user.bot or reaction.message not in current_messages.values():
        return
    category = next((cat for cat, msg if msg == reaction.message), None)
    if not category:
        return
    user_id = str(user.id)
    if user_id not in players:
        players[user_id] = {"points": 100, "name": user.name, "bet_history": [], "last_daily": 0, "subscriptions": []}
    if user_id not in bets:
        bets[user_id] = {}
    if category in bets[user_id]:
        return
    direction = "up" if reaction.emoji == "📈" else "down" if reaction.emoji == "📉" else None
    if direction:
        bets[user_id][category] = {"points": 0, "direction": direction, "timestamp": time.time()}
        save_players(players)

# Bet command
@bot.command()
async def bet(ctx: commands.Context, points: int, direction: str, category: str):
    if not current_assets:
        await ctx.send("No active predictions.")
        return
    if points <= 0 or direction.lower() not in ["up", "down"] or category.lower() not in ["crypto", "stock", "forex"]:
        await ctx.send("Invalid input. Use: !bet <positive points> <up/down> <crypto/stock/forex>")
        return
    user_id = str(ctx.author.id)
    if user_id not in players:
        players[user_id] = {"points": 100, "name": ctx.author.name, "bet_history": [], "last_daily": 0, "subscriptions": []}
    if players[user_id]["points"] < points:
        await ctx.send("Insufficient points.")
        return
    if user_id not in bets:
        bets[user_id] = {}
    if category in bets[user_id]:
        await ctx.send("Already bet on this category.")
        return
    bets[user_id][category] = {"points": points, "direction": direction.lower(), "timestamp": time.time()}
    players[user_id]["points"] -= points
    save_players(players)
    await ctx.send(f"Bet placed: {points} on {direction} for {category}. Balance: {players[user_id]['points']}")

# Other commands similar, with validation

# Profile command
@bot.command()
async def profile(ctx: commands.Context, user: discord.Member = None):
    target = user or ctx.author
    user_id = str(target.id)
    if user_id not in players:
        await ctx.send("No profile found.")
        return
    data = players[user_id]
    wins = sum(1 for bet in data.get('bet_history', []) if bet['correct'])
    total = len(data['bet_history'])
    win_rate = (wins / total * 100) if total > 0 else 0
    embed = discord.Embed(title=f"{target.name}'s Profile", color=0x00ff00)
    embed.add_field(name="Points", value=data['points'])
    embed.add_field(name="Win Rate", value=f"{win_rate:.2f}% ({wins}/{total})")
    embed.add_field(name="Bet History", value="\n".join([f"{b['category']}: {b['direction']} ({'Win' if b['correct'] else 'Loss'})" for b in data['bet_history'][-5:]] or "No history"))
    await ctx.send(embed=embed)

# Daily command
@bot.command()
async def daily(ctx: commands.Context):
    user_id = str(ctx.author.id)
    if user_id not in players:
        players[user_id] = {"points": 100, "name": ctx.author.name, "bet_history": [], "last_daily": 0, "subscriptions": []}
    if time.time() - players[user_id]["last_daily"] > 86400:
        players[user_id]["points"] += 50
        players[user_id]["last_daily"] = time.time()
        save_players(players)
        await ctx.send("Claimed 50 daily points!")
    else:
        await ctx.send("Already claimed today.")

# Admin forcepost
@bot.command()
async def forcepost(ctx: commands.Context):
    if ctx.author.id != OWNER_ID:
        await ctx.send("Admin only.")
        return
    await post_assets()
    await ctx.send("Forced post.")

# Resetpoints
@bot.command()
async def resetpoints(ctx: commands.Context, user: discord.Member):
    if ctx.author.id != OWNER_ID:
        await ctx.send("Admin only.")
        return
    user_id = str(user.id)
    if user_id in players:
        players[user_id]["points"] = 100
        save_players(players)
        await ctx.send(f"Reset {user.name}'s points to 100.")

# Subscribe
@bot.command()
async def subscribe(ctx: commands.Context, category: str):
    category = category.lower()
    if category not in ["crypto", "stock", "forex"]:
        await ctx.send("Invalid category.")
        return
    user_id = str(ctx.author.id)
    if user_id not in players:
        players[user_id] = {"points": 100, "name": ctx.author.name, "bet_history": [], "last_daily": 0, "subscriptions": []}
    if category not in players[user_id]["subscriptions"]:
        players[user_id]["subscriptions"].append(category)
        save_players(players)
        await ctx.send(f"Subscribed to {category} notifications.")

# Tip
@bot.command()
async def tip(ctx: commands.Context, user: discord.Member, points: int):
    if points <= 0:
        await ctx.send("Positive points only.")
        return
    sender_id = str(ctx.author.id)
    receiver_id = str(user.id)
    if sender_id not in players or players[sender_id]["points"] < points:
        await ctx.send("Insufficient points.")
        return
    if receiver_id not in players:
        players[receiver_id] = {"points": 100, "name": user.name, "bet_history": [], "last_daily": 0, "subscriptions": []}
    players[sender_id]["points"] -= points
    players[receiver_id]["points"] += points
    save_players(players)
    await ctx.send(f"Tipped {points} points to {user.name}.")

# Set timezone
@bot.command()
async def settimezone(ctx: commands.Context, tz: str):
    if tz not in all_timezones:
        await ctx.send("Invalid timezone. Use pytz names like America/Phoenix.")
        return
    guild_id = str(ctx.guild.id)
    config["SERVER_TIMEZONES"][guild_id] = tz
    save_config(config)
    await ctx.send(f"Timezone set to {tz}.")

# Check results
async def check_results():
    global current_assets, current_messages, bets
    if not current_assets:
        return
    is_friday = datetime.now(UTC).weekday() == 4
    multiplier = 2 if is_friday else 1
    for guild in bot.guilds:
        channel = bot.get_channel(CHANNEL_ID.get(guild.id, get_default_channel(guild)))
        if not channel:
            continue
        for category in ["crypto", "stock", "forex"]:
            asset = current_assets[category]
            new_price = fetch_new_price(asset, category)
            direction = "up" if new_price > asset["current_price"] else "down"
            embed = discord.Embed(title=f"Results for {category.capitalize()}", color=0x0000ff)
            embed.description = f"{asset['name']} went {direction}! Old: {asset['current_price']}, New: {new_price}"
            if is_friday:
                embed.description += " (Double points!)"
            winners = []
            for user_id, user_bets in bets.items():
                if category in user_bets:
                    bet = user_bets[category]
                    correct = bet["direction"] == direction
                    points_won = (bet["points"] * multiplier if correct else 0) + (10 * multiplier if correct else 0)
                    players[user_id]["points"] += points_won
                    players[user_id]["bet_history"].append({"category": category, "direction": bet["direction"], "correct": correct})
                    winners.append(f"{players[user_id]['name']}: +{points_won} points")
                    # Notify subscriber
                    if category in players[user_id].get('subscriptions', []):
                        user = guild.get_member(int(user_id))
                        if user:
                            await user.send(f"{category} result in {guild.name}: {direction}. You won {points_won} points.")
            if winners:
                embed.add_field(name="Winners", value="\n".join(winners))
            else:
                embed.add_field(name="Winners", value="No bets.")
            await channel.send(embed=embed)
    current_assets = {}
    current_messages = {}
    bets = {}

# Custom help
@bot.command()
async def help(ctx: commands.Context):
    embed = discord.Embed(title="Market Mover Commands", color=0x00ff00)
    embed.add_field(name="!predict <up/down> <category>", value="Free prediction (win 10 points if correct).", inline=False)
    embed.add_field(name="!bet <points> <up/down> <category>", value="Wager points on prediction.", inline=False)
    embed.add_field(name="!leverage <points> <category>", value="Increase existing bet.", inline=False)
    embed.add_field(name="!profile [user]", value="View profile and stats.", inline=False)
    embed.add_field(name="!daily", value="Claim 50 daily points.", inline=False)
    embed.add_field(name="!tip <user> <points>", value="Transfer points to user.", inline=False)
    embed.add_field(name="!subscribe <category>", value="Get DM notifications for category.", inline=False)
    embed.add_field(name="!leaderboard", value="Top 5 players.", inline=False)
    embed.add_field(name="!support", value="Donation info.", inline=False)
    embed.add_field(name="!setchannel", value="Set post channel.", inline=False)
    embed.add_field(name="!setbotalert", value="Set alert channel.", inline=False)
    embed.add_field(name="!settimezone <tz>", value="Set guild timezone (e.g., America/Phoenix).", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="!forcepost", value="Admin: Force daily post.", inline=False)
        embed.add_field(name="!resetpoints <user>", value="Admin: Reset user points to 100.", inline=False)
    await ctx.send(embed=embed)

# Leverage command (similar to bet, with validation)

# Run bot
try:
    bot.run(BOT_TOKEN)
except Exception as e:
    logger.error(f"Bot error: {e}")
    asyncio.run(shutdown_task())