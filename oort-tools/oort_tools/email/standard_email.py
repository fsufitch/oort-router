from __future__ import annotations

import base64
import codecs
import email.headerregistry
import email.message
import io
import pathlib
import sys
from dataclasses import dataclass
from typing import BinaryIO, Iterable, List, Literal, Optional, Sequence, Tuple

import magic
from chardet.universaldetector import UniversalDetector


@dataclass(frozen=True)
class StandardEmail:
    subject: str
    sender: str
    recipients: Sequence[str]
    text_body_chunks: Sequence[BodyChunk]
    html_body_chunks: Sequence[BodyChunk]
    attachments: Sequence[BodyChunk]

    def build_email_message(self) -> email.message.Message:
        message = email.message.EmailMessage()
        message["Subject"] = self.subject

        message["From"] = self.sender
        message["To"] = self.recipients

        message.make_mixed()

        message.set_payload(
            [
                self._build_body(),
                *(a.build_attachment_part() for a in self.attachments),
            ]
        )

        return message

    def _build_body(self) -> email.message.Message:
        parts: List[email.message.Message] = []

        if len(self.text_body_chunks) == 1:
            parts.append(self.text_body_chunks[0].build_text_part())
        elif len(self.text_body_chunks) > 1:
            part = email.message.EmailMessage()
            part.make_mixed()
            part.set_payload([chunk.build_text_part() for chunk in self.text_body_chunks])
            parts.append(part)

        if len(self.html_body_chunks) == 1:
            parts.append(self.text_body_chunks[0].build_text_part())
        elif len(self.html_body_chunks) > 1:
            part = email.message.EmailMessage()
            part.make_mixed()
            part.set_payload([chunk.build_html_part() for chunk in self.text_body_chunks])
            parts.append(part)

        if not parts:
            raise ValueError("No text or HTML parts built")

        if len(parts) == 1:
            return parts[0]

        body = email.message.EmailMessage()
        body.make_alternative()
        body.set_payload(parts)
        return body


def _read(
    input_mode: Literal["RAW", "FILE", "STDIN"],
    src: str,
) -> Tuple[str, str, Iterable[bytes]]:
    """Reads from the specified src using the input mode; returns encoding of the bytes once it is detected; assumes sys.getdefaultencoding() for RAW and STDIN.

    Return type is (mimetype: str, encoding: str, bytes_iter: Iterable[bytes]"""

    if input_mode == "RAW":
        if not isinstance(src, str):
            raise ValueError("invalid RAW body; %r" % src)
        encoding_name = sys.getdefaultencoding()
        encoding = codecs.lookup(encoding_name)
        return "text/plain", encoding_name, [encoding.encode(src)[0]]

    elif input_mode == "STDIN":
        encoding_name = sys.getdefaultencoding()
        encoding = codecs.lookup(encoding_name)
        return "text/plain", encoding_name, (encoding.encode(s)[0] for s in sys.stdin)

    elif input_mode == "FILE":
        path = pathlib.Path(src).resolve()
        mimetype = magic.from_file(path, mime=True)
        with open(path, "rb") as fp:
            encoding_name = _chardet_detect_encoding(fp)
        return mimetype, encoding_name, open(path, "rb")

    raise ValueError("invalid input mode: %r" % input_mode)


@dataclass(frozen=True)
class BodyChunk:
    mimetype: str
    bytes_iter: Iterable[bytes]

    filename: str = ""
    charset: Optional[str] = ""
    is_stdin: bool = False

    def build_text_part(self) -> email.message.Message:
        message = email.message.Message()
        message.set_type("text/plain")
        if self.charset:
            message.set_charset(self.charset)
        body = b"".join(self.bytes_iter)
        message.set_payload(body)
        return message

    def build_html_part(self) -> email.message.Message:
        message = email.message.Message()
        message.set_type("text/html")
        if self.charset:
            message.set_charset(self.charset)
        body = b"".join(self.bytes_iter)
        message.set_payload(body)
        return message

    def build_attachment_part(self) -> email.message.Message:
        print(self)
        message = email.message.Message()
        message.add_header("Content-Disposition", "attachment", filename=self.filename)
        message.add_header('Content-Transfer-Encoding', 'base64')        
        message.set_type(self.mimetype)
        if self.charset:
            message.set_charset(self.charset)

        message.set_payload(base64.encodebytes(b''.join(self.bytes_iter)))
        return message

    @staticmethod
    def from_args(
        chunk_type: Literal["html", "text", "attachment"],
        input_mode: Literal["RAW", "FILE", "STDIN"],
        src: str,
        filename: str = '',
        force_mimetype: str = 'AUTO',
    ) -> BodyChunk:
        mimetype, charset, bytes_iter = _read(input_mode, src)

        if chunk_type == 'html':
            mimetype='text/html'
        if chunk_type == 'text':
            mimetype='text/plain'
    
        if force_mimetype != 'AUTO':
            mimetype = force_mimetype

        is_stdin = input_mode == "STDIN"

        return BodyChunk(
            mimetype=mimetype,
            bytes_iter=bytes_iter,
            charset=charset or None,
            is_stdin=input_mode == "STDIN",
            filename=filename,
        )


def _chardet_detect_encoding(fp: BinaryIO, max_bytes: int = 10_000_000) -> str:
    detector = UniversalDetector()
    scanned_bytes = 0
    for byts in fp:
        scanned_bytes += len(byts)
        detector.feed(byts)
        if detector.done or scanned_bytes > max_bytes:
            break
    return detector.close()["encoding"]
