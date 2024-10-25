import os
import yfinance as yf
import logging
import json
import matplotlib.pyplot as plt
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, CommandHandler
from fpdf import FPDF
from pandas_ta import ema
from datetime import datetime

# Logging setup
logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

# Function to check if the JSON file exists, if not create it
def check_json_file():
    if not os.path.exists('bot_usage.json'):
        with open('bot_usage.json', 'w') as f:
            json.dump([], f)

# Function to log user activity in a JSON file
def log_user_activity(user_id, username, command):
    check_json_file()
    
    # Load existing data
    with open('bot_usage.json', 'r') as f:
        data = json.load(f)
    
    # Add new user activity
    data.append({
        'user_id': user_id,
        'username': username,
        'command': command,
        'timestamp': datetime.now().isoformat()
    })
    
    # Save updated data
    with open('bot_usage.json', 'w') as f:
        json.dump(data, f, indent=4)

# Function to format large numbers
def format_number(num):
    if num >= 1_000_000_000:
        return f'{num / 1_000_000_000:.2f}B'
    elif num >= 1_000_000:
        return f'{num / 1_000_000:.2f}M'
    elif num >= 1_000:
        return f'{num / 1_000:.2f}K'
    else:
        return str(num)

# Function to fetch stock data
def fetch_stock_data(symbol):
    stock = yf.Ticker(symbol)
    data = {}
    try:
        data['summary'] = stock.info
        data['news'] = stock.news
        data['chart'] = stock.history(period="1y")
        data['financials'] = stock.financials
        data['holders'] = stock.major_holders
    except Exception as e:
        logging.error(f"Error fetching data for {symbol}: {e}")
    return data

# Function to plot chart with historical prices and EMAs
def plot_stock_chart(symbol, stock_data):
    chart = stock_data['chart']
    
    # Calculate historical EMAs (10-day, 50-day, 200-day)
    chart['10_day_EMA'] = ema(chart['Close'], 10)
    chart['50_day_EMA'] = ema(chart['Close'], 50)
    chart['200_day_EMA'] = ema(chart['Close'], 200)

    plt.figure(figsize=(10, 6))
    
    # Plot Close prices and EMAs
    plt.plot(chart.index, chart['Close'], label='Close Price', color='blue')
    plt.plot(chart.index, chart['10_day_EMA'], label='10-Day EMA', color='green')
    plt.plot(chart.index, chart['50_day_EMA'], label='50-Day EMA', color='orange')
    plt.plot(chart.index, chart['200_day_EMA'], label='200-Day EMA', color='red')
    
    plt.title(f'{symbol} Stock Price with EMAs')
    plt.xlabel('Date')
    plt.ylabel('Price')
    plt.legend(loc='upper left')
    plt.grid(True)

    # Save the chart to a file
    chart_path = os.path.join(os.path.expanduser("~"), "Desktop", f'{symbol}_chart.png')
    plt.savefig(chart_path)
    plt.close()

    return chart_path

# Function to create a PDF with the financial data
def create_pdf(symbol, stock_data, chart_path):
    pdf = FPDF()
    pdf.add_page()

    # Title
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(200, 10, f"Stock Report: {symbol}", ln=True, align='C')

    # Add chart to the first page with spacing
    pdf.image(chart_path, x=10, y=30, w=190)
    pdf.ln(110)  # Add space after the chart

    # Summary Section
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(200, 10, 'Summary', ln=True, align='L')
    pdf.set_font('Arial', '', 12)
    summary = stock_data.get('summary', {})
    for key, value in summary.items():
        pdf.cell(200, 10, f"{key}: {format_number(value) if isinstance(value, (int, float)) else value}", ln=True, align='L')

    # News Section
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(200, 10, 'News', ln=True, align='L')
    pdf.set_font('Arial', '', 12)
    news = stock_data.get('news', [])
    for article in news[:3]:  # Display the first 3 news articles
        pdf.cell(200, 10, f"Title: {article['title']}", ln=True, align='L')
        pdf.cell(200, 10, f"Link: {article['link']}", ln=True, align='L')

    # Financials Section
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(200, 10, 'Financials', ln=True, align='L')
    pdf.set_font('Arial', '', 12)
    financials = stock_data.get('financials', {})
    for col in financials.columns:
        pdf.cell(200, 10, f"{col}: {format_number(financials[col].sum())}", ln=True, align='L')

    # Holders Section
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(200, 10, 'Holders', ln=True, align='L')
    holders = stock_data.get('holders', {})
    for holder in holders:
        pdf.cell(200, 10, f"Holder: {holder}", ln=True, align='L')

    # Save the PDF
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
    file_path = os.path.join(desktop_path, f'{symbol}_full_stock_report.pdf')
    pdf.output(file_path)
    return file_path

