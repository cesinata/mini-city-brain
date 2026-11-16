"""Create the buckets and queues with boto3. Fallback for the Terraform `init` service.

Usage: python -m scripts.init_resources
Reads AWS_ENDPOINT_URL and the resource names from the environment (see env.example).
"""

from __future__ import annotations

import json
from typing import Any

from services.common.aws import s3_client, sqs_client
from services.common.config import Settings


def create_resources(settings: Settings, sqs: Any | None = None, s3: Any | None = None) -> dict:
    sqs = sqs or sqs_client(settings)
    s3 = s3 or s3_client(settings)
    for bucket in (settings.raw_bucket, settings.curated_bucket):
        s3.create_bucket(
            Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": settings.region}
        )
    dlq_url = sqs.create_queue(
        QueueName=settings.dead_letter_queue_name,
        Attributes={"MessageRetentionPeriod": "1209600"},
    )["QueueUrl"]
    dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    ingest_url = sqs.create_queue(
        QueueName=settings.ingest_queue_name,
        Attributes={
            "VisibilityTimeout": str(settings.visibility_timeout),
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": 3}),
        },
    )["QueueUrl"]
    return {"ingest_queue_url": ingest_url, "dead_letter_queue_url": dlq_url}


if __name__ == "__main__":
    print(json.dumps(create_resources(Settings.from_env()), indent=2))
