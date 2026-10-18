#!/usr/bin/env bash
# Zero-surprise deploy, run on the server as user `nesma` (by GitHub Actions or by hand):
#   bash /var/www/nesma/app/deploy/deploy.sh
# Steps: pull main -> install deps -> checks -> migrate -> collectstatic -> restart -> health check.
# If anything fails before the restart, the running site is untouched; if the health check fails
# after the restart, the previous commit is restored automatically.
set -euo pipefail

APP=/var/www/nesma/app
VENV=/var/www/nesma/venv
BRANCH=${BRANCH:-main}
HEALTH_URL=${HEALTH_URL:-https://nit-admin.zakhf.com/api/career-options/}

cd "$APP"
PREVIOUS=$(git rev-parse HEAD)
echo "==> Current commit: $PREVIOUS"

git fetch --quiet origin "$BRANCH"
git reset --hard "origin/$BRANCH"
NEW=$(git rev-parse HEAD)
echo "==> Deploying commit: $NEW"

rollback() {
    echo "!! Deploy failed - restoring $PREVIOUS"
    git reset --hard "$PREVIOUS"
    "$VENV/bin/pip" install --quiet -r requirements.txt
    "$VENV/bin/python" manage.py collectstatic --noinput --verbosity 0
    sudo /usr/bin/systemctl restart nesma
    exit 1
}

"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r requirements.txt
"$VENV/bin/python" manage.py check --deploy --fail-level ERROR
"$VENV/bin/python" manage.py migrate --noinput
"$VENV/bin/python" manage.py collectstatic --noinput --verbosity 0

sudo /usr/bin/systemctl restart nesma
sleep 3
if ! sudo /usr/bin/systemctl is-active --quiet nesma; then rollback; fi

for attempt in 1 2 3 4 5; do
    if curl -fsS --max-time 10 -o /dev/null "$HEALTH_URL"; then
        echo "==> Deployed $NEW - health check OK"
        exit 0
    fi
    sleep 3
done
rollback
