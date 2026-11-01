variable "aws_region" {
  type        = string
  description = "AWS region where the test instance is created."
  default     = "us-east-1"
}

variable "ami_id" {
  type        = string
  description = "A valid Linux AMI ID for the selected region."
}

resource "aws_instance" "cloudsage_test" {
  ami           = var.ami_id
  instance_type = "t3.micro"

  tags = {
    Name    = "cloudsage-test"
    Purpose = "cloudsage-validation"
  }
}

output "instance_id" {
  value       = aws_instance.cloudsage_test.id
  description = "The EC2 instance ID discovered by CloudSage."
}
