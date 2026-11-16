output "raw_bucket" {
  value = aws_s3_bucket.raw.bucket
}

output "curated_bucket" {
  value = aws_s3_bucket.curated.bucket
}

output "ingest_queue_name" {
  value = aws_sqs_queue.ingest.name
}

output "ingest_queue_url" {
  value = aws_sqs_queue.ingest.url
}

output "dead_letter_queue_name" {
  value = aws_sqs_queue.dead_letter.name
}

output "dead_letter_queue_url" {
  value = aws_sqs_queue.dead_letter.url
}
