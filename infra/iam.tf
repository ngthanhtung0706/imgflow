# Phụ trách: Phong – Hạng mục 5 (IAM role, không nhúng khoá)
# LÀM ĐẦU TIÊN: Thanh và Tùng cần instance profile để bật máy.
#
# CẦN LÀM:
# [ ] Role web + aws_iam_instance_profile.web:
#     AmazonSSMManagedInstanceCore; s3:PutObject bucket originals;
#     secretsmanager:GetSecretValue secret DB
# [ ] Role worker + aws_iam_instance_profile.worker:
#     AmazonSSMManagedInstanceCore; s3:GetObject originals; s3:PutObject processed;
#     sqs:ReceiveMessage/DeleteMessage/ChangeMessageVisibility/GetQueueAttributes;
#     secretsmanager:GetSecretValue
# [ ] Không dùng Resource "*" (trừ policy SSM có sẵn)
#
# XONG KHI: có 2 instance profile; máy gắn role vào được SSM.
