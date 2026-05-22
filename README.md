# 🤖 Multi-Agent Meeting Assistant AI

A powerful, command-line multi-agent AI assistant built with Python, the official **Google GenAI SDK**, and **Pydantic**. It analyzes meeting transcripts to generate structured summaries and extract actionable tasks. The tool processes these requests concurrently using asynchronous execution and supports transcript translation.

---

## ✨ Features

* **Parallel Agent Processing**: Leverages `asyncio` to run the **Meeting Summarizer Agent** and the **Action Item Agent** concurrently, minimizing latency.
* **Structured Output Validation**: Enforces strict Pydantic schema validation on Gemini's JSON outputs, ensuring predictable, type-safe results.
* **Multilingual Translation**: Pre-translates transcripts into target languages before running downstream analysis.
* **Externalized Prompts**: Cleanly separates agent prompts into dedicated markdown files (`prompts/`) for easy tweaking and versioning.
* **Flexible CLI Interface**: Accept inputs from local files, configure target translation languages, and customize where results are written.

---

## 📂 Project Structure

```text
├── agents/
│   ├── __init__.py
│   ├── action_item_agent.py    # Extracts tasks, assignees, due dates, and flags issues
│   ├── meeting_summarizer.py   # Outlines discussion points, decisions, and summaries
│   └── translator_agent.py     # Pre-translates transcripts to target languages
├── schema/
│   ├── __init__.py
│   └── meeting_schema.py       # Pydantic schemas (MeetingSummary, ActionItemReport, etc.)
├── prompts/
│   ├── action_item_prompt.md   # System instructions for task extraction
│   ├── summarizer_prompt.md    # System instructions for meeting summarization
│   └── translator_prompt.md    # System instructions for translation
├── example/
│   └── transcripts/            # A collection of sample transcript files
├── main.py                     # Main entrypoint and CLI handler
├── pyproject.toml              # Project configuration and script entrypoint
├── uv.lock                     # UV lockfile
└── .env.example                # Template for environment configuration
```

---

## 🚀 Quick Start

### 1. Prerequisites

* **Python**: Version 3.11+
* **UV**: Astral's fast Python package installer. If not installed, you can install it using:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

### 2. Installation

Clone the repository and install the project dependencies:

```bash
cd Gapstars_hack_AI
uv sync
```

### 3. Setup Environment Variables

Copy the template environment file to `.env`:

```bash
cp .env.example .env
```

Edit your `.env` file and insert your Google Gemini API key:

```ini
GEMINI_API_KEY=AIzaSy...
```

---

## 🛠️ Usage

This project defines a CLI command shortcut called `meeting` in `pyproject.toml`. You can run it via `uv run meeting`.

### Display CLI Options

Run with the `--help` (or `-h`) flag to view the available CLI options:

```bash
uv run meeting --help
```

Output:
```text
usage: meeting [-h] [--file FILE] [--language LANGUAGE] [--output OUTPUT]

Multi-Agent Meeting Assistant CLI

options:
  -h, --help            show this help message and exit
  --file, -f FILE       Path to a text file containing the meeting transcript.
                        If not provided, the default sample transcript is
                        used.
  --language, -l LANGUAGE
                        Target language for translation (default: English).
  --output, -o OUTPUT   Path to save the JSON output (default: output.json).
```

### Run on Default Sample Transcript

Run the workflow on the built-in sample transcript:

```bash
uv run meeting
```

This runs both agents concurrently, prints a formatted overview of the meeting summary and action items to the terminal, and writes the complete structured payload to `output.json`.

### Run on a Specific Transcript File

Use the `--file` (or `-f`) flag to analyze one of the transcript files in the `example/transcripts/` directory:

```bash
uv run meeting --file "example/transcripts/Product Roadmap Sprint Kickoff.txt"
```

### Run with Translation

Analyze the meeting and translate the output to a target language (e.g., German, Spanish, French) by specifying the `--language` (or `-l`) flag:

```bash
uv run meeting --file "example/transcripts/Tangent Creative Co.txt" --language "Spanish"
```

### Customize Output File

Choose where to save the complete JSON results using the `--output` (or `-o`) option:

```bash
uv run meeting -f "example/transcripts/Product Roadmap Sprint Kickoff.txt" -o sprint_analysis.json
```

---

## 🤖 Under the Hood

1. **Translation (Optional)**: If the target language is not English, the `Translator Agent` translates the transcript first.
2. **Parallel Processing**: Using `asyncio.gather()`, both the `Meeting Summarizer` and the `Action Item` agents run concurrently.
3. **Structured Outputs**: Each agent queries Gemini using system instructions loaded from `prompts/` and parses the JSON response into a strict Pydantic model (`MeetingSummary` and `ActionItemReport`).
4. **Validation & Consolidation**: The results are consolidated into a `MeetingWorkflowResult` object, formatted, and saved to disk.