# Deploying Signal Workshop to Public Cloud (Vercel & GitHub)

Your repository is now completely configured and ready for public cloud deployment.

---

## Option A: GitHub + Vercel (Recommended — Automatic Continuous Deployment)

### Step 1: Create a GitHub Repository
1. Log into your account at [GitHub.com](https://github.com/).
2. Click **New Repository** (or visit [github.com/new](https://github.com/new)).
3. Name it `signal-workshop`, keep it **Public** (or Private), and **leave "Initialize with README / .gitignore" unchecked**.
4. Click **Create repository**.

### Step 2: Push your local code to GitHub
Open PowerShell and run these two commands (replace `<YOUR_USERNAME>` with your GitHub username):

```powershell
& "C:\Users\samaj\AppData\Local\MinGit\cmd\git.exe" -C "C:\Users\samaj\Documents\Codex\2026-11-20\c\outputs\signal-workshop" remote add origin https://github.com/<YOUR_USERNAME>/signal-workshop.git
& "C:\Users\samaj\AppData\Local\MinGit\cmd\git.exe" -C "C:\Users\samaj\Documents\Codex\2026-11-20\c\outputs\signal-workshop" push -u origin main
```

---

### Step 3: Connect & Deploy on Vercel
1. Log into [Vercel.com](https://vercel.com/) (Sign in with your GitHub account).
2. Click **Add New...** → **Project**.
3. Under **Import Git Repository**, find `signal-workshop` and click **Import**.
4. Keep all default settings (Vercel automatically detects `vercel.json`, `package.json`, and `api/index.py`).
5. Click **Deploy**!

Within ~60 seconds, Vercel will give you a live public URL:
**`https://signal-workshop.vercel.app`**
You can open this URL from your phone, tablet, or any computer 24/7 without keeping your laptop on!

---

## Option B: Direct 1-Command Deploy via Vercel CLI (No GitHub needed)

If you don't want to use GitHub right now, you can deploy straight to Vercel:

1. Open PowerShell and run:
```powershell
cd "C:\Users\samaj\Documents\Codex\2026-11-20\c\outputs\signal-workshop"
npx vercel
```
2. Press `Enter` to log in via browser.
3. Confirm project settings with default prompts.
4. Your website is instantly live!

---

## Optional: 24/7 Dedicated Backend on Render (For heavy 100-stock batch scans)

Vercel's free serverless tier has a 15-second execution timeout. If scanning all 100 Nifty stocks takes longer than 15s:
1. Log into [Render.com](https://render.com/).
2. Click **New +** → **Blueprint** and connect your GitHub `signal-workshop` repository.
3. Render reads `render.yaml` and starts a persistent 24/7 Python Web Service (`https://signal-workshop-backend.onrender.com`).
4. In Vercel Project Settings → **Environment Variables**, add:
   - `VITE_API_BASE` = `https://signal-workshop-backend.onrender.com`
5. Vercel automatically redeploys and routes all data through your 24/7 cloud backend with zero timeouts!
