import argparse
import base64
import os
from pprint import pprint
from typing import List, NamedTuple, cast
from venv import create


from oort_tools.email.standard_email import StandardEmail, BodyChunk
import oort_tools.aws

import email.message
import email.utils


DEFAULT_SENDER = os.getenv("OORT_DEFAULT_SENDER") or "no-reply@home.sufitchi.name"
ENCODING = "utf-8"


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send an email using AWS SES")
    parser.add_argument("subject", help="subject of the email")
    parser.add_argument(
        "recipient", metavar="EMAIL", nargs="+", help="recipients of the email"
    )
    parser.add_argument(
        "-f",
        "--from",
        metavar="SENDER_EMAIL",
        help="sender of the email; default: %r" % DEFAULT_SENDER,
    )

    body_grp = parser.add_argument_group(
        "body contents; ",
        "MODE can be one of RAW, FILE, or STDIN (maximum used only once); "
        "SRC can (respectively) be raw text, a file path, or empty (STDIN has no src so it is ignored)",
    )
    body_grp.add_argument(
        "-T",
        "--text",
        action="append",
        nargs=2,
        metavar=("MODE", "SRC"),
        help="text alternative content block",
    )
    body_grp.add_argument(
        "-H",
        "--html",
        action="append",
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

    recipients: List[str] = []
    for recipient in args.recipient:
        if not isinstance(recipient, str) or not recipient:
            raise ValueError("invalid recipient: %r" % recipient)
        recipients.append(recipient)
    if not recipients:
        raise ValueError("no recipients found")

    using_stdin: bool = False

    text_chunks: List[BodyChunk] = []
    for input_mode, input_value in args.text or []:
        if not isinstance(input_mode, str) or input_mode not in (
            "RAW",
            "FILE",
            "STDIN",
        ):
            raise ValueError("invalid body contents mode: %s" % input_mode)

        if not isinstance(input_value, str) or not input_value:
            raise ValueError("invalid body contents value: %s" % input_value)

        chunk = BodyChunk.from_args("text", input_mode, input_value)
        text_chunks.append(chunk)

        if chunk.is_stdin:
            if using_stdin:
                # multiple chunks cannot use stdin
                raise ValueError("multiple inputs trying to use STDIN")
            using_stdin = True

    html_chunks: List[BodyChunk] = []
    for input_mode, input_value in args.html or []:
        if not isinstance(input_mode, str) or input_mode not in (
            "RAW",
            "FILE",
            "STDIN",
        ):
            raise ValueError("invalid body contents mode: %s" % input_mode)

        if not isinstance(input_value, str) or not input_value:
            raise ValueError("invalid body contents value: %s" % input_value)

        chunk = BodyChunk.from_args("html", input_mode, input_value)
        html_chunks.append(chunk)

        if chunk.is_stdin:
            if using_stdin:
                # multiple chunks cannot use stdin
                raise ValueError("multiple inputs trying to use STDIN")
            using_stdin = True

    attachment_chunks: List[BodyChunk] = []
    print(args.attachment)
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

        if chunk.is_stdin:
            if using_stdin:
                # multiple chunks cannot use stdin
                raise ValueError("multiple inputs trying to use STDIN")
            using_stdin = True

    if not (text_chunks or html_chunks):
        raise ValueError("input does not contain any message body")

    return StandardEmail(
        subject=subject,
        sender=sender,
        recipients=recipients,
        text_body_chunks=text_chunks,
        html_body_chunks=html_chunks,
        attachments=attachment_chunks,
    )


def _ses_send(email_message: email.message.Message) -> None:
    session = oort_tools.aws.create_session()

    from_str = str(email_message["From"])
    to_addresses = [
        email.utils.formataddr((name, addr))
        for name, addr in email.utils.getaddresses(email_message["To"].split(", "))
    ]
    b64_email = base64.encodebytes(email_message.as_bytes())

    print(to_addresses)

    response = session.client("sesv2").send_email(
        FromEmailAddress=from_str,
        Destination={"ToAddresses": to_addresses},
        Content={"Raw": {"Data": b64_email}},
    )
    pprint(response)


def main() -> None:
    parser = _build_argument_parser()
    args = parser.parse_args()
    email = _email_from_args(args)
    message = email.build_email_message()
    _ses_send(message)
