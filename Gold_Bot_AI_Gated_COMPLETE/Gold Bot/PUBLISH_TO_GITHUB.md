# Publish this project on GitHub

Create a **private, empty** repository on <https://github.com/new> named `gold-mt5-paper-bot`. Leave the GitHub README, `.gitignore`, and license boxes unchecked because they are already supplied here.

Install Git for Windows if `git --version` fails. Open PowerShell in the extracted `Gold-Bot-GitHub` directory and run:

```powershell
git init
git branch -M main
git add .
git status --short
git commit -m "Add MT5 gold paper bot and research"
git remote add origin https://github.com/YOUR_USERNAME/gold-mt5-paper-bot.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username. If Git asks you to set an identity, run `git config --global user.name 'Your Name'` and `git config --global user.email 'you@example.com'`, then repeat the commit and push. Complete GitHub authentication in the browser if prompted; never put a token in the repository URL or project files.

The project deliberately excludes your local API keys, virtual positions, account logs, cache folders and the local `config.yaml`. The source, supplied strategy and backtest data are included. Check `git status --short` before committing. You can add a license later when you decide how others may reuse the code.
