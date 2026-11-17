# Phụ trách: Tùng – Hạng mục 3, 6
#
# CẦN LÀM:
# [ ] Launch template: Amazon Linux 2023, t3.small, KHÔNG IP public, IMDSv2,
#     SG aws_security_group.worker.id, instance profile aws_iam_instance_profile.worker
# [ ] User data: cài Python + Pillow + amazon-efs-utils, mount EFS vào /mnt/efs,
#     tải code app/worker, chạy service
# [ ] ASG worker: subnet aws_subnet.worker[*].id, min 1 / max 4 / desired 1
# [ ] Step scaling theo ApproximateNumberOfMessagesVisible của queue jobs:
#     >= 20 -> +2 máy, >= 100 -> +3 máy; < 5 trong 5 phút -> -1 máy
#
# XONG KHI: đẩy 200 ảnh thì worker tăng 1 -> 4, hàng đợi về 0, rồi tự giảm lại 1.
