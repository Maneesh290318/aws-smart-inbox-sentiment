# AWS Smart Inbox Sentiment

A serverless, event-driven customer-support workflow that automatically analyzes incoming messages with **Amazon Comprehend** and routes them by urgency using **Amazon SQS**.

The project demonstrates how managed AWS services can be combined into an AI-enabled workflow without provisioning application servers.

## Architecture

```text
Customer Message (.txt)
        |
        v
Amazon S3 /incoming
        |
        | ObjectCreated event
        v
SentimentAnalyzer Lambda
        |
        +--------------------> Amazon Comprehend
        |                       sentiment + confidence scores
        |
        v
Sentiment Routing
   +-------------------------+
   |                         |
NEGATIVE          POSITIVE / NEUTRAL / MIXED
   |                         |
   v                         v
HighPriorityQueue         NormalQueue
   |                         |
   +-----------+-------------+
               |
               v
    SmartInboxResultsReader
             Lambda
               |
               v
          API Gateway
               |
               v
       CloudFront + S3
        Web Dashboard

Monitoring: Amazon CloudWatch
Security: AWS IAM + private S3 origins
```

## Problem

Customer-support teams can receive large volumes of messages with different urgency levels. Manually reviewing every message before prioritization increases response time for complaints that may require immediate attention.

Smart Inbox automates the first classification step:

- customer messages arrive as text files;
- S3 events invoke Lambda automatically;
- Amazon Comprehend detects sentiment;
- negative messages are routed to a high-priority queue;
- positive, neutral, and mixed messages are routed to a normal queue;
- a lightweight API and dashboard expose recent classified results.

## AWS Services

| Service | Responsibility |
|---|---|
| Amazon S3 | Incoming message storage and static frontend origin |
| AWS Lambda | Event processing and read-only results API |
| Amazon Comprehend | Managed NLP sentiment detection |
| Amazon SQS | Asynchronous priority routing |
| Amazon API Gateway | HTTP endpoint for dashboard results |
| Amazon CloudFront | HTTPS delivery of the static dashboard |
| Amazon CloudWatch | Lambda logging and operational monitoring |
| AWS IAM | Least-privilege service permissions |

## Processing Flow

1. Upload a UTF-8 `.txt` message to the S3 `incoming/` prefix.
2. An S3 `ObjectCreated` event invokes `SentimentAnalyzerFunction`.
3. Lambda retrieves and validates the object.
4. Input is safely limited to the synchronous Comprehend sentiment API's 5,000-byte input limit.
5. Amazon Comprehend returns `POSITIVE`, `NEGATIVE`, `NEUTRAL`, or `MIXED` plus class scores.
6. Lambda builds a compact JSON result containing an S3 pointer, preview, sentiment scores, and timestamp.
7. `NEGATIVE` results are sent to `HighPriorityQueue`; all other results go to `NormalQueue`.
8. `SmartInboxResultsReader` reads recent queue messages through API Gateway.
9. The CloudFront-hosted frontend polls `GET /results` and displays the two priority feeds.

## Repository Structure

