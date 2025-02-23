# Subtitle Translation Telegram Bot

A Telegram bot that helps users translate subtitle (SRT) files using advanced AI translation capabilities. The bot provides a user-friendly interface for subtitle translation services with integrated payment processing.

## Features

- 🎯 Translate SRT subtitle files with high accuracy
- 🧠 Advanced RAG (Retrieval-Augmented Generation) system for context-aware translations
- 📚 Leverages extensive subtitle database for improved accuracy
- 💰 Built-in payment system using Zibal payment gateway
- 🤖 Powered by Dify AI for intelligent translation
- 🔄 Maintains subtitle timing and formatting
- 💳 Credit-based system for translations
- 📊 User balance tracking

## How It Works

### Advanced Translation System

The bot utilizes a sophisticated RAG (Retrieval-Augmented Generation) system to provide highly accurate translations:

1. **Context Retrieval**: When translating a subtitle, the system searches through a vast database of previously translated subtitles to find similar contexts and translations.
2. **Example-Based Learning**: The AI model is provided with relevant examples from the subtitle database, helping it understand context-specific translations and industry terminology.
3. **Enhanced Accuracy**: By combining these examples with the AI's translation capabilities, the system produces more natural and contextually appropriate translations.

This approach significantly improves translation quality by:
- Understanding movie/series-specific terminology
- Maintaining consistency in character names and recurring phrases
- Capturing cultural nuances and idiomatic expressions

## Prerequisites

- Python 3.8+
- PostgreSQL database
- Docker and Docker Compose (for deployment)
- Telegram Bot Token
- Zibal Merchant Account
- Dify AI API Access

## Configuration

Copy `.env.example` to `.env` and configure the following environment variables:

```env
# Telegram Configuration
TELEGRAM_TOKEN=your_bot_token
WEBHOOK_URL=your_webhook_domain

# Payment Gateway (Zibal)
ZIBAL_MERCHAND_ID=your_merchant_id
ZIBAL_RETURN_URL=your_return_url

# Translation Service (Dify)
DIFY_API_KEY=your_dify_api_key
DIFY_API_ENDPOINT=your_dify_endpoint

# Database
DATABASE_URL=your_database_url
```

## Installation

1. Clone the repository:
```bash
git clone https://github.com/m-hoseyny/motarjem.git
cd motarjem
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Run with Docker Compose:
```bash
docker-compose up -d
```

## Database Management

To update the database schema:
```bash
alembic revision --autogenerate -m "your_migration_message"
alembic upgrade head
```

## Third-Party Services

### Zibal Payment Gateway
The bot uses Zibal for processing payments. You'll need to:
- Create a Zibal merchant account
- Configure the merchant ID and return URL
- Set up webhook endpoints for payment confirmation

### Dify AI Translation
Translation is powered by [Dify AI](https://dify.ai), an advanced LLM API platform. You'll need to:
- Obtain API credentials from Dify
- Configure the API endpoint and key
- Ensure sufficient API quota for your usage

## Usage

1. Start a chat with the bot on Telegram
2. Send an SRT file to the bot
3. Choose translation options
4. Process payment if needed
5. Receive translated SRT file

## Support

For support, please [create an issue](https://github.com/m-hoseyny/motarjem) or contact the maintainers.
