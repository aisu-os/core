#!/bin/bash
set -e

# Docker daemon boshlash (Sysbox ichida ishlaydi)
if [ -e /var/run/docker.sock ] || command -v dockerd &> /dev/null; then
    # Sysbox runtimeda dockerd to'g'ridan-to'g'ri ishga tushishi mumkin
    if ! pgrep -x dockerd > /dev/null 2>&1; then
        sudo dockerd --storage-driver=overlay2 > /var/log/dockerd.log 2>&1 &

        # Docker daemon tayyor bo'lishini kutish
        retries=0
        max_retries=30
        while ! docker info > /dev/null 2>&1; do
            retries=$((retries + 1))
            if [ "$retries" -ge "$max_retries" ]; then
                echo "Warning: Docker daemon did not start in time" >&2
                break
            fi
            sleep 1
        done
    fi
fi

# Foydalanuvchi buyrug'ini ishga tushirish
exec "$@"
