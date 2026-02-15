#!/bin/bash

# Docker daemon boshlash (faqat Sysbox runtime ichida ishlaydi)
# Sysbox bo'lmasa dockerd ishlamaydi — o'tkazib yuboramiz
if [ -e /run/sysbox/sysfs ] && command -v dockerd &> /dev/null; then
    if ! pgrep -x dockerd > /dev/null 2>&1; then
        sudo dockerd --storage-driver=overlay2 > /var/log/dockerd.log 2>&1 &

        # Docker daemon tayyor bo'lishini kutish
        retries=0
        max_retries=15
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
