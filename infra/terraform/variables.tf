variable "endpoint_url" {
  description = "URL of the local AWS emulator. Inside compose this is http://emulator:5000."
  type        = string
  default     = "http://localhost:5000"
}

variable "region" {
  type    = string
  default = "ap-southeast-2"
}

variable "raw_bucket" {
  type    = string
  default = "mcb-raw-readings"
}

variable "curated_bucket" {
  type    = string
  default = "mcb-curated-exports"
}

variable "ingest_queue_name" {
  type    = string
  default = "mcb-ingest"
}

variable "dead_letter_queue_name" {
  type    = string
  default = "mcb-ingest-dlq"
}

variable "visibility_timeout_seconds" {
  description = "How long a received message stays hidden. A failed message returns after this."
  type        = number
  default     = 30
}
