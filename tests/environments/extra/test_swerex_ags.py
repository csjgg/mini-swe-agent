"""Tests for Tencent AGS SWE sandbox environment in mini-swe-agent.

Unit tests cover configuration and initialization logic.
Integration tests that require real AGS credentials are marked with @pytest.mark.slow.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from minisweagent.environments.extra.swerex_ags import (
    SwerexAgsEnvironment,
    SwerexAgsEnvironmentConfig,
)
from minisweagent.exceptions import Submitted
from swerex.exceptions import CommandTimeoutError, EnvironmentExpiredError


# =====================================================================
# SwerexAgsEnvironmentConfig tests
# =====================================================================


class TestSwerexAgsEnvironmentConfig:
    """Tests for SwerexAgsEnvironmentConfig."""

    def test_required_tool_id(self):
        """tool_id is required."""
        with pytest.raises(Exception):
            SwerexAgsEnvironmentConfig()

    def test_default_values(self):
        config = SwerexAgsEnvironmentConfig(tool_id="sdt-test")
        assert config.tool_id == "sdt-test"
        assert config.image == ""
        assert config.cwd == "/"
        assert config.timeout == 600
        assert config.startup_timeout == 300.0
        assert config.runtime_timeout == 60.0
        assert config.region == "ap-chongqing"
        assert config.domain == "ap-chongqing.tencentags.com"
        assert config.http_endpoint == "ags.tencentcloudapi.com"
        assert config.skip_ssl_verify is False
        assert config.timeout_duration == "1h"

    def test_custom_values(self):
        config = SwerexAgsEnvironmentConfig(
            tool_id="sdt-custom",
            image="swebench/sweb.eval.x86_64.django__django-16379:latest",
            cwd="/testbed",
            timeout=120,
            region="ap-guangzhou",
        )
        assert config.tool_id == "sdt-custom"
        assert config.image == "swebench/sweb.eval.x86_64.django__django-16379:latest"
        assert config.cwd == "/testbed"
        assert config.timeout == 120
        assert config.region == "ap-guangzhou"

    def test_env_var_credential_fallback(self):
        """Credentials should be read from environment variables if not provided."""
        with patch.dict(os.environ, {
            "TENCENTCLOUD_SECRET_ID": "env-id",
            "TENCENTCLOUD_SECRET_KEY": "env-key",
        }):
            config = SwerexAgsEnvironmentConfig(tool_id="sdt-test")
            assert config.secret_id == "env-id"
            assert config.secret_key == "env-key"

    def test_explicit_creds_override_env(self):
        """Explicit credentials should take precedence over env vars."""
        with patch.dict(os.environ, {
            "TENCENTCLOUD_SECRET_ID": "env-id",
            "TENCENTCLOUD_SECRET_KEY": "env-key",
        }):
            config = SwerexAgsEnvironmentConfig(
                tool_id="sdt-test",
                secret_id="explicit-id",
                secret_key="explicit-key",
            )
            assert config.secret_id == "explicit-id"
            assert config.secret_key == "explicit-key"


# =====================================================================
# SwerexAgsEnvironment tests (mocked deployment)
# =====================================================================


class TestSwerexAgsEnvironment:
    """Tests for SwerexAgsEnvironment with mocked AGS deployment."""

    def _make_mock_deployment(self):
        """Create a mock TencentAGSDeployment."""
        mock_deployment = MagicMock()
        mock_runtime = MagicMock()

        # Mock execute to return a CommandResponse-like object
        mock_result = MagicMock()
        mock_result.stdout = "hello world\n"
        mock_result.exit_code = 0

        async def mock_execute(cmd):
            return mock_result

        mock_runtime.execute = mock_execute

        async def mock_start():
            pass

        async def mock_stop():
            pass

        mock_deployment.start = mock_start
        mock_deployment.stop = mock_stop
        mock_deployment.runtime = mock_runtime

        return mock_deployment

    @patch("minisweagent.environments.extra.swerex_ags.SwerexAgsEnvironment._start_deployment")
    def test_init_calls_start_deployment(self, mock_start):
        """Init should call _start_deployment."""
        env = SwerexAgsEnvironment(tool_id="sdt-test")
        mock_start.assert_called_once()

    @patch("minisweagent.environments.extra.swerex_ags.SwerexAgsEnvironment._start_deployment")
    def test_config_is_set(self, mock_start):
        """Config should be properly initialized."""
        env = SwerexAgsEnvironment(
            tool_id="sdt-test",
            image="test-image:latest",
            cwd="/testbed",
        )
        assert env.config.tool_id == "sdt-test"
        assert env.config.image == "test-image:latest"
        assert env.config.cwd == "/testbed"

    @patch("minisweagent.environments.extra.swerex_ags.SwerexAgsEnvironment._start_deployment")
    def test_execute_when_not_started(self, mock_start):
        """Execute should return error when not started."""
        env = SwerexAgsEnvironment(tool_id="sdt-test")
        env._started = False
        env.deployment = None

        result = env.execute({"command": "echo hello"})
        assert result["returncode"] == -1
        assert "not started" in result["exception_info"].lower()

    @patch("minisweagent.environments.extra.swerex_ags.SwerexAgsEnvironment._start_deployment")
    def test_serialize(self, mock_start):
        """Serialize should return proper structure."""
        env = SwerexAgsEnvironment(tool_id="sdt-test", image="test:latest")
        data = env.serialize()
        assert "info" in data
        assert "config" in data["info"]
        assert "environment" in data["info"]["config"]
        assert data["info"]["config"]["environment"]["tool_id"] == "sdt-test"

    @patch("minisweagent.environments.extra.swerex_ags.SwerexAgsEnvironment._start_deployment")
    def test_get_template_vars(self, mock_start):
        """get_template_vars should return config values merged with kwargs."""
        env = SwerexAgsEnvironment(tool_id="sdt-test", cwd="/testbed")
        vars = env.get_template_vars(extra_key="extra_value")
        assert vars["tool_id"] == "sdt-test"
        assert vars["cwd"] == "/testbed"
        assert vars["extra_key"] == "extra_value"

    @patch("minisweagent.environments.extra.swerex_ags.SwerexAgsEnvironment._start_deployment")
    def test_execute_returns_observation_for_command_timeout(self, mock_start):
        """Command timeouts should stay as recoverable observations."""
        env = SwerexAgsEnvironment(tool_id="sdt-test")
        env._started = True
        env.deployment = self._make_mock_deployment()

        async def mock_execute(cmd):
            raise CommandTimeoutError("Timeout (600s) exceeded while running command")

        env.deployment.runtime.execute = mock_execute

        result = env.execute({"command": "sleep 999"})
        assert result["returncode"] == -1
        assert "Command timed out" in result["exception_info"]
        assert result["extra"]["exception_type"] == "CommandTimeoutError"

    @patch("minisweagent.environments.extra.swerex_ags.SwerexAgsEnvironment._start_deployment")
    def test_execute_raises_for_expired_environment(self, mock_start):
        """Expired environments should abort the task immediately."""
        env = SwerexAgsEnvironment(tool_id="sdt-test")
        env._started = True
        env.deployment = self._make_mock_deployment()

        async def mock_execute(cmd):
            raise EnvironmentExpiredError("sandbox expired")

        env.deployment.runtime.execute = mock_execute

        with pytest.raises(EnvironmentExpiredError):
            env.execute({"command": "echo hello"})


# =====================================================================
# _check_finished tests
# =====================================================================


class TestCheckFinished:
    """Tests for submission detection in _check_finished."""

    @patch("minisweagent.environments.extra.swerex_ags.SwerexAgsEnvironment._start_deployment")
    def test_normal_output_no_submit(self, mock_start):
        """Normal output should not trigger submission."""
        env = SwerexAgsEnvironment(tool_id="sdt-test")
        output = {"output": "hello world", "returncode": 0}
        # Should not raise
        env._check_finished(output)

    @patch("minisweagent.environments.extra.swerex_ags.SwerexAgsEnvironment._start_deployment")
    def test_submit_trigger(self, mock_start):
        """COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT should trigger Submitted."""
        env = SwerexAgsEnvironment(tool_id="sdt-test")
        output = {
            "output": "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\nmy patch content",
            "returncode": 0,
        }
        with pytest.raises(Submitted):
            env._check_finished(output)

    @patch("minisweagent.environments.extra.swerex_ags.SwerexAgsEnvironment._start_deployment")
    def test_submit_not_triggered_on_error(self, mock_start):
        """Submission should not trigger when returncode is non-zero."""
        env = SwerexAgsEnvironment(tool_id="sdt-test")
        output = {
            "output": "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\nmy patch content",
            "returncode": 1,
        }
        # Should not raise
        env._check_finished(output)

    @patch("minisweagent.environments.extra.swerex_ags.SwerexAgsEnvironment._start_deployment")
    def test_stop_when_not_started(self, mock_start):
        """Stop should be safe to call even if not started."""
        env = SwerexAgsEnvironment(tool_id="sdt-test")
        env.deployment = None
        env._started = False
        # Should not raise
        env.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
