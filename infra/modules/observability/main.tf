terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_sns_topic" "alarms" {
  name = "${var.name_prefix}-alarms"
  tags = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == null ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

locals {
  alarm_actions = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${var.name_prefix}-alb-5xx"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 5
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
    TargetGroup  = var.gateway_target_group_arn_suffix
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "alb_unhealthy_hosts" {
  alarm_name          = "${var.name_prefix}-alb-unhealthy-hosts"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 3
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
    TargetGroup  = var.gateway_target_group_arn_suffix
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.name_prefix}-rds-cpu-high"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "rds_storage_low" {
  alarm_name          = "${var.name_prefix}-rds-storage-low"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 1
  threshold           = 2147483648
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "redis_cpu" {
  alarm_name          = "${var.name_prefix}-redis-cpu-high"
  namespace           = "AWS/ElastiCache"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 75
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    CacheClusterId = var.elasticache_cluster_id
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "ecs_cpu_high" {
  for_each = toset(var.ecs_service_names)

  alarm_name          = "${var.name_prefix}-ecs-${each.value}-cpu-high"
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 90
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = each.value
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}

# --- Kafka (MSA): 브로커 호스트의 kafka-metrics.sh가 1분마다 올리는 지표 ---

# 소비가 멈추거나 따라가지 못하면 lag가 쌓인다. 워커는 긴 생성 중에 파티션을 pause하므로 몇 건의 lag는 정상이다.
resource "aws_cloudwatch_metric_alarm" "kafka_consumer_lag" {
  for_each = var.kafka_lag_thresholds

  alarm_name          = "${var.name_prefix}-kafka-lag-${each.key}"
  alarm_description   = "Consumer group ${each.key} is falling behind"
  namespace           = var.kafka_metrics_namespace
  metric_name         = "ConsumerLag"
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 10
  threshold           = each.value
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    Group = each.key
  }
  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}

# DLT의 끝 offset은 누적값이다. 1분 사이에 늘었으면(재시도를 다 쓰고 버려진 메시지가 생겼으면) 알린다.
resource "aws_cloudwatch_metric_alarm" "kafka_dead_letters" {
  for_each = toset(var.kafka_dlt_topics)

  alarm_name          = "${var.name_prefix}-kafka-dlt-${replace(each.value, ".", "-")}"
  alarm_description   = "New messages in ${each.value}"
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "increase"
    expression  = "DIFF(dlt)"
    label       = "new dead letters"
    return_data = true
  }

  metric_query {
    id = "dlt"
    metric {
      namespace   = var.kafka_metrics_namespace
      metric_name = "DeadLetterMessages"
      period      = 60
      stat        = "Maximum"
      dimensions = {
        Topic = each.value
      }
    }
  }

  alarm_actions = local.alarm_actions
  tags          = var.tags
}

# EC2로 띄운 상태 저장 계층(Kafka, Milvus/OpenSearch). 인스턴스가 죽으면 지표 자체가 끊기므로 상태 검사로 따로 본다.
resource "aws_cloudwatch_metric_alarm" "ec2_status" {
  for_each = var.ec2_instance_ids

  alarm_name          = "${var.name_prefix}-ec2-${each.key}-status-check"
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "breaching"
  dimensions = {
    InstanceId = each.value
  }
  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}
