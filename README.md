# 🤖 AI Code Review Bot

An automated code review tool that fetches GitHub PR diffs, sends them to [Google Gemini](https://ai.google.dev/) for analysis, and posts structured findings back as PR comments — both as a summary table and as inline diff annotations.

> Built with **Python 3.11+**, **PyGithub**, and the **Google GenAI SDK** (`google-genai` with structured JSON schema outputs).

---

## ✨ Features

| Feature | Detail |
|---|---|
| **Structured output** | Gemini returns typed JSON via `response_schema` — no fragile text parsing |
| **Inline comments** | Findings are posted directly on the offending diff line |
| **Severity tiers** | `critical` / `warning` / `minor` with configurable posting threshold |
| **Categories** | `bug`, `security`, `style`, `perf` |
| **Guardrails** | Skips binary files, files > 500 diff lines, and auto-generated paths |
| **Deduplication** | Same file + line + category findings are merged (highest severity wins) |
| **Dry-run mode** | Preview output locally before enabling live posting |
| **GitHub Actions** | One-file workflow — trigger on every PR open / push |

---

## 📁 Project Structure

```
code_review_bot/
├── main.py              # CLI entrypoint
├── github_client.py     # GitHub API: fetch diffs, post comments
├── reviewer.py          # Gemini API: review diffs, return structured findings
├── models.py            # Finding dataclass
├── config.py            # Thresholds, ignored paths, severity config
├── requirements.txt
├── .env.example
└── .github/
    └── workflows/
        └── review.yml   # GitHub Actions workflow
```

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/code_review.git
cd code_review
pip install -r requirements.txt
```

### 2. Configure secrets

```bash
cp .env.example .env
# Edit .env and fill in your tokens
```

Required variables:

| Variable | Where to get it |
|---|---|
| `GITHUB_TOKEN` | [GitHub → Settings → Developer Settings → PAT](https://github.com/settings/tokens) (needs `repo` + `pull_requests` scopes) |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) |

### 3. Dry-run on an existing PR

Always test with `--dry-run` first to verify output quality before enabling live posting:

```bash
python main.py \
  --repo your-org/your-repo \
  --pr 42 \
  --dry-run
```

Sample output:
```
========================================================================
DRY RUN — Summary comment that would be posted:
========================================================================
## 🤖 AI Code Review
...
🔴 [CRITICAL] `bug` — `src/auth.py:87`
> SQL query built with string interpolation — use parameterised queries to prevent SQL injection.
========================================================================
```

### 4. Live posting

Once you're happy with the output quality, remove `--dry-run`:

```bash
python main.py --repo your-org/your-repo --pr 42
```

---

## ⚙️ CLI Reference

```
python main.py [OPTIONS]

Required:
  --repo OWNER/NAME       GitHub repository (e.g. acme/backend)
  --pr NUMBER             Pull request number

Optional:
  --token GHTOKEN         GitHub token (default: $GITHUB_TOKEN)
  --gemini-key KEY        Google Gemini API key (default: $GEMINI_API_KEY or $GOOGLE_API_KEY)
  --dry-run               Print to stdout instead of posting to GitHub
  --min-severity LEVEL    Minimum severity to post inline [critical|warning|minor] (default: warning)
  --model MODEL           Gemini model to use (default: gemini-2.5-flash)
  -v, --verbose           Enable debug logging
```

---

## 🔄 GitHub Actions Setup

### 1. Add your Gemini API key as a secret

Go to **Settings → Secrets and variables → Actions → New repository secret**:

- Name: `GEMINI_API_KEY`
- Value: your key from [Google AI Studio](https://aistudio.google.com/)

> `GITHUB_TOKEN` is automatically provided by GitHub Actions — no setup needed.

### 2. Push the workflow

The workflow file is already at `.github/workflows/review.yml`. Once pushed to your default branch, every new PR will automatically trigger a review.

### 3. Grant workflow permissions

Go to **Settings → Actions → General → Workflow permissions** and select:
- ✅ Read and write permissions
- ✅ Allow GitHub Actions to create and approve pull requests

---

## ⚙️ Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `IGNORED_PATHS` | `node_modules`, `.lock`, `dist/`, ... | File path substrings to skip |
| `MIN_SEVERITY_TO_POST` | `"warning"` | Threshold for inline comments |
| `MAX_FILES_PER_RUN` | `20` | Cap Gemini API calls per review run |
| `MAX_DIFF_LINES_PER_FILE` | `500` | Skip files with too many changed lines |

---

## 🛡️ Guardrails

- **Large diffs** — Files with > 500 changed lines are logged and skipped.
- **Auto-generated files** — Paths matching `node_modules`, `.lock`, `dist/`, `migrations/`, protobuf outputs, etc. are filtered out.
- **API errors** — Per-file errors are caught and logged; the rest of the run continues.
- **Deduplication** — Identical (file, line, category) findings are merged to avoid comment spam.
- **Cap** — `MAX_FILES_PER_RUN` prevents runaway API costs on large PRs.

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Commit your changes
4. Open a PR — the bot will review its own changes 🎉

---

## 📄 License

MIT
