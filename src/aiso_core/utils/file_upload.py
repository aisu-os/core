import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB


async def save_avatar(file: UploadFile, user_id: uuid.UUID, upload_dir: str) -> str:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Faqat rasm fayllari qabul qilinadi",
        )

    ext = ""
    if file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ruxsat berilgan formatlar: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fayl hajmi 2MB dan oshmasligi kerak",
        )

    avatars_dir = Path(upload_dir) / "avatars"
    os.makedirs(avatars_dir, exist_ok=True)

    filename = f"{user_id}.{ext}"
    filepath = avatars_dir / filename

    with open(filepath, "wb") as f:
        f.write(content)

    return f"/uploads/avatars/{filename}"
