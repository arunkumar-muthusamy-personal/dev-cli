"""AWS CLI execution manager.

Detects the user's intent, classifies the command risk, asks for confirmation
at the right level, executes via the shell runner, and caches results.
"""
from __future__ import annotations

import re

from rich.console import Console
from rich.prompt import Confirm, Prompt

from dev_cli.aws_cli.cache import CommandCache
from dev_cli.aws_cli.command_classifier import CommandRisk, classify
from dev_cli.aws_cli.profile_detector import get_active_profile, get_available_profiles
from dev_cli.shell.runner import CommandResult, ShellRunner

# ---------------------------------------------------------------------------
# Intent detection: map natural-language phrases to AWS CLI commands
# ---------------------------------------------------------------------------

_INTENT_MAP: list[tuple[re.Pattern, str]] = [
    # CloudWatch Logs
    (re.compile(r"(show|tail|view|check|get|read).{0,30}(log|logs)", re.I),
     "logs tail {log_group} --since 1h"),
    (re.compile(r"log group", re.I),
     "logs describe-log-groups"),
    # Lambda
    (re.compile(r"lambda.{0,20}(config|env|environment|variable)", re.I),
     "lambda get-function-configuration --function-name {function_name}"),
    (re.compile(r"lambda.{0,20}(list|all)|(list|show).{0,20}lambda", re.I),
     "lambda list-functions"),
    (re.compile(r"invoke.{0,20}lambda|lambda.{0,20}invoke", re.I),
     "lambda invoke --function-name {function_name} --payload '{}' /dev/null"),
    # IAM
    (re.compile(r"(my |current )?(permission|policy|role|iam)", re.I),
     "iam get-user"),
    (re.compile(r"list.{0,15}(role|roles)", re.I),
     "iam list-roles"),
    # S3
    (re.compile(r"(list|show).{0,15}bucket", re.I),
     "s3 ls"),
    (re.compile(r"s3.{0,15}(content|file|object)", re.I),
     "s3 ls s3://{bucket_name}"),
    # EC2
    (re.compile(r"(list|show|describe).{0,15}(instance|ec2)", re.I),
     "ec2 describe-instances"),
    (re.compile(r"security.{0,10}group", re.I),
     "ec2 describe-security-groups"),
    # RDS
    (re.compile(r"(list|show|describe).{0,15}(rds|database|db instance)", re.I),
     "rds describe-db-instances"),
    # DynamoDB
    (re.compile(r"(list|show).{0,15}(dynamo|table)", re.I),
     "dynamodb list-tables"),
    # ECS
    (re.compile(r"(list|show).{0,15}(ecs|cluster|service|task)", re.I),
     "ecs list-clusters"),
    # CloudFormation
    (re.compile(r"(list|show|describe).{0,15}stack", re.I),
     "cloudformation list-stacks"),
    # General
    (re.compile(r"(aws.{0,10}(region|account|caller|identity)|who am i.{0,20}aws)", re.I),
     "sts get-caller-identity"),
]


def detect_aws_intent(message: str) -> str | None:
    """Return a suggested AWS CLI sub-command if the message seems AWS-related."""
    for pattern, template in _INTENT_MAP:
        if pattern.search(message):
            return template
    return None


