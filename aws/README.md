# CloudSage Terraform test resource

This directory contains one intentionally small EC2 test resource: an
`aws_instance.cloudsage_test` using `t3.micro`. CloudSage reads its local
Terraform state with the read-only command `terraform show -json` and matches
the state `id` to the AWS instance ID.

## Safe setup

```bash
cd /home/bob/projects/cloudsage/aws
# Edit terraform.tfvars once if the AMI needs to change.
terraform init
terraform validate
terraform plan
```

Terraform automatically loads `terraform.tfvars`, so subsequent `plan` and
`apply` commands do not prompt for `ami_id` or `aws_region`.

Do not run `terraform apply` until the instance has been reviewed. The
CloudSage application never runs Terraform apply.

After an approved, separately executed test deployment, restart CloudSage and
open the matching instance. The recommendation must be approved before the
Terraform diff button appears. The local state then supplies the resource
address instead of relying on the old demo mapping.
