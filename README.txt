### README.md Content
```markdown
# Market Mover Discord Bot

A fun Discord bot for daily market predictions (crypto, stock, forex) with free predictions and wagering options. Predict market trends and compete on the leaderboard!

## License
This project is licensed under the MIT License - see the [LICENSE.txt](LICENSE.txt) file for details.

## Requirements
- Python 3.11+
- discord.py
- requests
- python-dotenv
- pytz

## Installation
Follow these steps to set up Market Mover on your Discord server:

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/yourusername/MarketMover.git
   cd MarketMover
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   (Ensure `requirements.txt` contains: `discord.py requests python-dotenv pytz`)

3. **Create a Discord Bot**:
   - Go to the [Discord Developer Portal](https://discord.com/developers/applications).
   - Click "New Application", name it (e.g., "Market Mover"), and create it.
   - Go to the "Bot" tab, click "Add Bot", and confirm.
   - Under "Bot Permissions", enable "Send Messages" and "Add Reactions".
   - Copy the bot token (keep it secret and never share it publicly).
   - Go to the "OAuth2" tab, select "bot" under scopes, choose permissions (Send Messages, Add Reactions), and generate an invite link. Use this link to add the bot to your server.

4. **Set Up Environment**:
   - Create a `.env` file in the same directory as `bot.py` with:
     ```
     BOT_TOKEN=your_discord_bot_token
     ```
   - Replace `your_discord_bot_token` with the token from the Developer Portal.

5. **Configure Channel ID**:
   - Enable Developer Mode in Discord (User Settings > Appearance > Developer Mode).
   - Right-click the channel where you want predictions to post, select "Copy ID", and update `CHANNEL_ID = 1276115765589970966` in `bot.py` to your channel’s ID.

6. **Run the Bot**:
   ```bash
   python bot.py
   ```
   - The bot will start and wait for the scheduled posting time.

## Usage
- **Predictions**: React with 📈 or 📉 to predict for free (win 10 points per correct answer).
- **Wagering**: Use `!bet <points> <up/down> <category>` (e.g., `!bet 50 up stock`) to wager your points.
- **Leverage**: Use `!leverage <points> <category>` (e.g., `!leverage 20 stock`) to increase your wager on an existing prediction.
- **Leaderboard**: Check rankings with `!leaderboard`.
- **Support**: Get donation links with `!support`.

## Schedule
- Posts at 7:30 AM PT, results at 2:00 PM PT, Monday to Friday (skips weekends).
- Automatically adjusts for Pacific Daylight Time (PDT) or Pacific Standard Time (PST).

## Features
- Predict crypto, stock, and forex market movements.
- Free predictions with a 10-point reward for correct answers.
- Optional wagering and leverage to risk accumulated points.
- Real-time leaderboard updates.

## Support
For issues or questions, contact founders@wab3.io or send a Discord DM to wab3.io. Donations are welcome to support development—use `!support` for details.

## Contributing
Feel free to fork this repository, make improvements, and submit pull requests. Please maintain the MIT License and include your changes in the commit history.

## Disclaimer
Market Mover is for entertainment purposes only and uses mock data. It is provided "as is" without warranty. Use at your own risk.
```
