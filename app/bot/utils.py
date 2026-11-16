from typing import List


def chunk_text(text: str, max_length: int = 4096) -> List[str]:
    """Splits long text into chunks within Telegram's message character limit."""
    if not text:
        return [""]
    if len(text) <= max_length:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        # Find clean newline or whitespace break
        split_at = text.rfind("\n", 0, max_length)
        if split_at == -1:
            split_at = text.rfind(" ", 0, max_length)
        if split_at == -1:
            split_at = max_length

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()

    return chunks


def truncate_caption(caption: str, max_length: int = 1024) -> str:
    """Truncates caption to fit within Telegram's media caption limit."""
    if not caption:
        return ""
    if len(caption) <= max_length:
        return caption
    return caption[:max_length - 3] + "..."
