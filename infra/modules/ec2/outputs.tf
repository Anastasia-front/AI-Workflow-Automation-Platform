output "instance_id" {
  value = aws_instance.api.id
}

output "public_ip" {
  value = aws_eip.api.public_ip
}

output "private_ip" {
  value = aws_instance.api.private_ip
}

output "elastic_ip" {
  value = aws_eip.api.public_ip
}

output "elastic_ip_allocation_id" {
  value = aws_eip.api.id
}
