import openai
import os
import sys
import argparse
import json
import time
import re
import shutil
import textwrap
import threading
from datetime import datetime
from math import floor

# Version
VERSION = "0.9.5"

# wcwidth for proper unicode width calculation
try:
    from wcwidth import wcswidth
except ImportError:
    def wcswidth(text):
        return len(text) if text else 0

# ANSI escape codes for terminal colors
RESET = "\033[0m"
BOLD = "\033[1m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

# colors
CYAN = "\033[36m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
YELLOW = "\033[33m"
GRAY = "\033[90m"

ansi_escape = re.compile(r'\x1b\[[0-9;]*m')


def strip_ansi_codes(text):
    return ansi_escape.sub('', text)


def get_display_width(text):
    clean_text = strip_ansi_codes(text)
    return wcswidth(clean_text) or 0


def apply_markdown_inline(text, use_colors=True):
    if use_colors:
        text = re.sub(r'`([^`]+)`', YELLOW + r'\1' + RESET, text)
    else:
        text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\*\*(.+?)\*\*', BOLD + r'\1' + RESET, text)
    text = re.sub(r'(?<!\S)\*(?!\s)(.+?)(?<!\s)\*(?!\S)', ITALIC + r'\1' + RESET, text)
    return text


def clean_markdown_for_tables(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'(?<!\S)\*(?!\s)(.+?)(?<!\s)\*(?!\S)', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    return text


def format_header(line, use_colors=True):
    header_match = re.match(r'^(#{1,6})\s+(.*)$', line.strip())
    if not header_match:
        return line
    hashes, header_text = header_match.groups()
    level = len(hashes)
    header_text = apply_markdown_inline(header_text, use_colors)
    if use_colors:
        if level == 1:
            return BOLD + UNDERLINE + CYAN + header_text + RESET
        elif level == 2:
            return BOLD + BLUE + header_text + RESET
        elif level == 3:
            return BOLD + MAGENTA + header_text + RESET
        else:
            return BOLD + header_text + RESET
    else:
        if level == 1:
            return BOLD + UNDERLINE + header_text + RESET
        else:
            return BOLD + header_text + RESET


def format_list_item(line, terminal_width, use_colors=True):
    ordered_match = re.match(r'^(\s*\d+\.\s+)(.*)$', line)
    if ordered_match:
        indent, content = ordered_match.groups()
        content = apply_markdown_inline(content, use_colors)
        return textwrap.fill(content, width=terminal_width,
                             initial_indent=indent,
                             subsequent_indent=' ' * len(indent),
                             replace_whitespace=False)
    bullet_match = re.match(r'^(\s*[\*\-]\s+)(.*)$', line)
    if bullet_match:
        indent, content = bullet_match.groups()
        content = apply_markdown_inline(content, use_colors)
        return textwrap.fill(content, width=terminal_width,
                             initial_indent=indent,
                             subsequent_indent=' ' * len(indent),
                             replace_whitespace=False)
    return line


def looks_like_table_row(line):
    line = line.rstrip()
    return line.startswith('|') and line.count('|') >= 2


def is_table_separator(line):
    cells = [cell.strip() for cell in line.strip().split('|')[1:-1]]
    if not cells:
        return False
    return all(re.fullmatch(r':?-{3,}:?', cell) for cell in cells)


def extract_table_block(lines, start_index):
    i = start_index
    table_lines = []
    while i < len(lines) and looks_like_table_row(lines[i]):
        table_lines.append(lines[i].rstrip())
        i += 1
    return i, table_lines


def parse_markdown_table(table_lines):
    rows = []
    for idx, line in enumerate(table_lines):
        if idx == 1 and is_table_separator(line):
            continue
        cells = [cell.strip() for cell in line.strip().split('|')[1:-1]]
        rows.append(cells)
    if rows:
        max_cols = max(len(row) for row in rows)
        for row in rows:
            while len(row) < max_cols:
                row.append('')
    return rows, max_cols if rows else 0


def calculate_column_widths(rows, max_width, cell_padding=1, margin=1):
    if not rows:
        return []
    num_cols = len(rows[0])
    border_space = (num_cols + 1)
    padding_space = 2 * cell_padding * num_cols
    available_width = max_width - border_space - padding_space - margin
    if available_width < num_cols * 3:
        return [max(1, available_width // num_cols)] * num_cols
    natural_widths = []
    for col in range(num_cols):
        min_width = 3
        for row in rows:
            if col < len(row):
                min_width = max(min_width, get_display_width(row[col]))
        natural_widths.append(min_width)
    if sum(natural_widths) <= available_width:
        return natural_widths
    avg_width = max(1, floor(available_width / num_cols))
    min_col_width = max(10, min(24, avg_width))
    widths = [min(natural_widths[i], avg_width) for i in range(num_cols)]
    total_width = sum(widths)
    if total_width > available_width:
        excess = total_width - available_width
        sorted_cols = sorted(range(num_cols), key=lambda i: widths[i] - min_col_width, reverse=True)
        while excess > 0 and any(widths[i] > min_col_width for i in sorted_cols):
            for col_idx in sorted_cols:
                if widths[col_idx] > min_col_width and excess > 0:
                    widths[col_idx] -= 1
                    excess -= 1
    remaining = available_width - sum(widths)
    if remaining > 0:
        needed = [max(0, natural_widths[i] - widths[i]) for i in range(num_cols)]
        while remaining > 0 and sum(needed) > 0:
            for col_idx in sorted(range(num_cols), key=lambda i: needed[i], reverse=True):
                if needed[col_idx] > 0 and remaining > 0:
                    widths[col_idx] += 1
                    needed[col_idx] -= 1
                    remaining -= 1
    return [max(min_col_width, w) for w in widths]


def wrap_cell_content(content, max_width):
    if max_width <= 0:
        return [content]
    wrapped_lines = []
    for paragraph in str(content).splitlines() or ['']:
        lines = textwrap.wrap(paragraph, width=max_width,
                              replace_whitespace=False,
                              break_long_words=False,
                              break_on_hyphens=False)
        final_lines = []
        for line in (lines or ['']):
            if get_display_width(line) <= max_width:
                final_lines.append(line)
            else:
                current = ''
                for char in line:
                    if get_display_width(current + char) > max_width:
                        final_lines.append(current)
                        current = char
                    else:
                        current += char
                if current:
                    final_lines.append(current)
        wrapped_lines.extend(final_lines or [''])
    return wrapped_lines


TABLE_STYLES = {
    'ascii': {
        'horizontal': '-', 'vertical': '|',
        'top_left': '+', 'top_right': '+',
        'bottom_left': '+', 'bottom_right': '+',
        'top_join': '+', 'bottom_join': '+',
        'left_join': '+', 'right_join': '+',
        'cross': '+'
    },
    'box': {
        'horizontal': '═', 'vertical': '║',
        'top_left': '╔', 'top_right': '╗',
        'bottom_left': '╚', 'bottom_right': '╝',
        'top_join': '╦', 'bottom_join': '╩',
        'left_join': '╠', 'right_join': '╣',
        'cross': '╬'
    }
}


def render_table(rows, terminal_width, cell_padding=1, border_style='box'):
    clean_rows = []
    for row in rows:
        clean_row = [clean_markdown_for_tables(cell) for cell in row]
        clean_rows.append(clean_row)
    col_widths = calculate_column_widths(clean_rows, terminal_width, cell_padding)
    if not col_widths:
        return ''
    style = TABLE_STYLES.get(border_style, TABLE_STYLES['ascii'])

    def make_border_line(left_char, join_char, right_char):
        segments = [style['horizontal'] * (w + 2 * cell_padding) for w in col_widths]
        return left_char + join_char.join(segments) + right_char

    top_border = make_border_line(style['top_left'], style['top_join'], style['top_right'])
    middle_border = make_border_line(style['left_join'], style['cross'], style['right_join'])
    bottom_border = make_border_line(style['bottom_left'], style['bottom_join'], style['bottom_right'])
    result = [top_border]
    for row_idx, row in enumerate(clean_rows):
        wrapped_cells = []
        for col_idx, cell in enumerate(row):
            wrapped_cells.append(wrap_cell_content(cell, col_widths[col_idx]))
        max_lines = max(len(cell_lines) for cell_lines in wrapped_cells) if wrapped_cells else 1
        for line_idx in range(max_lines):
            line_parts = []
            for col_idx, cell_lines in enumerate(wrapped_cells):
                if line_idx < len(cell_lines):
                    cell_text = cell_lines[line_idx]
                else:
                    cell_text = ''
                text_width = get_display_width(cell_text)
                padding_needed = max(0, col_widths[col_idx] - text_width)
                left_pad = ' ' * cell_padding
                right_pad = ' ' * (cell_padding + padding_needed)
                line_parts.append(left_pad + cell_text + right_pad)
            result.append(style['vertical'] + style['vertical'].join(line_parts) + style['vertical'])
        if row_idx < len(clean_rows) - 1:
            result.append(middle_border)
        else:
            result.append(bottom_border)
    return '\n'.join(result)


def format_markdown_for_terminal(text, terminal_width=None, colors=True, table_style='box', margin=1):
    if terminal_width is None:
        term_size = shutil.get_terminal_size(fallback=(100, 24))
        terminal_width = max(72, min(160, term_size.columns - 2))
    text = text.replace('\\n', '\n')
    text = re.sub(r'(?m)^\s*---\s*$', '-' * (terminal_width - margin), text)
    lines = [line.rstrip() for line in text.splitlines()]
    normalized = []
    was_blank = False
    for line in lines:
        if line.strip() == '':
            if not was_blank:
                normalized.append('')
            was_blank = True
        else:
            normalized.append(line)
            was_blank = False
    output = []
    i = 0
    while i < len(normalized):
        line = normalized[i]
        stripped = line.strip()
        if looks_like_table_row(line):
            end_idx, table_block = extract_table_block(normalized, i)
            table_rows, _ = parse_markdown_table(table_block)
            if table_rows:
                formatted_table = render_table(table_rows,
                                               terminal_width - margin,
                                               cell_padding=1,
                                               border_style=table_style)
                output.append(formatted_table)
            i = end_idx
            continue
        if re.match(r'^#{1,6}\s+', stripped):
            output.append(format_header(line, colors))
            i += 1
            continue
        if stripped == '-' * len(stripped) and len(stripped) >= terminal_width - 4:
            rule_line = '-' * (terminal_width - margin)
            if colors:
                rule_line = GRAY + rule_line + RESET
            output.append(rule_line)
            i += 1
            continue
        if re.match(r'^\s*\d+\.\s+', line) or re.match(r'^\s*[\*\-]\s+', line):
            output.append(format_list_item(line, terminal_width - margin, colors))
            i += 1
            continue
        if stripped == '':
            output.append('')
            i += 1
            continue
        formatted = apply_markdown_inline(line, colors)
        wrapped = textwrap.fill(formatted, width=terminal_width - margin, replace_whitespace=False)
        output.append(wrapped)
        i += 1
    return '\n'.join(output)


class LoadingSpinner:
    def __init__(self, message="Processing"):
        self.spinner_chars = "|/-\\"
        self.message = message
        self.spinning = False
        self.thread = None
        self.position = 0

    def _spin(self):
        while self.spinning:
            char = self.spinner_chars[self.position % len(self.spinner_chars)]
            print(f"\r{self.message}{char}", end="", flush=True)
            self.position += 1
            time.sleep(0.1)

    def start(self):
        if not self.spinning:
            self.spinning = True
            self.thread = threading.Thread(target=self._spin)
            self.thread.daemon = True
            self.thread.start()

    def stop(self):
        if self.spinning:
            self.spinning = False
            if self.thread:
                self.thread.join(timeout=0.2)
            print(f"\r{' ' * (len(self.message) + 10)}\r", end="", flush=True)


class AITermCLI:
    def __init__(self, system_prompt=None, beep_enabled=True, logging_enabled=False, debug_mode=False,
                 retro_mode=False, stealth_mode=False):
        self.openai_client = None
        self.messages = []
        self.beep_enabled = beep_enabled
        self.logging_enabled = logging_enabled
        self.debug_mode = debug_mode
        self.retro_mode = retro_mode
        self.stealth_mode = stealth_mode
        self.session_log = None
        self.config_path = "AITermCLI_config.json"
        self.settings = {}
        self.colors_enabled = True
        self.table_border_style = "box"
        self._debug_log("Initializing AITermCLI...")
        self._load_configuration()
        if system_prompt:
            self.system_prompt = system_prompt
        else:
            self.system_prompt = self.settings.get("system_context", "")
        self._debug_log("Setting up OpenAI client...")
        if not self._configure_client():
            print("Failed to configure client. Exiting.")
            sys.exit(1)
        if self.logging_enabled:
            self._debug_log("Initializing session logging...")
            self._setup_session_log()
        self._debug_log("AITermCLI initialization complete")

    def _debug_log(self, msg):
        if self.debug_mode:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[DEBUG {timestamp}] {msg}")

    def _load_configuration(self):
        try:
            self._debug_log(f"Loading config from: {self.config_path}")
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
                self._debug_log("Config loaded successfully")
            else:
                self.settings = {
                    "api_url": "",
                    "api_key": "",
                    "model": "",
                    "provider": "",
                    "system_context": ""
                }
                self._debug_log("Created default config")
                self._save_configuration()
        except Exception as e:
            self._debug_log(f"Config load error: {e}")
            print(f"Error loading configuration: {e}")
            self.settings = {
                "api_url": "",
                "api_key": "",
                "model": "",
                "provider": "",
                "system_context": "You are an intelligent and helpful assistant. Respond concisely and accurately.\nAlways Always use markdown format for responses, avoid using ``` and the language name if it is code, and do not use emojis."
            }

    def _save_configuration(self):
        try:
            self._debug_log("Saving configuration...")
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            self._debug_log("Config saved")
        except Exception as e:
            self._debug_log(f"Config save error: {e}")
            print(f"Error saving configuration: {e}")

    def _request_user_config(self):
        self._debug_log("Starting interactive configuration")
        print("\n=== AI TERMINAL SETUP ===")
        print("Choose your AI provider:")
        print("1. OpenAI (https://api.openai.com)")
        print("2. Claude/Anthropic (https://api.anthropic.com)")
        print("3. DeepSeek (https://api.deepseek.com)")
        print("4. OpenRouter (https://openrouter.ai)")
        print("5. Google Gemini (https://generativelanguage.googleapis.com)")
        print("6. Custom API endpoint")
        while True:
            selection = input("Select provider (1-6): ").strip()
            if selection == "1":
                self.settings["api_url"] = "https://api.openai.com/v1"
                self.settings["provider"] = "OpenAI"
                break
            elif selection == "2":
                self.settings["api_url"] = "https://api.anthropic.com/v1"
                self.settings["provider"] = "Anthropic"
                break
            elif selection == "3":
                self.settings["api_url"] = "https://api.deepseek.com"
                self.settings["provider"] = "DeepSeek"
                break
            elif selection == "4":
                self.settings["api_url"] = "https://openrouter.ai/api/v1"
                self.settings["provider"] = "OpenRouter"
                break
            elif selection == "5":
                self.settings["api_url"] = "https://generativelanguage.googleapis.com/v1beta/openai"
                self.settings["provider"] = "Google Gemini"
                break
            elif selection == "6":
                custom_url = input("Enter custom API URL: ").strip()
                if custom_url:
                    self.settings["api_url"] = custom_url
                    self.settings["provider"] = "Custom"
                    break
            print("Invalid selection. Please choose 1-6.")
        while True:
            api_key = input(f"Enter your {self.settings['provider']} API key: ").strip()
            if api_key:
                self.settings["api_key"] = api_key
                break
            print("API key is required.")
        print(f"\nWould you like to set a custom system prompt?")
        print("This controls how the AI behaves and responds.")
        while True:
            want_prompt = input("Set custom system prompt? (y/n): ").strip().lower()
            if want_prompt in ['y', 'yes']:
                while True:
                    prompt = input("Enter system prompt: ").strip()
                    if prompt:
                        self.settings["system_context"] = prompt
                        print("System prompt configured!")
                        break
                    print("System prompt cannot be empty.")
                break
            elif want_prompt in ['n', 'no']:
                self.settings[
                    "system_context"] = "You are an intelligent and helpful assistant. Respond concisely and accurately.\nAlways Always use markdown format for responses, avoid using ``` and the language name if it is code, and do not use emojis."
                print("Default system prompt set.")
                break
            else:
                print("Please enter 'y' or 'n'")
        self._save_configuration()

    def _configure_client(self):
        if not self.settings.get("api_url") or not self.settings.get("api_key"):
            self._debug_log("Missing config, requesting from user")
            self._request_user_config()
        try:
            self._debug_log(f"Creating client for: {self.settings['api_url']}")
            start = time.time()
            self.openai_client = openai.OpenAI(
                api_key=self.settings["api_key"],
                base_url=self.settings["api_url"],
                timeout=30.0
            )
            elapsed = time.time() - start
            self._debug_log(f"Client created in {elapsed:.2f}s")
            if not self.system_prompt:
                self.system_prompt = self.settings.get("system_context", "")
            if not self.settings.get("model") or not self._validate_model():
                if not self._setup_model_selection():
                    return False
            return True
        except Exception as e:
            self._debug_log(f"Client setup error: {e}")
            print(f"Error setting up client: {e}")
            return False

    def _validate_model(self):
        self._debug_log(f"Validating model: {self.settings.get('model')}")
        try:
            start = time.time()
            response = self.openai_client.chat.completions.create(
                model=self.settings["model"],
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
                temperature=0,
                timeout=10.0
            )
            elapsed = time.time() - start
            self._debug_log(f"Model validated in {elapsed:.2f}s")
            return True
        except Exception as e:
            self._debug_log(f"Model validation failed: {e}")
            if "model" in str(e).lower() or "not found" in str(e).lower():
                return False
            return True

    def _get_available_models(self):
        self._debug_log("Fetching available models...")
        try:
            start = time.time()
            models_response = self.openai_client.models.list()
            available = []
            for model in models_response.data:
                model_name = model.id.lower()
                if any(keyword in model_name for keyword in ['gpt', 'claude', 'chat', 'deepseek', 'llama', 'mistral']):
                    available.append(model.id)
            elapsed = time.time() - start
            self._debug_log(f"Retrieved {len(available)} models in {elapsed:.2f}s")
            return sorted(available)
        except Exception as e:
            self._debug_log(f"Model fetch error: {e}")
            print(f"Error fetching models: {e}")
            return []

    def _setup_model_selection(self):
        self._debug_log("Starting model selection")
        print(f"\nFetching available models from {self.settings['provider']}...")
        models = self._get_available_models()
        if not models:
            print("Could not retrieve model list. Please enter manually.")
            while True:
                manual_model = input("Enter model name: ").strip()
                if manual_model:
                    self.settings["model"] = manual_model
                    self._save_configuration()
                    return True
                print("Model name cannot be empty.")
        print(f"\nAvailable models for {self.settings['provider']}:")
        for idx, model in enumerate(models, 1):
            print(f"{idx}. {model}")
        while True:
            try:
                selection = input(f"\nSelect model (1-{len(models)}) or enter custom name: ").strip()
                if selection.isdigit():
                    choice_idx = int(selection)
                    if 1 <= choice_idx <= len(models):
                        chosen_model = models[choice_idx - 1]
                        self.settings["model"] = chosen_model
                        self._save_configuration()
                        print(f"Model selected: {chosen_model}")
                        return True
                    else:
                        print(f"Invalid selection. Choose 1-{len(models)}")
                        continue
                elif selection:
                    self.settings["model"] = selection
                    self._save_configuration()
                    print(f"Model set to: {selection}")
                    return True
                print("Please enter a valid selection or model name.")
            except ValueError:
                print("Invalid input. Please try again.")

    def _setup_session_log(self):
        try:
            log_directory = "history_terminal_AI"
            if not os.path.exists(log_directory):
                os.makedirs(log_directory)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_name = f"session_{timestamp}.txt"
            self.session_log = os.path.join(log_directory, log_name)
            with open(self.session_log, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write("AI TERMINAL SESSION LOG\n")
                f.write(f"Provider: {self.settings.get('provider', 'Unknown')}\n")
                f.write(f"Model: {self.settings.get('model', 'Unknown')}\n")
                f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                context_preview = self.system_prompt[:100] + "..." if len(
                    self.system_prompt) > 100 else self.system_prompt
                f.write(f"System prompt: {context_preview}\n")
                f.write("=" * 60 + "\n\n")
            self._debug_log(f"Session log: {self.session_log}")
            print(f"Session logging enabled: {self.session_log}")
        except Exception as e:
            self._debug_log(f"Log setup error: {e}")
            print(f"Error setting up session log: {e}")
            self.logging_enabled = False

    def _write_to_log(self, role, content):
        if not self.logging_enabled or not self.session_log:
            return
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            role_label = "USER" if role == "user" else "ASSISTANT"
            with open(self.session_log, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {role_label}:\n")
                f.write(f"{content}\n")
                f.write("-" * 40 + "\n\n")
        except Exception as e:
            self._debug_log(f"Log write error: {e}")
            print(f"Error writing to log: {e}")

    def _log_command(self, command):
        if not self.logging_enabled or not self.session_log:
            return
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            with open(self.session_log, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] COMMAND: {command}\n")
                f.write("-" * 40 + "\n\n")
        except Exception as e:
            self._debug_log(f"Command log error: {e}")
            print(f"Error logging command: {e}")

    def _close_session_log(self):
        if not self.logging_enabled or not self.session_log:
            return
        try:
            with open(self.session_log, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 60 + "\n")
                f.write(f"SESSION ENDED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n")
        except Exception as e:
            self._debug_log(f"Log close error: {e}")
            print(f"Error closing session log: {e}")

    def clear_screen(self):
        if os.name == 'nt':
            os.system('cls')
        else:
            print("\033[2J\033[H", end="", flush=True)

    def _play_notification_sound(self):
        if not self.beep_enabled:
            return
        try:
            sound_locations = [
                "sounds/beep-02.wav",
                "./sounds/beep-02.wav",
                os.path.join(os.path.dirname(__file__), "sounds", "beep-02.wav"),
                os.path.join(os.getcwd(), "sounds", "beep-02.wav")
            ]
            sound_file = None
            for location in sound_locations:
                if os.path.exists(location):
                    sound_file = location
                    break
            if sound_file:
                if os.name == 'nt':
                    import winsound
                    winsound.PlaySound(sound_file, winsound.SND_FILENAME)
                else:
                    audio_commands = [
                        f'aplay "{sound_file}" >/dev/null 2>&1',
                        f'paplay "{sound_file}" >/dev/null 2>&1',
                        f'afplay "{sound_file}" >/dev/null 2>&1',
                        f'play "{sound_file}" >/dev/null 2>&1',
                    ]
                    for cmd in audio_commands:
                        if os.system(cmd) == 0:
                            return
            else:
                if os.name == 'nt':
                    import winsound
                    winsound.Beep(800, 200)
                else:
                    print('\a', end='', flush=True)
        except Exception:
            print(' *BEEP*', end='', flush=True)

    def send_chat_message(self, user_message):
        try:
            self._debug_log(f"Processing message: {user_message[:50]}...")
            start_time = time.time()
            self._write_to_log("user", user_message)
            self.messages.append({"role": "user", "content": user_message})
            full_messages = [{"role": "system", "content": self.system_prompt}] + self.messages
            self._debug_log("Sending API request...")
            spinner = LoadingSpinner("")
            spinner.start()
            try:
                api_start = time.time()
                response = self.openai_client.chat.completions.create(
                    model=self.settings["model"],
                    messages=full_messages,
                    max_tokens=2000,
                    temperature=0.7,
                    stream=False,
                    timeout=60.0
                )
                api_elapsed = time.time() - api_start
                self._debug_log(f"API response in {api_elapsed:.2f}s")
            finally:
                spinner.stop()
            if not response.choices or len(response.choices) == 0:
                error_text = f"Error: No response from {self.settings['provider']}"
                self._debug_log(error_text)
                self._write_to_log("system", error_text)
                return error_text
            ai_response = response.choices[0].message.content
            if not ai_response or ai_response.strip() == "":
                self.messages.pop()
                error_text = f"Error: {self.settings['provider']} returned empty response. Try again."
                self._debug_log(error_text)
                self._write_to_log("system", error_text)
                return error_text
            self.messages.append({"role": "assistant", "content": ai_response})
            self._write_to_log("assistant", ai_response)
            total_elapsed = time.time() - start_time
            self._debug_log(f"Total processing time: {total_elapsed:.2f}s")
            self._play_notification_sound()
            return ai_response
        except Exception as e:
            if self.messages and self.messages[-1]["role"] == "user":
                self.messages.pop()
            error_text = f"Error: {str(e)}"
            self._debug_log(f"Message send error: {e}")
            self._write_to_log("system", error_text)
            return error_text

    def clear_conversation_history(self, silent=False):
        self._debug_log("Clearing conversation history")
        self.messages = []
        if not silent:
            print("")

    def detect_code_content(self, text):
        if not text:
            return False
        if '```' in text:
            return False
        if "SOURCE CODE" in text.upper():
            return True
        code_patterns = [
            'PROGRAM-ID', 'IDENTIFICATION DIVISION', 'PROCEDURE DIVISION',
            'def ', 'class ', 'import ', 'function', 'var ', 'let ', 'const ',
            '#!/', '<?php', '<html', '<script', 'SELECT ', 'INSERT ', 'UPDATE ',
            '#include', '#define', 'public class', 'private ', 'protected ',
            'if __name__', 'from ', 'import', 'namespace', 'using System',
            'IDENTIFICATION DIVISION', 'ENVIRONMENT DIVISION', 'DATA DIVISION',
            'PROCEDURE DIVISION', 'WORKING-STORAGE SECTION', 'DISPLAY ',
            'STOP RUN', 'MOVE ', 'ACCEPT ', 'COMPUTE ',
            'BEGIN', 'END;', '#!/bin/', 'DOCTYPE html', 'console.log',
            'print(', 'printf(', 'echo ', 'cat ', 'grep ', 'awk ',
        ]
        text_upper = text.upper()
        pattern_count = 0
        for pattern in code_patterns:
            if pattern.upper() in text_upper:
                pattern_count += 1
        if pattern_count >= 3:
            return True
        code_symbols = ['{', '}', '[', ']', ';', '->', '=>', '==', '!=', '<=', '>=', '&&', '||']
        symbol_count = sum(text.count(symbol) for symbol in code_symbols)
        if symbol_count > len(text) * 0.05:
            return True
        lines = text.split('\n')
        indented_lines = sum(1 for line in lines if line.startswith('    ') or line.startswith('\t'))
        if len(lines) > 5 and indented_lines > len(lines) * 0.5:
            return True
        return False

    def format_ai_response(self, response_text):
        if not response_text:
            return ""
        try:
            if self.detect_code_content(response_text):
                return response_text
            return format_markdown_for_terminal(
                text=response_text,
                terminal_width=None,
                colors=self.colors_enabled,
                table_style=self.table_border_style,
                margin=1
            )
        except Exception as e:
            self._debug_log(f"Response formatting error: {e}")
            return str(response_text) if response_text else ""

    def show_conversation_history(self):
        if not self.messages:
            print("No conversation history")
            return
        print("\n--- CONVERSATION HISTORY ---")
        for idx, msg in enumerate(self.messages, 1):
            role_label = "User" if msg["role"] == "user" else "AI"
            content = msg['content']
            if len(content) > 100:
                content = content[:100] + "..."
            print(f"{idx}. {role_label}: {content}")
        print("--- END HISTORY ---")

    def show_system_prompt(self):
        print("\n--- SYSTEM PROMPT ---")
        print(self.system_prompt)
        print("--- END PROMPT ---")

    def show_current_config(self):
        print("\n--- CONFIGURATION ---")
        print(f"Provider: {self.settings.get('provider', 'Not configured')}")
        print(f"API URL: {self.settings.get('api_url', 'Not configured')}")
        print(f"Model: {self.settings.get('model', 'Not configured')}")
        masked_key = '*' * len(self.settings.get('api_key', '')) if self.settings.get('api_key') else 'Not set'
        print(f"API Key: {masked_key}")
        print(f"Debug mode: {'On' if self.debug_mode else 'Off'}")
        print(f"Retro mode: {'On' if self.retro_mode else 'Off'}")
        print(f"Stealth mode: {'On' if self.stealth_mode else 'Off'}")
        print(f"Colors: {'On' if self.colors_enabled else 'Off'}")
        print(f"Table style: {self.table_border_style}")
        print("--- END CONFIG ---")

    def modify_system_prompt(self):
        print("\n--- MODIFY SYSTEM PROMPT ---")
        print("Current prompt:")
        print(self.system_prompt)
        print("\nEnter new prompt (or press Enter to keep current):")
        new_prompt = input("> ")
        if new_prompt.strip():
            self.system_prompt = new_prompt.strip()
            self.settings["system_context"] = self.system_prompt
            self._save_configuration()
            print("System prompt updated and saved")
        else:
            print("System prompt unchanged")

    def reset_system_prompt(self):
        print("\n--- RESET SYSTEM PROMPT ---")
        print("Enter new system prompt:")
        while True:
            new_prompt = input("System prompt: ").strip()
            if new_prompt:
                self.system_prompt = new_prompt
                self.settings["system_context"] = self.system_prompt
                self._save_configuration()
                print("System prompt reset and saved")
                break
            print("System prompt cannot be empty.")

    def reconfigure_api(self):
        print("\n--- API RECONFIGURATION ---")
        current_prompt = self.settings.get("system_context",
                                           "You are an intelligent and helpful assistant. Respond concisely and accurately.\nAlways Always use markdown format for responses, avoid using ``` and the language name if it is code, and do not use emojis.")
        self.settings = {
            "api_url": "",
            "api_key": "",
            "model": "",
            "provider": "",
            "system_context": current_prompt
        }
        self._request_user_config()
        if self._configure_client():
            print("API reconfiguration successful!")
        else:
            print("API reconfiguration failed!")

    def change_ai_provider(self):
        print("\n--- CHANGE AI PROVIDER ---")
        print("WARNING: This will reset your current AI configuration.")
        print("Your system prompt will be preserved.")
        while True:
            confirm = input("Do you want to continue? (y/n): ").strip().lower()
            if confirm in ['y', 'yes']:
                current_prompt = self.settings.get("system_context",
                                                   "You are an intelligent and helpful assistant. Respond concisely and accurately.\nAlways Always use markdown format for responses, avoid using ``` and the language name if it is code, and do not use emojis.")
                self.settings = {
                    "api_url": "",
                    "api_key": "",
                    "model": "",
                    "provider": "",
                    "system_context": current_prompt
                }
                self._save_configuration()
                self._request_user_config()
                if self._configure_client():
                    self.system_prompt = self.settings.get("system_context", current_prompt)
                    print("\nAI provider changed successfully!")
                    print("Please restart the conversation or use /clear to start fresh.")
                else:
                    print("\nAI provider change failed!")
                break
            elif confirm in ['n', 'no']:
                print("AI provider change cancelled.")
                break
            else:
                print("Please enter 'y' or 'n'")

    def toggle_colors(self):
        self.colors_enabled = not self.colors_enabled
        status = "enabled" if self.colors_enabled else "disabled"
        print(f"Color output {status}")

    def cycle_table_style(self):
        self.table_border_style = "ascii" if self.table_border_style == "box" else "box"
        print(f"Table style: {self.table_border_style}")

    def toggle_retro_mode(self):
        self.retro_mode = not self.retro_mode
        status = "enabled" if self.retro_mode else "disabled"
        print(f"Retro answer mode {status}")
        if self.retro_mode:
            print("After each AI response, press Enter to continue and start a new conversation.")

    def show_version(self):
        print(f"\nAITermCLI version {VERSION}")
        print("Created by Fosilinx")
        print("AI Terminal - Chat with various AI providers")

    def display_help(self):
        print("\n--- AVAILABLE COMMANDS ---")
        print("/exit, quit, exit - Exit the program")
        print("/clear - Clear conversation history")
        print("/history - Show conversation history")
        print("/raw - Show last response without formatting")
        print("/context - Show current system prompt")
        print("/setcontext - Modify system prompt")
        print("/resetcontext - Reset system prompt")
        print("/config - Show current configuration")
        print("/reconfig - Reconfigure API settings")
        print("/changeai - Change AI provider (resets configuration)")
        print("/beep - Toggle notification beep")
        print("/beepoff - Disable notification beep")
        print("/testbeep - Test beep functionality")
        print("/testapi - Test API connection")
        print("/colors - Toggle color output")
        print("/tablestyle - Switch table border style")
        print("/models - List available models")
        print("/debug - Toggle debug mode")
        print("/retro - Toggle retro answer mode")
        print("/version - Show version information")
        print("/help - Show this help")
        print("--- END COMMANDS ---")

    def toggle_beep(self):
        self.beep_enabled = not self.beep_enabled
        status = "enabled" if self.beep_enabled else "disabled"
        print(f"Notification beep {status}")

    def toggle_debug_mode(self):
        self.debug_mode = not self.debug_mode
        status = "enabled" if self.debug_mode else "disabled"
        print(f"Debug mode {status}")

    def show_last_raw_response(self):
        if not self.messages:
            print("No conversation history")
            return
        for msg in reversed(self.messages):
            if msg["role"] == "assistant":
                print("\n--- RAW RESPONSE ---")
                print(msg["content"])
                print("--- END RAW ---")
                return
        print("No AI responses found")

    def list_available_models(self):
        print(f"\nFetching models from {self.settings['provider']}...")
        models = self._get_available_models()
        if models:
            print(f"\nAvailable models from {self.settings['provider']}:")
            for idx, model in enumerate(models, 1):
                current_indicator = " (current)" if model == self.settings.get('model') else ""
                print(f"{idx}. {model}{current_indicator}")
        else:
            print("Could not retrieve model list.")

    def test_api_connection(self):
        self._debug_log("Testing API connection...")
        print(f"Testing connection to {self.settings['provider']}...")
        spinner = LoadingSpinner("Connecting")
        spinner.start()
        try:
            start_time = time.time()
            test_response = self.openai_client.chat.completions.create(
                model=self.settings["model"],
                messages=[{"role": "user", "content": "Say only 'OK'"}],
                max_tokens=10,
                temperature=0,
                timeout=15.0
            )
            elapsed = time.time() - start_time
            self._debug_log(f"Connection test completed in {elapsed:.2f}s")
        except Exception as e:
            self._debug_log(f"Connection test failed: {e}")
            print(f"Connection failed: {e}")
            return
        finally:
            spinner.stop()
        if test_response.choices and len(test_response.choices) > 0:
            result = test_response.choices[0].message.content
            if result and result.strip():
                print(f"Connection successful. Response: {result.strip()}")
            else:
                print("Connection established but got empty response")
        else:
            print(f"Error: No response from {self.settings['provider']}")

    def test_beep_functionality(self):
        print("Testing notification beep...")
        self._play_notification_sound()
        print("Beep test complete")

    def run_chat_loop(self):
        provider = self.settings.get("provider", "Unknown")
        model = self.settings.get("model", "Unknown")

        if not self.stealth_mode:
            print(BLUE)
            print(" ███         █████████   █████ ███████████                                                 █████████  █████       █████")
            print("░░░███      ███░░░░░███ ░░███ ░█░░░███░░░█                                                ███░░░░░███░░███       ░░███ ")
            print("  ░░░███   ░███    ░███  ░███ ░   ░███  ░   ██████  ████████  █████████████              ███     ░░░  ░███        ░███ ")
            print("    ░░░███ ░███████████  ░███     ░███     ███░░███░░███░░███░░███░░███░░███  ██████████░███          ░███        ░███ ")
            print("     ███░  ░███░░░░░███  ░███     ░███    ░███████  ░███ ░░░  ░███ ░███ ░███ ░░░░░░░░░░ ░███          ░███        ░███ ")
            print("   ███░    ░███    ░███  ░███     ░███    ░███░░░   ░███      ░███ ░███ ░███            ░░███     ███ ░███      █ ░███ ")
            print(" ███░      █████   █████ █████    █████   ░░██████  █████     █████░███ █████            ░░█████████  ███████████ █████")
            print("░░░       ░░░░░   ░░░░░ ░░░░░    ░░░░░     ░░░░░░  ░░░░░     ░░░░░ ░░░ ░░░░░              ░░░░░░░░░  ░░░░░░░░░░░ ░░░░░ ")
            print(RESET)
            banner_lines = [
                f"AITermCLI v{VERSION} by Fosilinx",
                f"Provider: {provider}",
                f"Model: {model}",
                f"Beep: {'On' if self.beep_enabled else 'Off'}",
                f"Colors: {'On' if self.colors_enabled else 'Off'}",
                f"Tables: {self.table_border_style.title()}",
                f"Retro Mode: {'On' if self.retro_mode else 'Off'}"
            ]
            max_width = max(len(line) for line in banner_lines) + 2
            top_border = "╔" + "═" * max_width + "╗"
            bottom_border = "╚" + "═" * max_width + "╝"
            print(top_border)
            for line in banner_lines:
                print("║ " + line.ljust(max_width - 1) + "║")
            print(bottom_border)
        else:
            print(f"AITermCLI v{VERSION} - Stealth Mode")

        self._debug_log("Starting chat loop...")
        while True:
            try:
                print("\033[?25h\033[5 q", end="", flush=True)
                user_input = input("\n> ").strip()
                if user_input.lower() in ['/exit', 'quit', 'exit']:
                    self._log_command(user_input)
                    break
                elif user_input.lower() == '/clear':
                    self.clear_conversation_history(silent=True)
                    self.clear_screen()
                    continue
                elif user_input.lower() == '/history':
                    self.show_conversation_history()
                    continue
                elif user_input.lower() == '/raw':
                    self._log_command("/raw")
                    self.show_last_raw_response()
                    continue
                elif user_input.lower() == '/context':
                    self.show_system_prompt()
                    continue
                elif user_input.lower() == '/setcontext':
                    self.modify_system_prompt()
                    continue
                elif user_input.lower() == '/resetcontext':
                    self._log_command("/resetcontext")
                    self.reset_system_prompt()
                    continue
                elif user_input.lower() == '/config':
                    self.show_current_config()
                    continue
                elif user_input.lower() == '/reconfig':
                    self._log_command("/reconfig")
                    self.reconfigure_api()
                    continue
                elif user_input.lower() == '/changeai':
                    self._log_command("/changeai")
                    self.change_ai_provider()
                    continue
                elif user_input.lower() == '/beep':
                    self._log_command("/beep")
                    self.toggle_beep()
                    continue
                elif user_input.lower() == '/beepoff':
                    self._log_command("/beepoff")
                    if self.beep_enabled:
                        self.beep_enabled = False
                        print("Notification beep disabled")
                    else:
                        print("Notification beep already disabled")
                    continue
                elif user_input.lower() == '/testbeep':
                    self._log_command("/testbeep")
                    self.test_beep_functionality()
                    continue
                elif user_input.lower() == '/testapi':
                    self._log_command("/testapi")
                    self.test_api_connection()
                    continue
                elif user_input.lower() == '/colors':
                    self._log_command("/colors")
                    self.toggle_colors()
                    continue
                elif user_input.lower() == '/tablestyle':
                    self._log_command("/tablestyle")
                    self.cycle_table_style()
                    continue
                elif user_input.lower() == '/models':
                    self._log_command("/models")
                    self.list_available_models()
                    continue
                elif user_input.lower() == '/debug':
                    self._log_command("/debug")
                    self.toggle_debug_mode()
                    continue
                elif user_input.lower() == '/retro':
                    self._log_command("/retro")
                    self.toggle_retro_mode()
                    continue
                elif user_input.lower() == '/version':
                    self._log_command("/version")
                    self.show_version()
                    continue
                elif user_input.lower() == '/help':
                    self._log_command("/help")
                    self.display_help()
                    continue
                elif user_input == '':
                    continue
                self._debug_log("Processing user message...")
                ai_response = self.send_chat_message(user_input)
                formatted_output = self.format_ai_response(ai_response)
                print(formatted_output)
                if self.retro_mode:
                    input("\nPress Enter to continue...")
                    self.clear_screen()
                    self.clear_conversation_history()
            except KeyboardInterrupt:
                self._debug_log("Keyboard interrupt received")
                self._log_command("KeyboardInterrupt")
                break
            except Exception as e:
                error_msg = f"Error: {e}"
                self._debug_log(f"Main loop error: {e}")
                print(error_msg)
                self._write_to_log("system", f"Main loop error: {e}")
        self._debug_log("Shutting down...")
        self._close_session_log()


def main():
    parser = argparse.ArgumentParser(description='AI Terminal - Chat with various AI providers')
    parser.add_argument('-c', '--context', type=str, help='System context/prompt for the AI')
    parser.add_argument('-cf', '--context-file', type=str, help='File containing system context')
    parser.add_argument('-nb', '--no-beep', action='store_true', help='Disable notification beep')
    parser.add_argument('-l', '--log', action='store_true', help='Enable session logging')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug output')
    parser.add_argument('-r', '--retro', action='store_true', help='Enable retro answer mode')
    parser.add_argument('-s', '--stealth', action='store_true', help='Enable stealth mode (hide banners)')
    parser.add_argument('-v', '--version', action='store_true', help='Show version and exit')
    args = parser.parse_args()

    if args.version:
        print(f"AITermCLI version {VERSION}")
        print("Created by Fosilinx")
        print("AI Terminal - Chat with various AI providers")
        sys.exit(0)

    context = None
    if args.context_file:
        try:
            with open(args.context_file, 'r', encoding='utf-8') as f:
                context = f.read().strip()
        except FileNotFoundError:
            print(f"Error: Context file '{args.context_file}' not found")
            sys.exit(1)
        except Exception as e:
            print(f"Error reading context file: {e}")
            sys.exit(1)
    elif args.context:
        context = args.context
    try:
        import openai
    except ImportError:
        print("Error: OpenAI library not installed")
        print("Install with: pip install openai")
        sys.exit(1)
    beep_enabled = not args.no_beep
    logging_enabled = args.log
    debug_enabled = args.debug
    retro_enabled = args.retro
    stealth_enabled = args.stealth

    # Stealth mode disables beep automatically
    if stealth_enabled:
        beep_enabled = False

    if debug_enabled:
        print("Debug mode enabled - detailed timing and process information will be shown")
    if retro_enabled:
        print("Retro answer mode enabled - press Enter after each response to continue")
    if stealth_enabled:
        print("Stealth mode enabled - banners and beep hidden")
    terminal = AITermCLI(context, beep_enabled, logging_enabled, debug_enabled, retro_enabled, stealth_enabled)
    terminal.run_chat_loop()


if __name__ == "__main__":
    main()
