# Duet

A self-editing terminal workspace where human and AI collaborate through a living Python program.

## What is Duet?

Duet is a minimal terminal-based code editor where the document you're editing *is* the program itself. Claude (via the Anthropic API) can read and modify the source code while you're editing it, enabling a unique form of human-AI pair programming.

The file has two sections separated by a marker line:
- **Kernel**: Python code above the marker. Edits here trigger automatic hot-reload.
- **Conversation**: Comments below the marker where Claude responds.

When you invoke the AI (Ctrl+F), Claude sees the entire source file and can make surgical edits to the code while explaining its changes in the conversation section.

## Demo

```
┌──────────────────────────────────────────────────────────────┐
│ def hello():                                                 │
│     print("Hello, World!")                                   │
│                                                              │
│ # === CONVERSATION ===                                       │
│ # User: Can you make this greet by name?                     │
│ #                                                            │
│ # I've updated hello() to accept a name parameter with a     │
│ # default value of "World" for backwards compatibility.      │
├──────────────────────────────────────────────────────────────┤
│ Ctrl+F: agent | Ctrl+R: reload | Ctrl+S: save | Ctrl+Q: quit │
└──────────────────────────────────────────────────────────────┘
```

## Requirements

- Python 3.8+
- Anthropic API key
- macOS or Linux (curses-based terminal UI)

## Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/niklasmu/duet.git
   cd duet
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install anthropic
   ```

4. **Set your Anthropic API key**
   ```bash
   export ANTHROPIC_API_KEY="your-api-key-here"
   ```

   Or add it permanently to your shell profile (`~/.zshrc` or `~/.bashrc`):
   ```bash
   echo 'export ANTHROPIC_API_KEY="your-api-key-here"' >> ~/.zshrc
   source ~/.zshrc
   ```

5. **Run Duet**
   ```bash
   python3 duet.py
   ```

## Usage

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+F` | Invoke Claude to read the file and respond |
| `Ctrl+S` | Save the file |
| `Ctrl+R` | Hot-reload the kernel (code section) |
| `Ctrl+Q` | Quit |
| Arrow keys | Navigate |
| Enter | New line (auto-prefixes `#` in conversation section) |

### How it works

1. **Edit code** above the `# === CONVERSATION ===` marker
2. **Write comments** below the marker to communicate with Claude
3. **Press Ctrl+F** to have Claude read and respond
4. Claude can make edits to any part of the file using find-and-replace
5. If Claude edits the kernel, the program **hot-reloads** automatically

### The Conversation Section

Everything below `# === CONVERSATION ===` is treated as conversation. When you press Enter in this section, new lines are automatically prefixed with `#` to keep them as comments.

Write your questions or requests as comments, then press Ctrl+F to get Claude's response.

## How Claude Edits Work

Claude uses a `respond` tool with two fields:
- **edits**: An array of `{old, new}` replacements to apply to the source
- **message**: Claude's response (added as comments)

Each edit must match the source exactly and be unique. The system validates all edits before applying them:
- Checks the marker line isn't broken
- Validates Python syntax
- Only applies edits if validation passes

## Configuration

You can modify these constants in the script:

```python
MODEL = "claude-sonnet-4-5-20250929"  # Claude model to use
MAX_TOKENS = 4096                      # Max response tokens
MARKER = "# === CONVERSATION ==="      # Section separator
```

## Limitations

- Terminal must support curses (most Unix terminals do)
- Windows is not supported (no curses)
- The entire source file is sent to Claude on each invocation

## License

MIT
