# >_AITerm

🖥️ AITerm - Terminal AI Chat for Old-School Hackers 💾

Remember when the best tools lived in the terminal? AITerm brings that magic back. A retro-styled terminal interface, powered by Python, that connects you with the most powerful AI models: OpenAI's GPT, Anthropic's Claude, DeepSeek, and any OpenAI-compatible API.

🕹️ For true command-line devotees - Those old-school developers who prefer vim over VS Code, think GUIs are for rookies, and know that real productivity happens where the cursor blinks.
⚡ No breaking your workflow. No annoying windows. Just you, your favorite terminal, and the power of AI one command away.
Because real developers never leave the terminal. 🤖

Vintage computing vibes meets cutting-edge AI ✨

## ✨ Features

### Version
**0.5 Stable Release**

### 🌐 Multi-Provider Support
- **OpenAI** (GPT-3.5, GPT-4, GPT-4o, o1, o3)
- **Anthropic Claude** (Claude-3, Claude-3.5, Claude Sonnet 4)
- **DeepSeek** (DeepSeek-Chat, DeepSeek-Coder, DeepSeek-V3)
- **Custom APIs** (Any OpenAI-compatible endpoint)

### 💫 Smart Terminal Experience
- **Interactive Setup** - First-run configuration wizard
- **Persistent Configuration** - Your settings are saved automatically
- **Session Logging** - Optional conversation history with timestamps
- **Audio Feedback** - Customizable notification sounds (with quick disable)
- **Smart Markdown Formatting** - Beautiful headers, lists, tables, and code blocks
- **Retro Mode** - Clean slate after each response for focused interactions
- **Table Support** - Clean markdown table rendering with multiple border styles
- **Color Toggle** - Enable/disable colored output on the fly

### ⚡ Developer-Friendly
- **Smart Code Detection** - Automatically detects and preserves code formatting
- **Context Management** - Set custom system prompts for specialized tasks
- **History Navigation** - Review and clear conversation history
- **Raw Output** - View unformatted responses when needed
- **Connection Testing** - Verify API connectivity and model availability
- **Debug Mode** - Detailed timing and process information

## 🚀 Quick Start

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/fosilinx/aiterm.git
   cd aiterm
   ```

2. **Install dependencies**
   ```bash
   pip install openai
   # Optional for better unicode support
   pip install wcwidth
   ```

3. **Run AITerm**
   ```bash
   python aiterm.py
   ```

### First Run Setup

On first launch, AITerm will guide you through configuration:

1. **Choose your AI provider**
   - Select from OpenAI, Anthropic, DeepSeek, or custom URL
   
2. **Enter your API key**
   - Your key is stored locally in `aiterm_config.json`
   
3. **Select a model**
   - Browse available models for your provider
   
4. **Optional: Set system context**
   - Define how the AI should behave

## 🎯 Usage

### Basic Chat
```bash
> Hello, can you help me debug this Python function?
```

### Available Commands

| Command | Description |
|---------|-------------|
| `/exit`, `quit`, `exit` | Exit the application |
| `/clear` | Clear screen and conversation history |
| `/history` | View conversation history |
| `/raw` | Show last unformatted response |
| `/context` | View current system prompt |
| `/setcontext` | Modify system prompt |
| `/resetcontext` | Reset system prompt |
| `/config` | View current configuration |
| `/reconfig` | Reconfigure API settings |
| `/beep` | Toggle notification beep |
| `/beepoff` | Disable notification beep |
| `/testbeep` | Test notification sound |
| `/testapi` | Test API connection |
| `/colors` | Toggle color output |
| `/tablestyle` | Switch table border style (box/ascii) |
| `/models` | List available models |
| `/debug` | Toggle debug mode |
| `/retro` | Toggle retro answer mode |
| `/help` | Show all commands |

### Advanced Usage

#### Custom System Context
```bash
python aiterm.py -c "You are a senior Python developer focused on clean, efficient code."
```

#### Context from File
```bash
python aiterm.py -cf system_prompt.txt
```

#### Enable Session Logging
```bash
python aiterm.py --log
```

#### Silent Mode (No Beeps)
```bash
python aiterm.py --no-beep
```

#### Retro Mode (Fresh Start After Each Response)
```bash
python aiterm.py --retro
```

#### Debug Mode
```bash
python aiterm.py --debug
```

## ⚙️ Configuration

AITerm stores configuration in `aiterm_config.json`:

```json
{
  "api_url": "https://api.openai.com/v1",
  "api_key": "your-api-key",
  "model": "gpt-4",
  "provider": "OpenAI",
  "system_context": "You are a helpful assistant."
}
```

### Session Logs

When logging is enabled, conversations are saved to `history_terminal_AI/session_YYYYMMDD_HHMMSS.txt` with:
- Session metadata (provider, model, timestamp)
- Complete conversation history
- Command history
- Timestamps for each interaction

## 🎨 Customization

### Custom Notification Sounds

Place your custom beep sound at `sounds/beep-02.wav` to override the default system beep.

### Table Styles

Switch between two beautiful table styles:
- **Box** (default): Elegant Unicode borders `╔═╗║╚╝`
- **ASCII**: Classic terminal style `+-+||`

Use `/tablestyle` to toggle between styles.

### Code Detection

AIterm automatically detects code content and preserves formatting for:
- Programming languages (Python, JavaScript, Java, C++, Go, Rust, etc.)
- COBOL and legacy languages
- SQL queries
- Shell scripts
- Markup languages (HTML, XML)
- Configuration files

Triple backticks (```) in responses are properly handled by the markdown formatter.

