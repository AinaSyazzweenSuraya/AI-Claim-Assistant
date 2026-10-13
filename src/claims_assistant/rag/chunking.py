import re


def chunks(text: str, metadata: dict) -> list[dict]:
    result = []
    section = "Overview"
    body = []
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            if body:
                result.append({**metadata, "section": section, "text": "\n".join(body).strip()})
            section, body = heading[1], []
        else:
            body.append(line)
    if body:
        result.append({**metadata, "section": section, "text": "\n".join(body).strip()})
    return result
