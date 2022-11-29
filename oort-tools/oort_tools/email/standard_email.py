from __future__ import annotations

import base64
import codecs
import email.headerregistry
import email.message
import email.base64mime
import email.encoders
from functools import lru_cache
import io
import email.mime
import email.mime.nonmultipart
import email.mime.multipart
import email.mime.text
import email.utils
import pathlib
import email.mime.base
import sys
from dataclasses import dataclass
from typing import BinaryIO, Iterable, List, Literal, Optional, Sequence, Tuple

import magic
from chardet.universaldetector import UniversalDetector

SES_IDENTITY_HEADER = 'X-Oort-SES-Identity'

@dataclass(frozen=True)
class StandardEmail:
    subject: str
    sender: str
    ses_identity: str
    recipients: Sequence[str]
    text_chunk: Optional[BodyChunk]
    html_chunk: Optional[BodyChunk]
    attachments: Sequence[BodyChunk]

    @property
    def email_message(self) -> email.message.Message:
        message = email.message.EmailMessage()
        message["Subject"] = self.subject
        message["From"] = self.sender
        message["To"] = ', '.join(self.recipients)
        message[SES_IDENTITY_HEADER] = self.ses_identity
        message.make_alternative()

        if self.text_chunk:
            message.attach(self.text_chunk.build_text_part())

        if self.html_chunk:
            message.attach(self.html_chunk.build_html_part())

        for chunk in self.attachments:
            # byts = b''.join(chunk.bytes_iter)
            message.attach(chunk.build_attachment_part())

        print(message.as_string())

        return message


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
        message = email.message.EmailMessage()
        body = b"".join(self.bytes_iter)
        message.set_content(body, 'text', 'plain')
        return message

    def build_html_part(self) -> email.message.Message:
        message = email.message.EmailMessage()
        body = b"".join(self.bytes_iter)
        message.set_content(body, 'text', 'html')
        return message

    def build_attachment_part(self) -> email.message.Message:
        maintype, subtype = self.mimetype.split('/', 1)
        message = email.mime.base.MIMEBase(maintype, subtype)
        message.add_header("Content-Disposition", "attachment", filename=self.filename)
        message.set_type(self.mimetype)
        if self.charset:
            message.set_charset(self.charset)
        message.set_payload(b''.join(self.bytes_iter))
        email.encoders.encode_base64(message)
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
