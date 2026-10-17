#!/usr/bin/env bash
set -euo pipefail

# 1. Initialize Git and commit all project + CI/CD files to main
if [ ! -d .git ]; then
  git init -b main
fi
git add index.html manifest.json sw.js deploy.sh .github/workflows/deploy-pages.yml
git commit -m "feat: VibeHop PWA with mobile fixes and GitHub Pages CI/CD" || true

# 2. Create GitHub repository (or push if already created)
if ! git remote get-url origin >/dev/null 2>&1; then
  gh repo create vibehop --public --source=. --remote=origin --push
else
  git push -u origin main
fi

# 3. Enable GitHub Pages with GitHub Actions workflow build_type
gh api --method POST \
  -H "Accept: application/vnd.github+json" \
  /repos/:owner/vibehop/pages \
  -f build_type='workflow' 2>/dev/null || \
gh api --method PUT \
  -H "Accept: application/vnd.github+json" \
  /repos/:owner/vibehop/pages \
  -f build_type='workflow' || true

# 4. Print live GitHub Pages URL
GH_USER=$(gh api user -q .login)
LIVE_URL="https://${GH_USER}.github.io/vibehop/"
echo "===================================================="
echo "✨ VibeHop CI/CD deployed! Live URL:"
echo "👉 ${LIVE_URL}"
echo "===================================================="
