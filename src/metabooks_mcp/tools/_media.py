"""Validação de mídia sem confiar no nome, rótulo ou Content-Type isoladamente."""

from io import BytesIO
from typing import BinaryIO
from zipfile import ZipFile, BadZipFile

from PIL import Image, ImageOps

from ..client import MetabooksError

MAX_IMAGE_PIXELS = 25_000_000


def _check_pixels(img):
    if img.width * img.height > MAX_IMAGE_PIXELS:
        raise MetabooksError("Imagem excede o limite de 25 milhões de pixels.")


def media_extension(file: BinaryIO, content_type: str = "") -> str:
    file.seek(0)
    head = file.read(512)
    ext = None
    if head.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")):
        file.seek(0)
        with Image.open(file) as img:
            _check_pixels(img)
            ext = {"JPEG": "jpg", "PNG": "png"}.get(img.format)
            img.verify()
    elif head.startswith(b"%PDF-"):
        file.seek(0, 2)
        file.seek(max(0, file.tell() - 4096))
        if b"%%EOF" in file.read():
            ext = "pdf"
    elif head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        ext = "wav"
    elif head[:3] == b"ID3" or (len(head) >= 4 and head[0] == 255 and head[1] & 0xE0 == 0xE0
                               and head[1] & 0x06 and head[2] & 0xF0 not in (0, 0xF0)):
        ext = "mp3"
    elif head.startswith(b"PK\x03\x04"):
        file.seek(0)
        try:
            with ZipFile(file) as archive:
                # Só lemos o mimetype minúsculo; nunca descompactamos o arquivo.
                info = archive.getinfo("mimetype")
                if info.file_size <= 64 and archive.read(info) == b"application/epub+zip":
                    ext = "epub"
        except (BadZipFile, KeyError, RuntimeError):
            pass
    if ext is None:
        raise MetabooksError("Arquivo de mídia inválido ou formato não suportado (JPEG, PNG, PDF, WAV, MP3 ou EPUB).")
    mime = content_type.split(";", 1)[0].strip().lower()
    expected = {
        "jpg": {"image/jpeg", "image/jpg"}, "png": {"image/png"},
        "pdf": {"application/pdf"}, "wav": {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"},
        "mp3": {"audio/mpeg", "audio/mp3"}, "epub": {"application/epub+zip", "application/zip"},
    }
    if mime and mime not in {"application/octet-stream", "binary/octet-stream", *expected[ext]}:
        raise MetabooksError("O tipo de conteúdo informado pela API não corresponde ao arquivo recebido.")
    file.seek(0)
    return ext


def downscale_to_jpeg(data: bytes, max_dim: int = 1024) -> bytes:
    with Image.open(BytesIO(data)) as img:
        _check_pixels(img)
        img.thumbnail((max_dim, max_dim))
        img = ImageOps.exif_transpose(img).convert("RGB")
        out = BytesIO()
        img.save(out, format="JPEG", quality=85, optimize=True)
        return out.getvalue()
