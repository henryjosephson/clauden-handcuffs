# Clauden Handcuffs

It's a nannybot that holds you accountable! It takes regular screenshots, asks the vision LLM of your choice whether the content on your screen is consistent with your goal. If it isn't, Claude will make you get back on task!

## Setup

You should probably use a virtual environment. I like [uv](https://astral.sh/uv), so I run

```bash
uv venv                             # creates venv
source .venv/bin/activate           # activates the venv
uv pip install -r requirements.txt  # installs reqs
```

In addition to the requirements in `requirements.txt`, you also need to have TKinter installed. It wasn't included with my [homebrew](https://brew.sh) version of python 3.13, so I installed it by running:

```bash
brew install python-tk
```

You should also create a `.env` file with your `ANTHROPIC_API_KEY`. If you don't know how to do this, paste this paragraph into chatgpt and it'll walk you through it.

## Usage

Once you have everything set up, you can run the script using:

```bash
python main.py --task "your task description" --interval 60
```

Required arguments:

- `--task`: Description of the task you should be working on (e.g., "writing my thesis")
- `--interval`: Time between checks in seconds (default: 60)

Optional arguments:

- `--verbose`: Enable debug logging

You might have to give screen recording permissions to your terminal application or Python for the screenshot functionality to work. On macOS, you can do this in System Settings > Privacy & Security > Screen Recording.

When the script detects you're off task, it will display a full-screen overlay that you can only dismiss by typing a randomly generated apologetic message. The overlay blocks all attempts to close or minimize it until you type the message correctly.

## Todos

At some point, I'll want to:

- add support for different LLMs (ollama locally, OpenAI, whatever)
- make script calling more user-friendly (if no flags passed, ask for task + interval, if no api key, ask for it + store in .env)
- let user set strictness levels
