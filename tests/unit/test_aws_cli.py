from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dev_cli.aws_cli.cache import CommandCache
from dev_cli.aws_cli.command_classifier import CommandRisk, classify
from dev_cli.aws_cli.intent_detector import detect_aws_intent, is_aws_related
from dev_cli.aws_cli.profile_detector import get_active_profile, get_available_profiles


# ---------------------------------------------------------------------------
# command_classifier
# ---------------------------------------------------------------------------

class TestAWSCommandClassifier:
    def test_read_verbs(self):
        assert classify("aws logs tail /aws/lambda/fn") == CommandRisk.READ
        assert classify("aws lambda list-functions") == CommandRisk.READ
        assert classify("aws ec2 describe-instances") == CommandRisk.READ
        assert classify("aws iam get-user") == CommandRisk.READ
        assert classify("aws s3api head-bucket --bucket my-bucket") == CommandRisk.READ

    def test_modify_verbs(self):
        assert classify("aws lambda update-function-configuration --function-name fn") == CommandRisk.MODIFY
        assert classify("aws ec2 create-security-group --group-name sg") == CommandRisk.MODIFY
        assert classify("aws s3api put-object-acl --bucket b --key k") == CommandRisk.MODIFY

    def test_delete_verbs(self):
        assert classify("aws logs delete-log-group --log-group-name /aws/lambda/fn") == CommandRisk.DELETE
        assert classify("aws ec2 terminate-instances --instance-ids i-123") == CommandRisk.DELETE
        assert classify("aws dynamodb delete-item --table-name t") == CommandRisk.DELETE

    def test_strips_aws_prefix(self):
        assert classify("aws ec2 describe-instances") == classify("ec2 describe-instances")

    def test_hyphenated_verbs(self):
        # update-function-configuration → verb="update" → MODIFY
        assert classify("aws lambda update-function-configuration") == CommandRisk.MODIFY
        # delete-log-group → verb="delete" → DELETE
        assert classify("aws logs delete-log-group") == CommandRisk.DELETE

    def test_unknown_verb_defaults_to_modify(self):
        assert classify("aws unknown-service weird-command") == CommandRisk.MODIFY

    def test_empty_command(self):
        assert classify("aws") == CommandRisk.MODIFY


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------

class TestCommandCache:
    def test_miss_on_empty(self):
        cache = CommandCache(ttl=30)
        assert cache.get("aws logs tail fn", "prod") is None

    def test_hit_after_set(self):
        cache = CommandCache(ttl=30)
        cache.set("aws logs tail fn", "log output", "prod")
        assert cache.get("aws logs tail fn", "prod") == "log output"

    def test_miss_after_ttl_expires(self):
        cache = CommandCache(ttl=1)
        cache.set("aws s3 ls", "bucket list", "default")
        time.sleep(1.1)
        assert cache.get("aws s3 ls", "default") is None

    def test_different_profiles_different_keys(self):
        cache = CommandCache(ttl=30)
        cache.set("aws s3 ls", "prod buckets", "prod")
        cache.set("aws s3 ls", "dev buckets", "dev")
        assert cache.get("aws s3 ls", "prod") == "prod buckets"
        assert cache.get("aws s3 ls", "dev") == "dev buckets"

    def test_clear_empties_store(self):
        cache = CommandCache(ttl=30)
        cache.set("aws s3 ls", "output", "prod")
        cache.clear()
        assert cache.get("aws s3 ls", "prod") is None

    def test_none_profile(self):
        cache = CommandCache(ttl=30)
        cache.set("aws s3 ls", "output", None)
        assert cache.get("aws s3 ls", None) == "output"


# ---------------------------------------------------------------------------
# profile_detector
# ---------------------------------------------------------------------------

class TestProfileDetector:
    def test_explicit_profile_takes_priority(self):
        assert get_active_profile(explicit="staging") == "staging"

    def test_aws_profile_env_var(self, monkeypatch):
        monkeypatch.setenv("AWS_PROFILE", "prod")
        monkeypatch.delenv("AWS_DEFAULT_PROFILE", raising=False)
        assert get_active_profile() == "prod"

    def test_aws_default_profile_env_var(self, monkeypatch):
        monkeypatch.delenv("AWS_PROFILE", raising=False)
        monkeypatch.setenv("AWS_DEFAULT_PROFILE", "staging")
        assert get_active_profile() == "staging"

    def test_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("AWS_PROFILE", "prod")
        assert get_active_profile(explicit="dev") == "dev"

    def test_get_available_profiles_missing_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        profiles = get_available_profiles()
        assert profiles == []

    def test_get_available_profiles_from_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        aws_dir = tmp_path / ".aws"
        aws_dir.mkdir()
        (aws_dir / "config").write_text(
            "[default]\nregion=us-east-1\n"
            "[profile prod]\nregion=us-west-2\n"
            "[profile staging]\nregion=eu-west-1\n",
            encoding="utf-8",
        )
        profiles = get_available_profiles()
        assert "default" in profiles
        assert "prod" in profiles
        assert "staging" in profiles

    def test_get_available_profiles_from_credentials(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        aws_dir = tmp_path / ".aws"
        aws_dir.mkdir()
        (aws_dir / "credentials").write_text(
            "[default]\naws_access_key_id=xxx\n"
            "[dev]\naws_access_key_id=yyy\n",
            encoding="utf-8",
        )
        profiles = get_available_profiles()
        assert "default" in profiles
        assert "dev" in profiles

    def test_profiles_sorted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        aws_dir = tmp_path / ".aws"
        aws_dir.mkdir()
        (aws_dir / "credentials").write_text(
            "[zebra]\n[alpha]\n[mango]\n", encoding="utf-8"
        )
        profiles = get_available_profiles()
        assert profiles == sorted(profiles)


# ---------------------------------------------------------------------------
# intent_detector (aws)
# ---------------------------------------------------------------------------

class TestAWSIntentDetector:
    def test_cloudwatch_logs_intent(self):
        result = detect_aws_intent("show me the logs for my lambda")
        assert result is not None
        assert "logs" in result

    def test_lambda_list_intent(self):
        result = detect_aws_intent("list all my lambdas")
        assert result is not None
        assert "lambda" in result

    def test_s3_list_intent(self):
        result = detect_aws_intent("list my S3 buckets")
        assert result is not None
        assert "s3" in result

    def test_iam_intent(self):
        result = detect_aws_intent("what are my IAM permissions")
        assert result is not None
        assert "iam" in result

    def test_ec2_intent(self):
        result = detect_aws_intent("show my EC2 instances")
        assert result is not None
        assert "ec2" in result

    def test_caller_identity_intent(self):
        result = detect_aws_intent("who am i in AWS")
        assert result is not None
        assert "sts" in result

    def test_no_aws_intent(self):
        assert detect_aws_intent("can you help me write a python function") is None
        assert detect_aws_intent("what is the capital of france") is None

    def test_is_aws_related(self):
        assert is_aws_related("check my lambda errors") is True
        assert is_aws_related("list S3 buckets") is True
        assert is_aws_related("show cloudwatch logs") is True
        assert is_aws_related("write a hello world function") is False
        assert is_aws_related("what is the weather today") is False
