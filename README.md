# Mini City Brain

A proof-of-concept backend that ingests mock traffic sensor data and streams it to object storage. Built with FastAPI and containerized with Docker, with infrastructure provisioned via Terraform against a LocalStack-backed AWS environment.

## Architecture

```
Traffic Client → FastAPI (Docker) → S3 (LocalStack)
                        ↑
              Terraform (S3, EC2, Security Group)
```

| Component | Role |
|-----------|------|
| **FastAPI** | REST API exposing `POST /api/v1/traffic` for traffic sensor payloads |
| **Docker** | Packages the application with its Python dependencies |
| **Terraform** | Provisions S3 bucket, EC2 instance, and security group |
| **LocalStack** | Local AWS emulator (S3 on port 4566) for development and testing |
| **Boto3** | AWS SDK used by the API to write JSON objects to S3 |

Incoming traffic records are validated, timestamped, and written to S3 under `traffic-data/{sensor_id}-{timestamp}.json`.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.0
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) (for verifying S3 uploads)

## Quick Start

### 1. Start LocalStack

```bash
docker run -d \
  --name localstack \
  -p 4566:4566 \
  -e SERVICES=s3,ec2,sts \
  localstack/localstack
```

### 2. Provision infrastructure

```bash
terraform init
terraform apply -auto-approve
```

Note the `s3_bucket_name` output and update `BUCKET_NAME` in `main.py` if it differs from the value already configured.

### 3. Build and run the API

```bash
docker build -t mini-city-brain .
docker run -d --name mini-city-brain -p 8000:8000 mini-city-brain
```

### 4. Send test traffic data

```bash
curl -X POST http://localhost:8000/api/v1/traffic \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_id": "sensor-001",
    "vehicle_count": 42,
    "average_speed": 35.5,
    "junction_name": "Collins & Swanston"
  }'
```

Expected response:

```json
{
  "status": "success",
  "cloud_destination": "s3://<bucket>/traffic-data/sensor-001-<timestamp>.json"
}
```

### 5. Verify the S3 upload

```bash
aws --endpoint-url=http://localhost:4566 s3 ls s3://<bucket>/traffic-data/
```

Replace `<bucket>` with your Terraform output value.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check; returns service status and target bucket |
| `POST` | `/api/v1/traffic` | Ingest a traffic sensor record |

### Request body (`POST /api/v1/traffic`)

| Field | Type | Description |
|-------|------|-------------|
| `sensor_id` | string | Unique sensor identifier |
| `vehicle_count` | integer | Number of vehicles detected |
| `average_speed` | float | Average speed in km/h |
| `junction_name` | string | Intersection or junction label |

## Project Structure

```
.
├── main.py           # FastAPI application
├── requirements.txt  # Python dependencies
├── Dockerfile        # Container image definition
├── main.tf           # Terraform infrastructure
└── README.md
```

## License

See [LICENSE.txt](LICENSE.txt).
