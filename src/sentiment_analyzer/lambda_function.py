import json
import os
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3

s3 = boto3.client("s3")
comprehend = boto3.client("comprehend")
sqs = boto3.client("sqs")

HIGH_PRIORITY_QUEUE_URL = os.environ["HIGH_PRIORITY_QUEUE_URL"]
NORMAL_QUEUE_URL = os.environ["NORMAL_QUEUE_URL"]

MOVE_TO_PROCESSED = os.environ.get("MOVE_TO_PROCESSED", "false").lower() == "true"
PROCESSED_PREFIX = os.environ.get("PROCESSED_PREFIX", "processed/")
MAX_BYTES = 5000


def _truncate_utf8_bytes(text: str, max_bytes: int) -> str:
    data = text.encode("utf-8")
    if len(data) <= max_bytes:
        return text
    return data[:max_bytes].decode("utf-8", errors="ignore")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _route_queue(sentiment: str):
    if sentiment == "NEGATIVE":
        return HIGH_PRIORITY_QUEUE_URL, "HighPriorityQueue", "HIGH"
    return NORMAL_QUEUE_URL, "NormalQueue", "NORMAL"


def lambda_handler(event, context):
    results = []

    try:
        records = event.get("Records", [])
        if not records:
            return {"statusCode": 400, "body": json.dumps({"error": "No Records in event"})}

        for record in records:
            key = "unknown"
            try:
                s3_event = record["s3"]
                bucket = s3_event["bucket"]["name"]
                key = unquote_plus(s3_event["object"]["key"])

                obj = s3.get_object(Bucket=bucket, Key=key)
                body_bytes = obj["Body"].read()

                try:
                    text = body_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    print(f"Skipping non-UTF8 object: {key}")
                    results.append({"file": key, "status": "skipped_non_utf8"})
                    continue

                if not text.strip():
                    print(f"Skipping empty object: {key}")
                    results.append({"file": key, "status": "empty_file"})
                    continue

                text_for_analysis = _truncate_utf8_bytes(text, MAX_BYTES)
                response = comprehend.detect_sentiment(
                    Text=text_for_analysis,
                    LanguageCode="en",
                )

                sentiment = response["Sentiment"]
                scores = response["SentimentScore"]

                message_body = {
                    "s3_bucket": bucket,
                    "s3_key": key,
                    "sentiment": sentiment,
                    "sentiment_scores": {
                        "positive": float(scores["Positive"]),
                        "negative": float(scores["Negative"]),
                        "neutral": float(scores["Neutral"]),
                        "mixed": float(scores["Mixed"]),
                    },
                    "preview": text[:300],
                    "timestamp": _now_iso(),
                }

                queue_url, queue_name, priority = _route_queue(sentiment)
                sqs_response = sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps(message_body),
                    MessageAttributes={
                        "Sentiment": {"StringValue": sentiment, "DataType": "String"},
                        "S3Key": {"StringValue": key, "DataType": "String"},
                    },
                )

                if MOVE_TO_PROCESSED:
                    relative_key = key.split("/", 1)[-1]
                    destination_key = f"{PROCESSED_PREFIX}{relative_key}"
                    s3.copy_object(
                        Bucket=bucket,
                        CopySource={"Bucket": bucket, "Key": key},
                        Key=destination_key,
                    )
                    s3.delete_object(Bucket=bucket, Key=key)

                results.append(
                    {
                        "file": key,
                        "queue": queue_name,
                        "priority": priority,
                        "sentiment": sentiment,
                        "message_id": sqs_response["MessageId"],
                    }
                )

            except Exception as exc:
                print(f"Error processing {key}: {exc}")
                results.append({"file": key, "error": str(exc)})

        status = 207 if any("error" in result for result in results) else 200
        return {"statusCode": status, "body": json.dumps({"results": results})}

    except Exception as exc:
        print(f"Fatal handler error: {exc}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "handler_error", "details": str(exc)}),
        }
