import argparse
import base64
import os
from pprint import pprint
from typing import List, NamedTuple, Optional, cast
from venv import create


from oort_tools.email.standard_email import SES_IDENTITY_HEADER, StandardEmail, BodyChunk
import oort_tools.aws

import email.message
import email.utils


# Defaults are hardcoded but configurable via env and CLI args
DEFAULT_IDENTITY = os.getenv('OORT_DEFAULT_IDENTITY') or 'arn:aws:ses:us-east-1:370059773792:identity/sufitchi.name'
DEFAULT_SENDER = os.getenv("OORT_DEFAULT_SENDER") or "no-reply@sufitchi.name"
ENCODING = "utf-8"


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send an email using AWS SES")
    parser.add_argument(
        "recipient", metavar="to_email", nargs="+", help="recipients of the email"
    )
    parser.add_argument("subject", help="subject of the email")

    parser.add_argument(
        "-f",
        "--from",
        metavar="SENDER_EMAIL",
        default=DEFAULT_SENDER,
        help="sender of the email; default: %r" % DEFAULT_SENDER,
    )

    parser.add_argument(
        '--identity',
        metavar='ARN',
        default=DEFAULT_IDENTITY,
        help='ARN of AWS SES identity to use for sending authorization',
    )

    body_grp = parser.add_argument_group(
        "body contents",
        "MODE can be one of RAW, FILE, or STDIN (maximum used only once); "
        "SRC can (respectively) be raw text, a file path, or empty (STDIN has no src so it is ignored)",
    )
    body_grp.add_argument(
        "-T",
        "--text",
        nargs=2,
        metavar=("MODE", "SRC"),
        help="text alternative content block",
    )
    body_grp.add_argument(
        "-H",
        "--html",
        nargs=2,
        metavar=("MODE", "SRC"),
        help="HTML alternative content block",
    )
    body_grp.add_argument(
        "-A",
        "--attachment",
        action="append",
        nargs=4,
        metavar=("MODE", "FILENAME", "MIMETYPE", "SRC"),
        help="attachment, added to the end of the message; set MIMETYPE to 'AUTO' to guess",
    )

    return parser


def _email_from_args(args: argparse.Namespace) -> StandardEmail:
    subject = args.subject
    if not isinstance(args.subject, str) or not subject:
        raise ValueError("invalid subject: %r", args.subject)

    sender = getattr(args, "from") or DEFAULT_SENDER
    if not isinstance(sender, str) or not sender:
        raise ValueError("invalid sender: %r" % sender)

    ses_identity = getattr(args, 'identity') or DEFAULT_IDENTITY
    if not isinstance(ses_identity, str) or not ses_identity:
        raise ValueError('invalid SES identity: %r' % ses_identity)

    recipients: List[str] = []
    for recipient in args.recipient:
        if not isinstance(recipient, str) or not recipient:
            raise ValueError("invalid recipient: %r" % recipient)
        recipients.append(recipient)
    if not recipients:
        raise ValueError("no recipients found")

    stdin_count: int = 0

    text_chunk: Optional[BodyChunk] = None
    if args.text:
        input_mode, input_value = args.text
        if not isinstance(input_mode, str) or input_mode not in (
            "RAW",
            "FILE",
            "STDIN",
        ):
            raise ValueError("invalid body contents mode: %s" % input_mode)

        if not isinstance(input_value, str) or not input_value:
            raise ValueError("invalid body contents value: %s" % input_value)

        text_chunk = BodyChunk.from_args("text", input_mode, input_value)
        stdin_count += text_chunk.is_stdin

    html_chunk: Optional[BodyChunk] = None
    if args.html:
        input_mode, input_value = args.html
        if not isinstance(input_mode, str) or input_mode not in (
            "RAW",
            "FILE",
            "STDIN",
        ):
            raise ValueError("invalid body contents mode: %s" % input_mode)

        if not isinstance(input_value, str) or not input_value:
            raise ValueError("invalid body contents value: %s" % input_value)

        html_chunk = BodyChunk.from_args("html", input_mode, input_value)
        stdin_count += html_chunk.is_stdin


    attachment_chunks: List[BodyChunk] = []
    for input_mode, attachment_filename, attachment_mimetype, input_value in (
        args.attachment or []
    ):
        if not isinstance(input_mode, str) or input_mode not in (
            "RAW",
            "FILE",
            "STDIN",
        ):
            raise ValueError("invalid body contents mode: %s" % input_mode)

        if not isinstance(input_value, str) or not input_value:
            raise ValueError("invalid body contents value: %s" % input_value)

        chunk = BodyChunk.from_args(
            "attachment",
            input_mode,
            input_value,
            filename=attachment_filename,
            force_mimetype=attachment_mimetype,
        )
        attachment_chunks.append(chunk)

        stdin_count += chunk.is_stdin

    if stdin_count > 1:
        raise ValueError('more than 1 chunk is trying to use STDIN for input')

    if not (text_chunk or html_chunk):
        raise ValueError("input does not contain any message body")

    return StandardEmail(
        subject=subject,
        sender=sender,
        ses_identity=ses_identity,
        recipients=recipients,
        text_chunk=text_chunk,
        html_chunk=html_chunk,
        attachments=attachment_chunks,
    )


def _ses_send(email_message: email.message.Message) -> None:
    session = oort_tools.aws.create_session()

    from_str = str(email_message["From"])
    to_addresses = [
        email.utils.formataddr((name, addr))
        for name, addr in email.utils.getaddresses(email_message["To"].split(", "))
    ]

    # header_bytes, body_bytes = email_message.as_bytes().split(b'\n\n', 1)
    # from email import base64mime
    # raw_data = b''.join([
    #     header_bytes,
    #     b'\n\n',
    #     base64mime.body_encode(body_bytes).encode(),
    # ])

    # print(raw_data.decode())

    response = session.client("sesv2").send_email(
        FromEmailAddress=from_str,
        FromEmailAddressIdentityArn=email_message[SES_IDENTITY_HEADER],
        ReplyToAddresses=[from_str],
        Destination={"ToAddresses": to_addresses},
        Content={"Raw": {"Data": email_message.as_string()}},
    )
    pprint(response)


def main() -> None:
    parser = _build_argument_parser()
    args = parser.parse_args()
    email = _email_from_args(args)
    _ses_send(email.email_message)
