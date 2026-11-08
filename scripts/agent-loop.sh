#!/usr/bin/env bash
cd ~/project/Cipher-CTF-notes || exit 1
MAX=20; HOURS=10
DEADLINE=$(( $(date +%s) + HOURS*3600 ))
MODELS=(opencode/glm-5.3-flash-free opencode/deepseek-v4.1-flash-free opencode/mimo-v2.6-flash-free)
EMPTY=0
for n in $(seq 1 $MAX); do
  [ "$(date +%s)" -ge "$DEADLINE" ] && { echo "time limit reached"; break; }
  [ -f .agent/DONE ] && { echo "agent says DONE"; break; }
  git fetch -q origin main || { echo "fetch failed"; sleep 120; continue; }
  B="dev/auto-$(date +%m%d-%H%M)-$n"
  git checkout -q -b "$B" origin/main || break
  M=${MODELS[$((n % ${#MODELS[@]}))]}
  echo "== [$n/$MAX] $B with $M =="
  timeout 60m opencode run -m "$M" "$(cat scripts/agent-prompt.md)

Current branch: $B"
  [ "$(git branch --show-current)" = "$B" ] || { echo "branch changed, abort"; exit 1; }
  if [ -n "$(git status --porcelain)" ]; then git add -A && git commit -q -m "chore: leftover changes"; fi
  if [ "$(git rev-list --count origin/main..HEAD)" -gt 0 ]; then
    git push -u origin "$B" && EMPTY=0
  else
    EMPTY=$((EMPTY+1)); echo "no commits this run ($EMPTY)"
    git checkout -q --detach origin/main; git branch -D "$B" -q
    [ "$EMPTY" -ge 3 ] && { echo "3 empty runs in a row, stopping"; break; }
  fi
  sleep 30
done
git checkout -q --detach origin/main
echo "finished. branches:"; git branch --list 'dev/auto-*'
