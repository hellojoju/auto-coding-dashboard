"""CommandConsumer 测试：轮询 Repository 待处理命令并消费。"""

from pathlib import Path

import pytest

from dashboard.consumer import CommandConsumer
from dashboard.command_processor import CommandProcessor
from dashboard.event_bus import EventBus
from dashboard.state_repository import ProjectStateRepository
from dashboard.models import Command, Event


@pytest.fixture
def repo(tmp_path: Path) -> ProjectStateRepository:
    return ProjectStateRepository(base_dir=tmp_path, project_id="test-project", run_id="test-run")


@pytest.fixture
def processor() -> CommandProcessor:
    return CommandProcessor()


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def consumer(
    repo: ProjectStateRepository,
    processor: CommandProcessor,
    event_bus: EventBus,
) -> CommandConsumer:
    return CommandConsumer(
        repository=repo,
        processor=processor,
        event_bus=event_bus,
    )


class TestCommandConsumer:
    def test_consumer_claims_and_processes_pending_command(
        self, consumer: CommandConsumer, repo: ProjectStateRepository
    ) -> None:
        cmd = repo.save_command(Command(type="approve", target_id="feature-1"))
        assert cmd.status == "pending"

        processed = consumer.process_once()
        assert processed == 1

        saved = repo.get_command(cmd.command_id)
        assert saved is not None
        assert saved.status in ("applied", "accepted")

    def test_consumer_processes_nothing_when_queue_empty(
        self, consumer: CommandConsumer
    ) -> None:
        processed = consumer.process_once()
        assert processed == 0

    def test_consumer_handles_command_error_gracefully(
        self,
        repo: ProjectStateRepository,
        processor: CommandProcessor,
        event_bus: EventBus,
    ) -> None:
        """命令处理抛出异常时，Consumer 不应崩溃，应标记失败并继续。"""

        class BrokenProcessor(CommandProcessor):
            def accept(self, command: Command) -> Command:
                raise RuntimeError("boom")

        consumer = CommandConsumer(
            repository=repo,
            processor=BrokenProcessor(),
            event_bus=event_bus,
        )
        cmd = repo.save_command(Command(type="approve", target_id="feature-1"))

        processed = consumer.process_once()
        assert processed == 1

        saved = repo.get_command(cmd.command_id)
        assert saved is not None
        assert saved.status == "failed"

    def test_consumer_processes_multiple_pending_commands(
        self, consumer: CommandConsumer, repo: ProjectStateRepository
    ) -> None:
        repo.save_command(Command(type="approve", target_id="feature-1"))
        repo.save_command(Command(type="reject", target_id="feature-2"))
        repo.save_command(Command(type="pause", target_id="feature-3"))

        processed = consumer.process_once()
        assert processed == 3

    def test_consumer_skips_non_pending_commands(
        self, consumer: CommandConsumer, repo: ProjectStateRepository, processor: CommandProcessor
    ) -> None:
        """已经 accepted 的命令不应被再次消费。"""
        cmd = repo.save_command(Command(type="approve", target_id="feature-1"))
        processor.accept(cmd)

        processed = consumer.process_once()
        assert processed == 0
