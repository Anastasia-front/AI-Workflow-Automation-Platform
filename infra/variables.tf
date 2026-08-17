variable "aws_region" {
  type = string
}

variable "project_name" {
  type = string
}

variable "key_name" {
  type = string
}

variable "ssh_allowed_cidrs" {
  description = "IPs allowed to SSH"
  type        = list(string)
}

variable "frontend_security_group_id" {
  description = "Frontend EC2 Security Group ID allowed to reach the backend over private VPC networking."
  type        = string
}

variable "backend_public_http_allowed_cidrs" {
  description = "CIDR ranges allowed to reach the backend public HTTP endpoint."
  type        = list(string)
  default     = []
}

variable "ec2_ami" {
  type = string
}

variable "backend_enable_private_dns" {
  description = "Create a Route 53 private DNS record for the backend FastAPI EC2 instance."
  type        = bool
  default     = false
}

variable "backend_private_dns_zone_name" {
  description = "Route 53 private hosted zone name for backend internal DNS."
  type        = string
  default     = "ai-platform.internal"
}

variable "backend_private_dns_record_name" {
  description = "Route 53 private DNS record name for the backend FastAPI service."
  type        = string
  default     = "backend"
}

variable "ollama_enabled" {
  description = "Whether to create the Ollama EC2 instance and related resources. Set to false to tear it down without deleting the module config."
  type        = bool
  default     = true
}

variable "ollama_instance_type" {
  #  description = "EC2 GPU instance type used by Ollama."
  type = string
  #  default     = "g5.xlarge"
}

variable "ollama_associate_public_ip_address" {
  description = "Assign a public IP to the Ollama instance for bootstrap internet access. Keep false when using a private subnet with NAT."
  type        = bool
  default     = true
}

variable "ollama_root_volume_size" {
  description = "Root EBS volume size in GiB for the Ollama instance."
  type        = number
  default     = 80
}

variable "ollama_data_volume_size" {
  description = "Persistent Ollama model/data EBS volume size in GiB."
  type        = number
  default     = 250
}

variable "ollama_models" {
  description = "Ollama models to pre-pull during instance bootstrap."
  type        = list(string)
  default     = ["llama3.1:8b", "nomic-embed-text"]
}

variable "ollama_enable_private_dns" {
  description = "Create ollama.internal as a private Route 53 record in the existing VPC."
  type        = bool
  default     = true
}

variable "db_username" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "google_client_id" {
  type        = string
  description = "OAuth client ID used by the backend to verify Google ID tokens."
}

variable "env_values" {
  type = map(string)

  sensitive = true
}

variable "nginx_origin_certificate" {
  type        = string
  description = "Cloudflare Origin Certificate for the backend docs Nginx origin, supplied through Terraform variables or updated directly in SSM."
  sensitive   = true
}

variable "nginx_origin_certificate_version" {
  type        = number
  description = "Increment when rotating nginx_origin_certificate because value_wo is write-only."
  default     = 1
}

variable "nginx_origin_private_key" {
  type        = string
  description = "Cloudflare Origin private key for the backend docs Nginx origin, supplied through Terraform variables or updated directly in SSM."
  sensitive   = true
}

variable "nginx_origin_private_key_version" {
  type        = number
  description = "Increment when rotating nginx_origin_private_key because value_wo is write-only."
  default     = 1
}
