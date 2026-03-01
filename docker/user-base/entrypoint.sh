#!/bin/bash

# ── Home directory initialization ──
# Bind mount bo'sh host papkani mount qilganda default fayllar yo'qoladi.
# /etc/aisu-skel/ dan etishmayotgan fayllarni tiklash (mavjudlarini ustiga yozmaydi).
SKEL_DIR="/etc/aisu-skel"
HOME_DIR="/home/aisu"

if [ -d "$SKEL_DIR" ]; then
    # Standard papkalar yaratish
    for dir in Desktop Documents Downloads Pictures Music Videos .Trash; do
        [ ! -d "$HOME_DIR/$dir" ] && mkdir -p "$HOME_DIR/$dir"
    done

    # Etishmayotgan default fayllarni nusxalash (mavjudlarini o'zgartirmaydi)
    cd "$SKEL_DIR" && find . -type f | while IFS= read -r file; do
        target="$HOME_DIR/$file"
        if [ ! -e "$target" ]; then
            mkdir -p "$(dirname "$target")"
            cp -a "$SKEL_DIR/$file" "$target"
        fi
    done

    # Ownership tuzatish
    chown -R aisu:aisu "$HOME_DIR" 2>/dev/null || true
fi

# ── Docker daemon (faqat Sysbox runtime ichida) ──
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
