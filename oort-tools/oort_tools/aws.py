from typing import NamedTuple, Optional

import boto3

AWSCreds = NamedTuple(
    "AWSCreds",
    [
        ("key_id", str),
        ("secret_key", str),
        ("region", str),
    ],
)


def create_session(creds: Optional[AWSCreds] = None) -> boto3.Session:
    return (
        boto3.Session(creds.key_id, creds.secret_key, region_name=creds.region)
        if creds
        else boto3.Session()
    )
