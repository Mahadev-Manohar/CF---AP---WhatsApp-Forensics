"""A `Case` is an extracted Android file tree (the output of the acquisition stage)."""

from __future__ import annotations

import os
from pathlib import Path

# Locations from Table 1 of the paper.
DATA_DIR = "data/data/com.whatsapp"
SDCARD_WA = "mnt/sdcard/WhatsApp"


class Case:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        if not self.root.is_dir():
            raise FileNotFoundError(f"evidence root not found: {self.root}")

    def find(self, rel: str) -> Path | None:
        """Case-insensitive path lookup (Table 1 mixes 'Whatsapp' and 'WhatsApp')."""
        cur = self.root
        for part in [p for p in rel.split("/") if p]:
            if not cur.is_dir():
                return None
            match = next((n for n in os.listdir(cur) if n.lower() == part.lower()), None)
            if match is None:
                return None
            cur = cur / match
        return cur

    @property
    def wa_db(self) -> Path | None:
        return self.find(f"{DATA_DIR}/databases/wa.db")

    @property
    def msgstore_db(self) -> Path | None:
        return self.find(f"{DATA_DIR}/databases/msgstore.db")

    @property
    def backups_dir(self) -> Path | None:
        return self.find(f"{SDCARD_WA}/Databases")

    @property
    def avatars_dir(self) -> Path | None:
        return self.find(f"{DATA_DIR}/files/Avatars")

    @property
    def profile_pictures_dir(self) -> Path | None:
        return self.find(f"{SDCARD_WA}/ProfilePictures")

    @property
    def logs_dir(self) -> Path | None:
        return self.find(f"{DATA_DIR}/files/Logs")

    @property
    def media_dir(self) -> Path | None:
        return self.find(f"{SDCARD_WA}/Media")

    @property
    def media_sent_dir(self) -> Path | None:
        return self.find(f"{SDCARD_WA}/Media/Sent")

    @property
    def me_file(self) -> Path | None:
        return self.find(f"{DATA_DIR}/files/me")

    @property
    def me_jpg(self) -> Path | None:
        return self.find(f"{DATA_DIR}/files/me.jpg")
