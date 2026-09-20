import json
import os

import boto3

sqs = boto3.client("sqs")

HIGH_PRIORITY_QUEUE_URL = os.environ["HIGH_PRIORITY_QUEUE_URL"]
NORMAL_QUEUE_URL = os.environ["NORMAL_QUEUE_URL"]


def _read_from(queue_url: str, label: str):
    response = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=5,
        VisibilityTimeout=2,
        WaitTimeSeconds=1,
        MessageAttributeNames=["All"],
    )

    messages = []
    for message in response.get("Messages", []):
        body = json.loads(message["Body"])
        messages.append(
            {
                "queue": label,
                "sentiment": body.get("sentiment"),
                "scores": body.get("sentiment_scores"),
                "preview": body.get("preview"),
                "timestamp": body.get("timestamp"),
                "s3_bucket": body.get("s3_bucket"),
                "s3_key": body.get("s3_key"),
            }
        )

        # Demo behavior: messages are intentionally not deleted so the same
        # SQS entries can also be inspected in the AWS console.
        # Production consumers should define explicit acknowledgement/deletion
        # behavior and an appropriate retry/dead-letter strategy.

    return messages


def lambda_handler(event, context):
    messages = _read_from(HIGH_PRIORITY_QUEUE_URL, "HighPriorityQueue")
    messages += _read_from(NORMAL_QUEUE_URL, "NormalQueue")

    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": os.environ.get(
                "ALLOWED_ORIGIN", "https://example.com"
            ),
            "Content-Type": "application/json",
        },
        "body": json.dumps(messages),
    }