def is_aws_related(message: str) -> bool:
    """Quick check: does the message seem to be asking about AWS resources?"""
    keywords = re.compile(
        r"\b(aws|lambda|s3|ec2|rds|iam|cloudwatch|cloudformation|"
        r"dynamodb|dynamo|ecs|fargate|bucket|stack|permission|role|policy|"
        r"log\s+group|security\s+group)\b",
        re.I,
    )
    return bool(keywords.search(message))


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class AWSCLIManager:
    """Orchestrate AWS CLI command detection, confirmation, and execution."""

    def __init__(
        self,
        console: Console | None = None,
        aws_profile: str | None = None,
    ) -> None:
        self._console = console or Console()
        self._profile = aws_profile
        self._cache = CommandCache(ttl=30)
        self._shell = ShellRunner(console=self._console)

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def select_profile(self, explicit: str | None = None) -> str | None:
        """Resolve or interactively select the AWS profile."""
        profile = get_active_profile(explicit or self._profile)
        if profile:
            self._profile = profile
            return profile

        profiles = get_available_profiles()
        if not profiles:
            self._console.print("[yellow]No AWS profiles found in ~/.aws/[/yellow]")
            return None

        self._console.print("\n[bold]Available AWS profiles:[/bold]")
        for i, p in enumerate(profiles, 1):
            self._console.print(f"  {i}. {p}")

        choice = Prompt.ask(
            "Select profile",
            choices=[str(i) for i in range(1, len(profiles) + 1)] + profiles,
            default=profiles[0],
            console=self._console,
        )
        # Accept either index or name
        if choice.isdigit():
            profile = profiles[int(choice) - 1]
        else:
            profile = choice

        self._profile = profile
        return profile

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run(
        self,
        command: str,
        auto_confirm: bool = False,
    ) -> CommandResult | None:
        """Classify, confirm, execute an AWS CLI command. Returns None if cancelled."""
        # Normalise: ensure command starts with 'aws'
        cmd = command.strip()
        if not cmd.lower().startswith("aws "):
            cmd = f"aws {cmd}"

        # Append profile flag if we have one and it's not already there
        if self._profile and "--profile" not in cmd:
            cmd = f"{cmd} --profile {self._profile}"

        # Check cache first
        cached = self._cache.get(cmd, self._profile)
        if cached is not None:
            self._console.print("[dim](using cached result)[/dim]")
            return CommandResult(
                command=cmd, stdout=cached, stderr="", returncode=0
            )

        # Classify risk
        risk = classify(cmd)

        if risk == CommandRisk.READ:
            confirmed = auto_confirm or self._confirm_read(cmd)
        elif risk == CommandRisk.MODIFY:
            confirmed = self._confirm_modify(cmd)
        else:  # DELETE
            confirmed = self._confirm_delete(cmd)

        if not confirmed:
            self._console.print("[dim]Cancelled.[/dim]")
            return None

        # Execute
        self._console.print("[dim]Running AWS CLI...[/dim]")
        result = await self._shell.run_silent(cmd)

        # Cache read-only results
        if risk == CommandRisk.READ and result.success:
            self._cache.set(cmd, result.output, self._profile)

        if not result.success:
            self._console.print(
                f"[yellow]AWS CLI returned exit code {result.returncode}[/yellow]"
            )

        return result

    # ------------------------------------------------------------------
    # Confirmation helpers
    # ------------------------------------------------------------------

    def _confirm_read(self, cmd: str) -> bool:
        self._console.print(f"\n[bold cyan]AWS command:[/bold cyan]")
        self._console.print(f"  [cyan]$ {cmd}[/cyan]")
        return Confirm.ask("Run?", console=self._console, default=True)

    def _confirm_modify(self, cmd: str) -> bool:
        self._console.print(f"\n[bold yellow]⚠ This will MODIFY AWS resources:[/bold yellow]")
        self._console.print(f"  [yellow]$ {cmd}[/yellow]")
        return Confirm.ask("Confirm?", console=self._console, default=False)

    def _confirm_delete(self, cmd: str) -> bool:
        self._console.print(f"\n[bold red]⛔ DESTRUCTIVE — this will DELETE AWS resources:[/bold red]")
        self._console.print(f"  [red]$ {cmd}[/red]")
        first = Confirm.ask("Are you sure?", console=self._console, default=False)
        if not first:
            return False
        typed = Prompt.ask(
            "Type [bold]DELETE[/bold] to confirm permanent deletion",
            console=self._console,
        )
        return typed.strip() == "DELETE"