## 🛠️ Advanced Features

### Retro Mode
Perfect for presentations or teaching - each response is isolated:
1. Get AI response
2. Press Enter
3. Screen clears
4. Fresh conversation starts

### Multiple Model Testing
Easily switch between models to compare responses:
```bash
> /models          # List available models
> /reconfig        # Switch to different model
```

### Context Switching
Perfect for different types of tasks:
```bash
> /setcontext      # Change context for coding tasks
> /resetcontext    # Set up for writing tasks
```

### API Debugging
```bash
> /testapi         # Verify connection
> /config          # Check current settings
> /raw             # See unprocessed responses
> /debug           # Toggle detailed logging
```

## 📋 Requirements

- **Python 3.6+**
- **openai** library (`pip install openai`)
- **API key** from your chosen provider
- **wcwidth** (optional, for better unicode support)

### Optional Dependencies

For enhanced audio feedback:
- **Windows**: Built-in `winsound`
- **Linux**: `aplay`, `paplay`, or `play`
- **macOS**: `afplay`

## 🔧 Command-Line Arguments

```
usage: aiterm.py [-h] [-c CONTEXT] [-cf CONTEXT_FILE] [-nb] [-lo] [-d] [-r]

AI Terminal - Chat with various AI providers

optional arguments:
  -h, --help            show this help message and exit
  -c CONTEXT, --context CONTEXT
                        System context/prompt for the AI
  -cf CONTEXT_FILE, --context-file CONTEXT_FILE
                        File containing system context
  -nb, --no-beep        Disable notification beep
  -lo, --log            Enable session logging
  -d, --debug           Enable debug output
  -r, --retro           Enable retro answer mode
```

## 🤝 Contributing

We welcome contributions! Here are some ways you can help:

- 🐛 **Bug Reports** - Found an issue? Let us know!
- 💡 **Feature Requests** - Have an idea? We'd love to hear it!
- 🔧 **Pull Requests** - Code improvements and new features
- 📚 **Documentation** - Help improve our docs

### Development Setup

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with the [OpenAI Python SDK](https://github.com/openai/openai-python)
- Inspired by terminal-based AI tools and developer workflows
- Thanks to all AI providers for their APIs

## 📞 Support

- 🐛 **Issues**: [GitHub Issues](https://github.com/fosilinx/aiterm/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/fosilinx/aiterm/discussions)

## ☕ Support the Project

If AITerm has been helpful in your development workflow, consider buying me a coffee:

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/fosilinx)

Your support helps maintain and improve AITerm, add new AI provider integrations, and keep the project actively developed.

---

<p align="center">
  <b>Made with ❤️ for old school computer users who live in the terminal</b>
</p>