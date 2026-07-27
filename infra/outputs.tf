output "backend_ec2_ip" {
  value = module.ec2.public_ip
}

output "backend_instance_id" {
  value = module.ec2.instance_id
}

output "backend_elastic_ip" {
  value = module.ec2.elastic_ip
}

output "backend_elastic_ip_allocation_id" {
  value = module.ec2.elastic_ip_allocation_id
}

output "backend_private_ip" {
  value = module.ec2.private_ip
}

output "backend_private_dns_name" {
  value = try(aws_route53_record.backend[0].fqdn, null)
}

output "backend_private_base_url" {
  value = var.backend_enable_private_dns ? "http://${trimsuffix(aws_route53_record.backend[0].fqdn, ".")}" : "http://${module.ec2.private_ip}"
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "s3_bucket" {
  value = module.s3.bucket_name
}

output "ecr_repository" {
  value = module.ecr.repository_url
}

output "ssm_prefix" {
  value = module.ssm.parameter_prefix
}

output "ollama_private_ip" {
  value = module.ollama.private_ip
}

output "ollama_elastic_ip" {
  value = module.ollama.elastic_ip
}

output "ollama_elastic_ip_allocation_id" {
  value = module.ollama.elastic_ip_allocation_id
}

output "ollama_private_dns_name" {
  value = module.ollama.private_dns_name
}

output "ollama_base_url" {
  value = module.ollama.base_url
}

output "ollama_security_group_id" {
  value = module.ollama.security_group_id
}

output "ollama_cloudwatch_log_group" {
  value = module.ollama.cloudwatch_log_group
}
