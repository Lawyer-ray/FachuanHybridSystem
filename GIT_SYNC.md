# Git Sync Workflow

Repo path: `D:\LawFiles\FachuanHybridSystem`

Default sync branch: `dev`

## 1. Enter the repo

```powershell
cd D:\LawFiles\FachuanHybridSystem
```

## 2. Check current status

```powershell
git status
```

If the working tree is clean, syncing is safest.

## 3. Get latest remote changes

Fetch remote updates:

```powershell
git fetch origin
```

Then update local code from remote `dev`:

```powershell
git pull --ff-only origin dev
```

Notes:

- `git fetch` downloads remote updates without changing local files.
- `git pull --ff-only` updates only when Git can fast-forward safely.

## 4. Commit your local changes

Check changes:

```powershell
git status
```

Stage changes:

```powershell
git add .
```

Commit:

```powershell
git commit -m "Describe your change"
```

## 5. Push to GitHub

```powershell
git push origin dev
```

## 6. Daily workflow

```powershell
cd D:\LawFiles\FachuanHybridSystem
git status
git fetch origin
git pull --ff-only origin dev

# make changes

git status
git add .
git commit -m "Describe your change"
git push origin dev
```

## 7. If you have local changes but want to sync first

Option A: commit first, then pull

```powershell
git add .
git commit -m "WIP: save current progress"
git fetch origin
git pull --ff-only origin dev
```

Option B: stash first, then pull

```powershell
git stash
git fetch origin
git pull --ff-only origin dev
git stash pop
```

## 8. Useful check commands

Show remote:

```powershell
git remote -v
```

Show branch tracking:

```powershell
git branch -vv
```

Show recent commits:

```powershell
git log --oneline --decorate -n 10
```

## 9. Current repo setup

- Remote: `origin = https://github.com/zzdd5201314-ctrl/FachuanHybridSystem.git`
- Current branch: `dev`
- Local `dev` tracks `origin/dev`

Core commands:

```powershell
git pull --ff-only origin dev
git push origin dev
```
