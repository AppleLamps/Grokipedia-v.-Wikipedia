# Grokipedia

An AI-powered encyclopedia article generator inspired by Elon Musk's vision for a bias-free "Encyclopedia Galactica." Uses xAI's Grok model with web and X search capabilities to research and write neutral, fact-checked articles.

**Author:** Apple Lamps ([@lamps_apple](https://x.com/lamps_apple))

## Features

- 🔍 **AI-Powered Research**: Uses xAI's Grok-4 with web search and X search tools to gather real-time information
- 📝 **Create Mode**: Generate original Grokipedia articles from Wikipedia URLs with fact-checking and bias removal
- ⚖️ **Compare Mode**: Side-by-side comparison of Grokipedia vs Wikipedia articles with AI bias analysis
- ✏️ **Edit Mode**: Get AI-suggested edits to improve existing Grokipedia articles
- 🎯 **Bias Detection**: Identifies and removes "woke" ideological bias, political framing, and activist spin
- 🚀 **Encyclopedia Galactica**: Articles written for a long-term civilizational record

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment (create .env file)
XAI_API_KEY=your-xai-key-here          # Required for search tools
OPENROUTER_API_KEY=your-key-here       # Fallback option

# Run the application
python run.py
```

The application will start on `http://localhost:5000`

## Modes

### Create Mode

Generate a new Grokipedia article from any Wikipedia URL. The AI will:

1. Fetch the Wikipedia article as base context
2. Search the web and X for additional sources
3. Cross-reference and verify facts
4. Write a neutral, bias-free article
5. Compile references at the bottom

### Compare Mode

Compare existing Grokipedia and Wikipedia articles side-by-side with AI analysis of differences in framing, bias, and coverage.

### Edit Mode

Submit a Grokipedia article URL to receive AI-suggested improvements and corrections.

## Project Structure

```
Grokipedia/
├── app/                      # Flask application
│   ├── routes/              # HTTP endpoints
│   ├── services/            # AI & article logic
│   │   ├── article_fetcher.py    # Wikipedia & Grokipedia fetching
│   │   └── comparison_service.py # LLM prompts & API calls
│   └── utils/               # Helpers
├── static/                  # Frontend assets
│   ├── css/                # Modular CSS
│   └── js/                 # ES6 JavaScript modules
├── templates/              # HTML templates
├── grokipedia-sdk/        # Grokipedia SDK package
├── run.py                 # Entry point
└── requirements.txt       # Dependencies
```

## Environment Variables

```env
XAI_API_KEY=xai-...              # xAI API key (enables search tools)
OPENROUTER_API_KEY=sk-or-...     # OpenRouter key (fallback, no search)
```

## Tech Stack

- **Backend**: Flask (Python)
- **AI**: xAI Grok-4 via Responses API with web_search and x_search tools
- **Frontend**: Vanilla JavaScript (ES6 modules) + CSS
- **Data**: Grokipedia SDK for article fetching

## License

This project is provided as-is for educational and development purposes.
