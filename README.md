# 🤖 AI Code Review Bot (Google Gemini + GitHub Actions)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Google Gemini API](https://img.shields.io/badge/AI-Google%20Gemini-orange.svg)](https://ai.google.dev/)
[![GitHub Actions](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-brightgreen.svg)](https://github.com/features/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An automated, intelligent AI code reviewer that fetches GitHub Pull Request diffs, analyzes changed code using the **Google Gemini API** (`google-genai` SDK with structured JSON output), and automatically posts actionable feedback back to GitHub — both as a **summary status table** and as **inline diff comments** directly on the offending lines of code.

---

## 📑 Table of Contents

- [Features](#-features)
- [Architecture & Flow](#-architecture--flow)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Step-by-Step Setup Guide](#-step-by-step-setup-guide)
  - [1. Clone & Environment Setup](#1-clone--environment-setup)
  - [2. Obtain API Tokens](#2-obtain-api-tokens)
  - [3. Configure Environment Variables](#3-configure-environment-variables)
- [Usage](#-usage)
  - [Local CLI (Dry-Run Mode)](#local-cli-dry-run-mode)
  - [Local CLI (Live Posting)](#local-cli-live-posting)
  - [Automated GitHub Actions CI/CD](#automated-github-actions-cicd)
- [CLI Reference](#-cli-reference)
- [Configuration Reference (`config.py`)](#-configuration-reference-configpy)
- [Comprehensive Troubleshooting Guide](#-comprehensive-troubleshooting-guide)
  - [1. Virtual Environment Activation Errors on Windows](#1-virtual-environment-activation-errors-on-windows)
  - [2. Pip Download / DNS Errors (`[Errno 11001] getaddrinfo failed`)](#2-pip-download--dns-errors-errno-11001-getaddrinfo-failed)
  - [3. GitHub API `404 Not Found` when fetching PR files](#3-github-api-404-not-found-when-fetching-pr-files)
  - [4. Gemini Model `404 NOT_FOUND` or Deprecation Errors](#4-gemini-model-404-not_found-or-deprecation-errors)
  - [5. Gemini API Key Format Questions (`AQ.Ab...` vs `AIzaSy...`)](#5-gemini-api-key-format-questions-aqab-vs-aizasy)
  - [6. Windows Console Unicode / Emoji Crash (`UnicodeEncodeError: 'charmap'`)](#6-windows-console-unicode--emoji-crash-unicodeencodeerror-charmap)
  - [7. GitHub Actions `403 Resource not accessible by integration`](#7-github-actions-403-resource-not-accessible-by-integration)
  - [8. PowerShell Chaining Error (`The token '&&' is not a valid statement separator`)](#8-powershell-chaining-error-the-token--is-not-a-valid-statement-separator)
  - [9. Inline Comments Not Appearing on PR Diff](#9-inline-comments-not-appearing-on-pr-diff)
  - [10. Authentication & Missing Env Var Errors](#10-authentication--missing-env-var-errors)
- [Contributing](#-contributing)
- [License](#-license)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🧠 **Structured AI Outputs** | Uses `response_schema` in Google GenAI SDK for 100% typed, reliable JSON schema parsing without fragile text regexes. |
| 💬 **Line-by-Line Inline Comments** | Attaches actionable comments directly to the exact file line in the GitHub PR diff. |
| 📊 **Summary Review Table** | Generates an organized Markdown table categorized by severity level (`CRITICAL`, `WARNING`, `MINOR`). |
| 🏷️ **Categorized Findings** | Identifies `bug`, `security`, `perf` (performance), and `style` violations. |
| 🛡️ **Cost & Safety Guardrails** | Automatically skips lock files, binary assets, and files exceeding the 500-line diff threshold. |
| 🔄 **Smart Deduplication** | Merges duplicate comments on the same `(file, line, category)` key and keeps the highest severity. |
| 🧪 **Dry-Run Mode** | Test and preview reviews locally in your terminal before publishing any comments to GitHub. |
| ⚡ **Zero-Config CI/CD** | Plug-and-play GitHub Actions workflow triggers automatically on PR open, synchronize, or reopen. |

---

## 🏗 Architecture & Flow

```
   ┌────────────────────────────────────────────────────────┐
   │                  GitHub Pull Request                   │
   └───────────────────────────┬────────────────────────────┘
                               │ (1) Fetch changed files & diff
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │             github_client.py (PyGithub)                │
   └───────────────────────────┬────────────────────────────┘
                               │ (2) Filter ignored paths / diff > 500 lines
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │                reviewer.py (Google GenAI)              │
   │  - Model: gemini-flash-latest                          │
   │  - System Prompt: Senior Code Reviewer                 │
   │  - Output: Structured JSON Schema (Finding objects)    │
   └───────────────────────────┬────────────────────────────┘
                               │ (3) Deduplicate & sort by severity
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │                   main.py (Orchestrator)               │
   └───────────────────────────┬────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
┌───────────────────────────────┐   ┌───────────────────────────────┐
│   Top-Level Summary Comment   │   │  Per-Line Diff Annotations    │
│  (Markdown table of findings) │   │ (create_review_comment on SHA)│
└───────────────────────────────┘   └───────────────────────────────┘
```

---

## 📁 Project Structure

```
code_review_bot/
├── main.py                  # CLI orchestrator: argument parsing, deduplication, posting
├── github_client.py         # GitHub API wrapper: fetch PR diffs, post summary & inline comments
├── reviewer.py              # Gemini API engine: schema definition, system prompt, AI review
├── models.py                # Data classes: Finding model, severity levels, markdown formatting
├── config.py                # Settings: ignored paths, caps, severity thresholds, comment templates
├── requirements.txt         # Pinned Python dependencies
├── .env.example             # Template for local environment secrets
├── .gitignore               # Ignores virtual environments, pycache, and secrets
└── .github/
    └── workflows/
        └── review.yml       # GitHub Actions automated PR review workflow
```

---

## 📋 Prerequisites

- **Python**: 3.11 or newer installed
- **Git**: Installed and configured
- **GitHub Account & Repository**: With administrative permissions to add repository secrets and create pull requests
- **Google AI Studio Account**: For generating a Gemini API Key

---

## 🚀 Step-by-Step Setup Guide

### 1. Clone & Environment Setup

```bash
# Clone your repository
git clone https://github.com/YOUR_USERNAME/code_review.git
cd code_review

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# On Windows (Command Prompt):
.venv\Scripts\activate
# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

### 2. Obtain API Tokens

#### A. Google Gemini API Key
1. Go to **[Google AI Studio](https://aistudio.google.com/)**.
2. Click **"Get API key"** → **"Create API key"**.
3. Copy the key (it starts with `AIzaSy...` or `AQ.Ab...`).

#### B. GitHub Personal Access Token (PAT)
*(Needed for local testing; GitHub Actions uses automatic internal tokens)*
1. Go to **[GitHub Personal Access Tokens (Classic)](https://github.com/settings/tokens)**.
2. Click **Generate new token (classic)**.
3. Note: `code-review-bot`.
4. Select scope: ✅ **`repo`** (Full control of repositories).
5. Click **Generate token** and copy the string (starts with `ghp_...`).

---

### 3. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Edit `.env`:
```env
GITHUB_TOKEN=ghp_your_github_token_here
GEMINI_API_KEY=your_gemini_api_key_here
```

---

## 💻 Usage

### Local CLI (Dry-Run Mode)
Preview what the AI reviewer would post without modifying GitHub:

```bash
python main.py --repo your-org/your-repo --pr 42 --dry-run
```

**Example Output:**
```
========================================================================
DRY RUN — Summary comment that would be posted:
========================================================================
## 🤖 AI Code Review

Automated review generated by **gemini-code-reviewer**.
Findings are ordered by severity. Please address **critical** issues before merging.

Found **1** issue(s): **1** critical.

| Severity | Category | File | Line | Issue |
|----------|----------|------|------|-------|
| 🔴 Critical | `security` | `test_feature.py` | 8 | Direct string interpolation into SQL query allows SQL injection. Use parameterized query. |

---
_This review was generated automatically. False positives may occur — use your own judgement._
========================================================================
```

---

### Local CLI (Live Posting)
Run review and publish both summary and inline comments to the PR:

```bash
python main.py --repo your-org/your-repo --pr 42
```

---

### Automated GitHub Actions CI/CD

1. Open your repository on GitHub.
2. Navigate to **Settings → Secrets and variables → Actions → New repository secret**.
3. Add:
   - **Name**: `GEMINI_API_KEY`
   - **Secret**: `<Your Google Gemini API Key>`
4. Go to **Settings → Actions → General → Workflow permissions**:
   - Select **Read and write permissions**.
   - Check **Allow GitHub Actions to create and approve pull requests**.
   - Click **Save**.
5. Push any commit to a branch and open a Pull Request — the review bot will comment automatically!

---

## ⚙️ CLI Reference

```
usage: main.py [-h] --repo OWNER/NAME --pr NUMBER [--token GHTOKEN]
               [--gemini-key API_KEY] [--dry-run]
               [--min-severity {critical,warning,minor}] [--model MODEL]
               [--verbose]

Options:
  -h, --help            Show this help message and exit
  --repo OWNER/NAME     GitHub repository in owner/name format (e.g. acme/backend or your-org/your-repo)
  --pr NUMBER           Pull request number to review (e.g. 42)
  --token GHTOKEN       GitHub personal access token (defaults to GITHUB_TOKEN env var)
  --gemini-key API_KEY  Google Gemini API key (defaults to GEMINI_API_KEY or GOOGLE_API_KEY env var)
  --dry-run             Print findings to stdout without posting comments to GitHub
  --min-severity LEVEL  Minimum severity to post as inline comment: critical | warning | minor (default: warning)
  --model MODEL         Gemini model name (default: gemini-flash-latest)
  -v, --verbose         Enable debug-level logging
```

---

## 🛠️ Configuration Reference (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `IGNORED_PATHS` | `['node_modules', '.lock', 'dist/', 'build/', ...]` | Files containing these strings in their path are skipped from review. |
| `MIN_SEVERITY_TO_POST` | `"warning"` | Lowest severity finding to post as an inline comment. |
| `MAX_FILES_PER_RUN` | `20` | Caps the number of files analyzed per run to prevent excessive API consumption. |
| `MAX_DIFF_LINES_PER_FILE`| `500` | Files exceeding this diff line count are safely skipped with a log warning. |

---

## 🔧 Comprehensive Troubleshooting Guide

Here is the complete step-by-step solution for all common issues:

---

### 1. Virtual Environment Activation Errors on Windows

#### Symptom:
```
/.venv/Scripts/activate
The system cannot find the path specified.
```
or
```
.venv/Scripts/activate
'.venv' is not recognized as an internal or external command
```
or PowerShell Execution Policy error:
```
File .venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on this system.
```

#### Cause:
- Windows Command Prompt (`cmd.exe`) requires **backslashes** `\`, not forward slashes `/`.
- PowerShell blocks script execution by default.

#### Solution:
- **For Command Prompt (`cmd.exe`)**:
  ```cmd
  .venv\Scripts\activate
  ```
- **For PowerShell**: Run as Administrator once to enable script execution:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  .\.venv\Scripts\Activate.ps1
  ```
- **For Git Bash**:
  ```bash
  source .venv/Scripts/activate
  ```

---

### 2. Pip Download / DNS Errors (`[Errno 11001] getaddrinfo failed`)

#### Symptom:
```
WARNING: Retrying ... after connection broken by 'NewConnectionError('<...>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /pydantic/
```

#### Cause:
- Temporary DNS resolution lag, network interruption, or firewall/VPN blocking PyPI domains during package downloads.

#### Solution:
1. **Allow Pip to Retry**: Pip has automatic retries (up to 5 attempts) built in. In most cases, it successfully connects after the second attempt.
2. **Explicitly trust PyPI hosts**:
   ```cmd
   pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
   ```
3. **Disable VPN / Proxy**: If behind a corporate proxy, set the proxy flag:
   ```cmd
   pip install -r requirements.txt --proxy http://user:password@proxyserver:port
   ```

---

### 3. GitHub API `404 Not Found` when fetching PR files

#### Symptom:
```
[ERROR] github_client: GitHub API error fetching PR files: 404 {"message": "Not Found"}
```

#### Cause:
1. **The PR does not exist yet**: Running `--pr 1` before creating a pull request on GitHub.
2. **Private Repository without Token**: The repo is private and no `GITHUB_TOKEN` was provided or the token lacks the `repo` scope.
3. **Typo in `--repo` argument**: For example, typing `user/repo` instead of the exact `Owner/Repo_Name`.

#### Solution:
1. Check that the PR is actually open at `https://github.com/<OWNER>/<REPO>/pull/<PR_NUMBER>`.
2. Ensure your token in `.env` has the **`repo`** scope checked at [GitHub Tokens](https://github.com/settings/tokens).
3. Ensure the `--repo` flag matches your repository's exact path (`owner/repo-name`).

---

### 4. Gemini Model `404 NOT_FOUND` or Deprecation Errors

#### Symptom:
```
google.genai.errors.ClientError: 404 NOT_FOUND.
{'error': {'code': 404, 'message': 'This model models/gemini-2.5-flash is no longer available to new users.'}}
```

#### Cause:
- Hardcoding a deprecated or preview model name that has been superseded in the Google GenAI endpoint.

#### Solution:
- Use the alias **`gemini-flash-latest`** or **`gemini-2.0-flash`** / **`gemini-1.5-flash`**.
- This project defaults to `gemini-flash-latest` which always targets the current stable Flash release.
- You can override the model on the fly using `--model`:
  ```cmd
  python main.py --repo your-org/your-repo --pr 42 --model gemini-flash-latest
  ```

---

### 5. Gemini API Key Format Questions (`AQ.Ab...` vs `AIzaSy...`)

#### Question:
> *"My Gemini API key starts with `AQ.Ab...` instead of `AIzaSy...`. Is this supported?"*

#### Answer:
- **Yes!** Google AI Studio issues API keys with different prefixes depending on the account tier and project region (`AQ.Ab...`, `AIzaSy...`, etc.).
- The bot does not validate key prefixes; it passes the raw token directly to the Google GenAI SDK. Paste your complete key into `.env` under `GEMINI_API_KEY`.

---

### 6. Windows Console Unicode / Emoji Crash (`UnicodeEncodeError: 'charmap'`)

#### Symptom:
```
UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f916' in position 3: character maps to <undefined>
```

#### Cause:
- Windows Command Prompt traditionally defaults to legacy code page `cp1252`, which cannot print emojis like 🤖, 🔴, 🟡.

#### Solution:
- In `main.py`, `sys.stdout.reconfigure(encoding='utf-8')` is automatically invoked at startup.
- If running in custom scripts or older shells, set the console code page to UTF-8 before executing:
  ```cmd
  chcp 65001
  python main.py --repo your-org/your-repo --pr 42 --dry-run
  ```

---

### 7. GitHub Actions `403 Resource not accessible by integration`

#### Symptom:
GitHub Actions fails on the step `post_review_comment` with:
```
403 {"message": "Resource not accessible by integration", "status": "403"}
```

#### Cause:
- The default `${{ secrets.GITHUB_TOKEN }}` in GitHub Actions does not have write permissions to post pull request comments.

#### Solution:
1. Ensure `.github/workflows/review.yml` contains:
   ```yaml
   permissions:
     pull-requests: write
     contents: read
   ```
2. In your GitHub repository: Go to **Settings → Actions → General → Workflow permissions** → Check **"Read and write permissions"** and **Save**.

---

### 8. PowerShell Chaining Error (`The token '&&' is not a valid statement separator`)

#### Symptom:
```
git add .env.example && git commit -m "update"
The token '&&' is not a valid statement separator in this version.
```

#### Cause:
- Windows PowerShell 5.1 (the default built into Windows) does not support the Bash-style `&&` operator.

#### Solution:
- Use a semicolon `;` to chain commands in PowerShell:
  ```powershell
  git add -A; git commit -m "message"; git push origin main
  ```
- Or run each command on a new line.

---

### 9. Inline Comments Not Appearing on PR Diff

#### Symptom:
- The summary table is posted, but inline comments on specific code lines are omitted or logged with a warning: `Could not post inline comment on file:line`.

#### Cause:
- GitHub only allows inline review comments on lines that are **part of the pull request unified diff** (new or modified lines). Unmodified context lines cannot receive inline comments via the review comment API.

#### Solution:
- The bot handles this gracefully: findings on unmodified lines will still appear in the **Top-Level Summary Table**, while lines present in the diff will receive direct inline comments.

---

### 10. Authentication & Missing Env Var Errors

#### Symptom:
```
[ERROR] main: No GitHub token provided. Set --token or the GITHUB_TOKEN env var.
```
or
```
[ERROR] main: No Google Gemini API key provided. Set --gemini-key, GEMINI_API_KEY, or GOOGLE_API_KEY env var.
```

#### Solution:
- Verify your `.env` file exists in the root directory and contains:
  ```env
  GITHUB_TOKEN=ghp_...
  GEMINI_API_KEY=...
  ```
- Ensure `load_dotenv()` can find the `.env` file, or supply the keys explicitly via CLI flags:
  ```cmd
  python main.py --repo your-org/your-repo --pr 42 --token ghp_xxx --gemini-key AQ.Ab_xxx
  ```

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'feat: Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request — let the bot review your code! 🎉

---

## 📄 License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.