```text
aws-smart-inbox-sentiment/
├── src/
│   ├── sentiment_analyzer/
│   │   └── lambda_function.py
│   └── results_reader/
│       └── lambda_function.py
├── frontend/
│   └── index.html
├── infrastructure/
│   └── iam/
│       ├── sentiment-analyzer-policy.json
│       └── results-reader-policy.json
├── sample-data/
│   ├── s3-event.json
│   ├── negative-message.txt
│   └── positive-message.txt
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Key Engineering Decisions

### Event-driven ingestion

S3 invokes the analyzer only when a new object arrives. A deployment should configure the event notification with the `incoming/` prefix and `.txt` suffix so unrelated objects do not invoke the function.

### Managed NLP instead of a hosted model

Amazon Comprehend provides sentiment inference without managing model servers, endpoints, scaling, or ML infrastructure.

### Asynchronous routing

SQS decouples classification from downstream customer-support processing. Separate queues make priority explicit and allow consumers to scale independently.

### Environment-based configuration

Queue URLs and deployment-specific settings are read from environment variables instead of being hard-coded in the Lambda functions.

### Least-privilege IAM

The templates in `infrastructure/iam/` intentionally avoid broad managed policies such as `AmazonSQSFullAccess`. The analyzer receives only the S3, Comprehend, and SQS actions needed for this workflow.

### Defensive input handling

The analyzer handles empty files and non-UTF-8 content and limits Comprehend input by UTF-8 bytes rather than Python character count.

## Configuration

The analyzer requires:

```text
HIGH_PRIORITY_QUEUE_URL
NORMAL_QUEUE_URL
```

Optional analyzer configuration:

```text
MOVE_TO_PROCESSED=false
PROCESSED_PREFIX=processed/
```

The results-reader also supports:

```text
ALLOWED_ORIGIN=https://YOUR_CLOUDFRONT_DOMAIN
```

Use `.env.example` only as a configuration reference. AWS Lambda environment variables should be configured in the deployment environment.

## Test Scenarios

### Negative complaint

Upload `sample-data/negative-message.txt` to the S3 `incoming/` prefix.

Expected path:

```text
S3 → Lambda → Comprehend: NEGATIVE → HighPriorityQueue
```

### Positive feedback

Upload `sample-data/positive-message.txt`.

Expected path:

```text
S3 → Lambda → Comprehend: POSITIVE → NormalQueue
```

### Empty input

An empty text object is detected and skipped without sending a queue message.

### Non-text objects

Configure the S3 notification suffix as `.txt`; objects such as images should not invoke the analyzer.

## Dashboard

The static frontend displays:

- high-priority messages;
- normal-priority messages;
- detected sentiment;
- sentiment scores;
- a short message preview;
- processing timestamp.

Before deployment, replace the placeholder `API_BASE` in `frontend/index.html` with the API Gateway base URL and configure API Gateway CORS for the CloudFront origin.

## Demo vs. Production Behavior

The results-reader intentionally **does not delete SQS messages**. This mirrors the original demonstration workflow so results remain inspectable in the SQS console.

For a production system, the read path should not use an operational queue as a persistent UI datastore. A stronger architecture would consume queue messages once and persist results to a datastore such as DynamoDB, with the dashboard API reading from that datastore.

## Production Improvements

The next iteration would add:

- SQS dead-letter queues and retry/redrive policies;
- DynamoDB persistence for processed results;
- idempotency to handle duplicate S3 event delivery safely;
- AWS SAM, CDK, CloudFormation, or Terraform infrastructure as code;
- automated unit/integration tests;
- CloudWatch alarms and structured operational metrics;
- API authorization and rate controls where appropriate;
- CI/CD with GitHub Actions;
- retention/lifecycle policies for S3 objects and logs.

## Security

This repository contains placeholders rather than account-specific resource identifiers.

Do **not** commit:

- AWS access keys or secret keys;
- AWS account IDs;
- real queue URLs;
- sensitive ARNs;
- customer messages containing personal or confidential information;
- local `.env` files.

The frontend S3 bucket should remain private and be accessed through CloudFront origin access controls.

## What This Project Demonstrates

- Event-driven serverless architecture
- Managed AI/NLP integration
- Asynchronous messaging
- Sentiment-based routing
- Lambda/API integration
- Static cloud frontend delivery
- IAM least-privilege design
- CloudWatch-based observability
- Defensive handling of application inputs

## Roadmap

- [x] S3 event-driven ingestion
- [x] Lambda sentiment processing
- [x] Amazon Comprehend integration
- [x] Sentiment-based SQS routing
- [x] API Gateway results endpoint
- [x] S3 + CloudFront dashboard
- [x] CloudWatch logging
- [x] Least-privilege IAM templates
- [ ] DynamoDB result persistence
- [ ] Dead-letter queues
- [ ] Infrastructure as Code
- [ ] Automated tests
- [ ] CI/CD pipeline

## Portfolio Context

Smart Inbox complements my work in data engineering, analytics, RAG, and agentic AI by demonstrating an end-to-end **AWS-native AI application** spanning ingestion, managed inference, asynchronous routing, APIs, monitoring, security, and frontend delivery.