# Function to handle the start command (Introduction and Help)
async def start(update: Update, context):
    await update.message.reply_text(
        "Welcome to the Stock Analysis Bot!\n"
        "You can use this bot to get detailed stock reports.\n"
        "Simply enter the stock symbol to receive a financial and technical analysis.\n"
        "For example: Send 'AAPL' to get the Apple stock report.\n"
        "For any inquiries, feel free to contact us."
    )

# Function to check and handle Saudi stock symbols
def normalize_symbol(symbol):
    if symbol.isdigit():
        return f"{symbol}.SR"
    return symbol

# Function to fetch stock data and send PDF
async def send_stock_pdf(update: Update, context):
    symbol = update.message.text.strip().upper()  # Extract the stock symbol from user's message
    
    # Normalize Saudi stock symbols
    symbol = normalize_symbol(symbol)
    
    # Validate stock symbol input
    if not symbol.isalnum() and not symbol.endswith('.SR'):
        await update.message.reply_text("Please enter a valid stock symbol.")
        return

    # Log the user activity
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    log_user_activity(user_id, username, symbol)
    
    # Send interactive message while preparing the report
    await update.message.reply_text(f"Preparing the report for {symbol}...")

    # Fetch the stock data
    stock_data = fetch_stock_data(symbol)
    
    # Check if data exists
    if stock_data and 'summary' in stock_data and stock_data['summary']:
        # Plot and save the chart with EMAs
        chart_path = plot_stock_chart(symbol, stock_data)
        
        # Create PDF with the stock data
        pdf_path = create_pdf(symbol, stock_data, chart_path)
        
        # Send the PDF to the user
        await context.bot.send_document(chat_id=update.effective_chat.id, document=open(pdf_path, 'rb'), caption=f"Stock Report for {symbol}")
    else:
        await update.message.reply_text(f"Sorry, no data found for the stock symbol '{symbol}'. Please check the symbol and try again.")

# Function to get the number of unique users
def get_unique_users():
    check_json_file()
    
    with open('bot_usage.json', 'r') as f:
        data = json.load(f)
        
    # Get the unique user_ids
    unique_users = {entry['user_id'] for entry in data}
    return len(unique_users)

# Function to handle the /users command to show unique user count
async def users_count(update: Update, context):
    count = get_unique_users()
    await update.message.reply_text(f"Total unique users: {count}")

# Bot setup
if __name__ == '__main__':
    # Set up your Telegram bot token (add this in an environment variable for security)
    TOKEN = os.getenv("6035947166:AAGIelWBYakN9_u8PoKXWFC_aTW7K2UVAww")

    # Initialize the bot application
    application = Application.builder().token('6035947166:AAGIelWBYakN9_u8PoKXWFC_aTW7K2UVAww').build()

    # Set up handlers
    start_handler = CommandHandler('start', start)  # Start command to show bot info
    users_handler = CommandHandler('users', users_count)  # Command to show unique user count
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, send_stock_pdf)  # Message handler for stock symbol

    application.add_handler(start_handler)  # Add start handler
    application.add_handler(users_handler)  # Add users handler
    application.add_handler(message_handler)  # Add message handler
    
    # Webhook setup
    WEBHOOK_URL = f"https://<your-vercel-project-name>.vercel.app/{TOKEN}"  # Replace with your Vercel project URL
    
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get('PORT', '8443')),
        webhook_url=WEBHOOK_URL
    )