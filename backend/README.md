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

## 🌐 FastAPI WebSocket API Server

In addition to the CLI, the backend exposes a real-time **FastAPI WebSocket Server** to stream agent insights chunk-by-chunk to the client dashboard.

### 1. Launch the Server
To start the FastAPI server on port `8000`:
```bash
uv run main.py
```
*Note: If port `8000` has a local development conflict (e.g. PHP built-in server or macOS AirPlay sharing), you can specify another port:*
```bash
uv run uvicorn main:app --port 8001
```

### 2. WebSocket Endpoint
*   **Path**: `/ws/summarize`
*   **Client Handshake**: Sends a JSON object with the transcript and optional target language:
    ```json
    {
      "transcript": "Sarah: Let's discuss the Q2 roadmap...",
      "language": "English"
    }
    ```
*   **Server Stream Events**:
    *   `status`: Updates the current operation stage.
        ```json
        { "type": "status", "message": "Translating to French..." }
        ```
    *   `summary_chunk` / `actions_chunk`: Real-time streaming tokens generated by the agents.
        ```json
        { "type": "summary_chunk", "chunk": "The team aligned..." }
        ```
    *   `summary_done` / `actions_done`: Final parsed JSON payloads matching the Pydantic schemas.
        ```json
        { "type": "summary_done", "data": { "concise_summary": "...", "decisions_made": [] } }
        ```
    *   `complete`: Fired when all agents complete their execution cycles.
        ```json
        { "type": "complete" }
        ```
    *   `error`: Triggered if the connection or LLM pipeline fails.
        ```json
        { "type": "error", "message": "API key validation failed." }
        ```

### 3. Run WebSocket Tests
A test runner `test_websocket.py` is included to verify WebSocket client connectivity:
```bash
# Activate virtualenv and run the test client
./.venv/bin/python test_websocket.py
```

---

## 🤖 Under the Hood

1. **Translation (Optional)**: If the target language is not English, the `Translator Agent` translates the transcript first.
2. **Parallel Processing**: Using `asyncio.gather()`, both the `Meeting Summarizer` and the `Action Item` agents run concurrently.
3. **Structured Outputs**: Each agent queries Gemini using system instructions loaded from `prompts/` and parses the JSON response into a strict Pydantic model (`MeetingSummary` and `ActionItemReport`).
4. **Validation & Consolidation**: The results are consolidated into a `MeetingWorkflowResult` object, formatted, and saved to disk.