import io
from google import genai
from google.genai import types
from utils.utils import DEFAULT_MODEL

MIME_TO_KIND = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
    "application/pdf": "pdf",
    "audio/mpeg": "audio",
    "audio/mp3": "audio",
    "audio/wav": "audio",
    "audio/x-wav": "audio",
    "audio/ogg": "audio",
    "audio/mp4": "audio",
    "audio/aac": "audio",
    "audio/webm": "audio",
    "video/mp4": "video",
    "video/mpeg": "video",
    "video/quicktime": "video",
    "video/x-msvideo": "video",
    "video/webm": "video",
}

EXT_TO_KIND = {
    "docx": "docx",
    "txt": "txt",
    "pdf": "pdf",
    "mp3": "audio", "wav": "audio", "ogg": "audio", "m4a": "audio", "aac": "audio",
    "mp4": "video", "mov": "video", "avi": "video", "webm": "video",
}

EXT_TO_MIME = {
    "pdf": "application/pdf",
    "mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg",
    "m4a": "audio/mp4", "aac": "audio/aac",
    "mp4": "video/mp4", "mov": "video/quicktime", "avi": "video/x-msvideo", "webm": "video/webm",
}

GEMINI_PROMPT = {
    "pdf": "Extract the full text content from this PDF document. Return only the extracted text, preserving structure.",
    "audio": "Transcribe this audio in full. Return only the transcript text.",
    "video": "Transcribe all spoken content from this video. Return only the transcript text.",
}


def extract_docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


async def extract_transcript(
    client: genai.Client,
    filename: str,
    content_type: str,
    data: bytes,
) -> str:
    kind = MIME_TO_KIND.get(content_type)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if kind is None:
        kind = EXT_TO_KIND.get(ext)

    if kind is None:
        raise ValueError(f"Unsupported file type '{content_type}' for '{filename}'")

    if kind == "txt":
        return data.decode("utf-8", errors="replace")

    if kind == "docx":
        return extract_docx(data)

    # Resolve to a concrete MIME type for Gemini (avoid application/octet-stream)
    resolved_mime = content_type if content_type in MIME_TO_KIND else EXT_TO_MIME.get(ext, content_type)

    response = await client.aio.models.generate_content(
        model=DEFAULT_MODEL,
        contents=[
            types.Part.from_bytes(data=data, mime_type=resolved_mime),
            GEMINI_PROMPT[kind],
        ],
    )
    return response.text
