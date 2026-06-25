import os
import json
import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import boto3

app = FastAPI(title="Mini City Brain API")

BUCKET_NAME = "mini-city-brain-storage-20260624081121020000000001"

s3_client = boto3.client(
    "s3",
    aws_access_key_id="test",
    aws_secret_access_key="test",
    region_name="us-east-1",
    endpoint_url="http://host.docker.internal:4566",
)


class TrafficRecord(BaseModel):
    sensor_id: str
    vehicle_count: int
    average_speed: float
    junction_name: str


@app.get("/")
def read_root():
    return {"status": "online", "storage_target": BUCKET_NAME}


@app.post("/api/v1/traffic")
async def receive_traffic_data(data: TrafficRecord):
    try:
        payload = data.dict()
        timestamp = datetime.datetime.utcnow().isoformat()
        payload["processed_at"] = timestamp

        json_data = json.dumps(payload)
        file_name = (
            f"traffic-data/{payload['sensor_id']}-"
            f"{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}.json"
        )

        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=file_name,
            Body=json_data,
            ContentType="application/json",
        )

        print(f"Uploaded s3://{BUCKET_NAME}/{file_name}")

        return {
            "status": "success",
            "cloud_destination": f"s3://{BUCKET_NAME}/{file_name}",
        }

    except Exception as e:
        print(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
