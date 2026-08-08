"""Strip live credentials out of a newman htmlextra report before publishing it.

The htmlextra reporter records full request/response bodies and headers,
including the Bearer JWTs and test passwords the collection generates while
running -- fine for a private CI artifact, not fine to publish on a public
page. Run this on the generated report before it goes anywhere public.

Usage: python3 redact_report.py <input.html> <output.html>
"""

import re
import sys

# 3-part JWT (header.payload.signature), matches both `Bearer eyJ...` request
# headers and `"access_token":"eyJ..."` / `"refresh_token":"eyJ..."` response
# bodies -- the token shape doesn't change between those two contexts.
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

# The collection's Register pre-request script generates passwords shaped
# like "Passw0rd!<digits>" (see postman_collection.json) -- redact those
# specifically rather than every occurrence of the word "password".
GENERATED_PASSWORD_RE = re.compile(r"Passw0rd![0-9]+")


def redact(html: str) -> str:
    html = JWT_RE.sub("***REDACTED-JWT***", html)
    html = GENERATED_PASSWORD_RE.sub("***REDACTED-PASSWORD***", html)
    return html


def main() -> None:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <input.html> <output.html>", file=sys.stderr)
        raise SystemExit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    with open(input_path, encoding="utf-8") as f:
        html = f.read()

    redacted = redact(html)

    jwt_remaining = len(JWT_RE.findall(redacted))
    if jwt_remaining:
        print(f"warning: {jwt_remaining} JWT-shaped strings survived redaction", file=sys.stderr)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(redacted)

    print(f"Redacted {input_path} -> {output_path}")


if __name__ == "__main__":
    main()
