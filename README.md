<div align="center">

<img src="desktop/public/deutschx.png" width="96" alt="DeutschX logo" />

# DeutschX 🇩🇪

**Your personal AI German tutor — on your own computer.**

Learn German through real conversation: pick a topic, and DeutschX teaches you at your level
with examples, exercises and feedback — and it never forgets where you left off. Plus a
vocabulary trainer, spaced-repetition review, a Paul-Noble-style listening drill, deep word
study, and pronunciation practice.

[![Release](https://img.shields.io/github/v/release/amirbahador-hub/DeutschX?display_name=tag)](https://github.com/amirbahador-hub/DeutschX/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Platforms](https://img.shields.io/badge/platforms-macOS%20%7C%20Windows%20%7C%20Linux-informational)

</div>

---

## ⬇️ Download & install

Grab the installer for your system from the **[latest release](https://github.com/amirbahador-hub/DeutschX/releases/latest)** — nothing else to install.

| Your computer | Download | How to install |
|---|---|---|
| **macOS** | `DeutschX_x.y.z_aarch64.dmg` (Apple Silicon) or `…_x64.dmg` (Intel) | Open the `.dmg`, drag **DeutschX** into **Applications**. **First launch:** right-click the app → **Open** → **Open** (one time — see below). |
| **Windows** | `DeutschX_x.y.z_x64-setup.exe` or `.msi` | Double-click and follow the installer. |
| **Linux** | `DeutschX_x.y.z_amd64.AppImage` or `.deb` | AppImage: right-click → Properties → allow “executable”, then double-click. Or `sudo dpkg -i` the `.deb`. |

### macOS: "DeutschX can't be opened"
The app is **not code-signed** (signing needs a paid Apple account), so the first time you
open it macOS asks you to confirm. This is one-time and safe:

1. **Right-click** (or Control-click) the DeutschX app in Applications
2. Choose **Open**
3. Click **Open** again in the dialog

After that it opens normally like any other app.

---

## 🔑 First run

On first launch DeutschX asks for an **Anthropic API key** — this is what powers the tutor.

1. Get a key at **[console.anthropic.com](https://console.anthropic.com/settings/keys)** (you create an Anthropic account and add a little credit).
2. Paste it into DeutschX, pick your native language and German level, and click **Get started**.

That's it. You can change the key any time in **Settings**.

> 💡 Usage is billed to **your own** Anthropic account, directly from your computer. Costs are
> small for normal study (a typical lesson is a few cents). The deep "word study" and sentence
> courses are **generated once and cached**, so you only ever pay for them once.

---

## 🔒 Your privacy

**Everything stays on your machine.** DeutschX has no servers of its own — it talks to
Anthropic directly from your computer to generate lessons, and stores your lessons, vocabulary
and settings locally:

- **macOS:** `~/Library/Application Support/DeutschX`
- **Windows:** `%APPDATA%\DeutschX`
- **Linux:** `~/.local/share/DeutschX`

Your lessons and notes are **never uploaded anywhere**. Each person's DeutschX is entirely their own.

---

## ✨ What's inside

- **💬 Lessons** — a patient AI tutor teaches any topic step by step, corrects you kindly, and
  resumes exactly where you left off.
- **🔤 Vocabulary** — every new word is captured automatically (with gender colour-coding:
  <span>der</span>/<span>die</span>/<span>das</span>). Add your own words too — with an optional
  AI check that fixes the article, spelling and meaning.
- **🔁 Review** — spaced-repetition quizzes (SM-2) so you don't forget what you learned.
- **🎧 Listen** — a Paul-Noble-style hands-free drill: hear the English, say the German in the
  pause, then hear the slow answer. **Words** mode drills your deck; **Sentences** mode builds a
  progressive course (each word taught first, then assembled into sentences that grow harder).
- **📖 Words** — deep study of any word: its parts (*Versicherung = ver- + sicher + -ung*),
  its word family across noun/verb/adjective/adverb, verb conjugations, examples, and links to
  Linguee & Wiktionary.
- **🎤 Speak** *(optional)* — practise pronunciation with your microphone (see below).
- **⚙️ Settings** — interface & native language, level, voices, and more. Everything is per-topic
  scoped via the topic selector at the top.

### Pronunciation (microphone) is opt-in
To keep the install light, pronunciation practice is **off by default**. It needs a one-time
speech-model download and microphone access; turn it on in **Settings → Enable microphone
pronunciation**. (In the prebuilt installers this is currently a power-user / source-build
feature — see the developer notes.)

---

## 🛠️ Run from source (developers)

DeutschX is a Python core (the tutor/engine) + a local API + a Tauri (Rust) desktop shell with a
React UI. See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the full setup. The short version:

```bash
git clone https://github.com/amirbahador-hub/DeutschX.git && cd DeutschX
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd desktop && pnpm install && cd ..
./run-dev.sh            # starts the engine + opens the desktop app
```

There's also a terminal version: `python -m deutschx`.

## 📦 Publishing installers

Releases are built automatically by GitHub Actions. To cut a release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow (`.github/workflows/release.yml`) builds the macOS/Windows/Linux installers (with
the Python engine bundled in) and attaches them to a **draft** GitHub Release for you to review
and publish. See CONTRIBUTING.md for details and how to add macOS notarization later.

## 📄 License

[MIT](LICENSE) © AmirBahador
