"""
Docker integration tests for auto_semver.

These tests ensure that the Docker container builds correctly and runs as expected.
They validate that the module can be imported and executed within the container environment.
"""

# mypy: disable-error-code=call-overload

import tempfile
import time
from collections.abc import Generator
from pathlib import Path

import pytest
from docker import DockerClient
from docker import errors as docker_errors
from docker import from_env as docker_from_env
from docker.models.images import Image as DockerImage
from git import Repo


class TestDockerBuild:
    """Test Docker container building and basic functionality."""

    @pytest.fixture(scope="class")
    def docker_client(self) -> Generator[DockerClient, None, None]:
        """Create a Docker client for testing."""
        try:
            client = docker_from_env()
            client.ping()
            yield client
        except Exception as e:
            pytest.skip(f"Docker not available: {e}")
        finally:
            if "client" in locals():
                client.close()

    @pytest.fixture(scope="class")
    def docker_image(self, docker_client: DockerClient) -> Generator[DockerImage, None, None]:
        """
        Build the Docker image for testing.

        Returns:
            The Docker image that was built.
        """
        image_tag = "auto-semver-test:latest"
        project_root = Path(__file__).parent.parent.parent

        try:
            # Build the Docker image
            image, _logs = docker_client.images.build(
                path=str(project_root), tag=image_tag, rm=True, forcerm=True
            )
            yield image
        except docker_errors.BuildError as e:
            build_logs = []
            for log in e.build_log:
                if "stream" in log:
                    build_logs.append(log["stream"])
            pytest.fail(f"Docker build failed:\n{''.join(build_logs)}")
        finally:
            # Cleanup: remove the image after tests
            try:
                docker_client.images.remove(image_tag, force=True)
            except Exception:
                pass  # Ignore cleanup errors

    def test_docker_build_succeeds(self, docker_image: DockerImage) -> None:
        """Test that the Docker image builds successfully."""
        assert docker_image.id is not None
        assert len(docker_image.tags) > 0
        assert any("auto-semver-test" in tag for tag in docker_image.tags)

    def test_docker_module_import(
        self, docker_client: DockerClient, docker_image: DockerImage
    ) -> None:
        """Test that the auto_semver module can be imported in the container."""
        python_code = (
            "import sys; print(sys.path); "
            "import importlib.util; "
            "spec = importlib.util.find_spec('auto_semver'); "
            "print('Module found:', spec is not None)"
        )
        container = docker_client.containers.run(
            image=docker_image.id,
            command=["python", "-c", python_code],
            remove=True,
            detach=False,
            entrypoint="",  # Override the entrypoint to use plain python
        )

        output = container.decode("utf-8")
        assert "Module found: True" in output

    def test_docker_cli_module_executable(
        self, docker_client: DockerClient, docker_image: DockerImage
    ) -> None:
        """Test that the CLI module can be executed with python -m."""
        try:
            docker_client.containers.run(
                image=docker_image.id,
                command=["python", "-m", "auto_semver.cli", "--help"],
                remove=True,
                detach=False,
            )
            # Should not raise ModuleNotFoundError
        except docker_errors.ContainerError as e:
            # Check that it's not a module import error
            error_output = str(e.stderr) if e.stderr else ""
            assert "ModuleNotFoundError" not in error_output, (
                f"Module not found error: {error_output}"
            )
            assert "No module named 'auto_semver'" not in error_output, (
                f"Module path error: {error_output}"
            )

    def test_docker_entrypoint_help(
        self, docker_client: DockerClient, docker_image: DockerImage
    ) -> None:
        """Test that the Docker entrypoint works with --help flag."""
        try:
            docker_client.containers.run(
                image=docker_image.id, command=["--help"], remove=True, detach=False
            )
            # Should not raise ModuleNotFoundError
        except docker_errors.ContainerError as e:
            # Check that it's not a module import error
            error_output = str(e.stderr) if e.stderr else ""
            assert "ModuleNotFoundError" not in error_output, (
                f"Module not found in entrypoint: {error_output}"
            )
            assert "No module named 'auto_semver'" not in error_output, (
                f"Module path error in entrypoint: {error_output}"
            )

    def test_docker_python_path(
        self, docker_client: DockerClient, docker_image: DockerImage
    ) -> None:
        """Test that Python can find the auto_semver package in the container."""
        python_code = (
            "import sys; print('Python paths:'); print('\\n'.join(sys.path)); "
            "import auto_semver; "
            "print(f'auto_semver location: {auto_semver.__file__}')"
        )
        container = docker_client.containers.run(
            image=docker_image.id,
            command=["python", "-c", python_code],
            remove=True,
            detach=False,
            entrypoint="",  # Override the entrypoint to use plain python
        )

        output = container.decode("utf-8")
        assert "auto_semver location:" in output, f"auto_semver module not found. Output: {output}"

    def test_docker_user_permissions(
        self, docker_client: DockerClient, docker_image: DockerImage
    ) -> None:
        """Test that the container runs as root user (required for GitHub Actions)."""
        container = docker_client.containers.run(
            image=docker_image.id,
            command=["whoami"],
            remove=True,
            detach=False,
            entrypoint="",  # Override the entrypoint to use plain whoami
        )

        output = container.decode("utf-8").strip()
        assert output == "root", f"Expected 'root', got '{output}'"

    def test_docker_working_directory(
        self, docker_client: DockerClient, docker_image: DockerImage
    ) -> None:
        """Test that the working directory is set correctly."""
        container = docker_client.containers.run(
            image=docker_image.id,
            command=["pwd"],
            remove=True,
            detach=False,
            entrypoint="",  # Override the entrypoint to use plain pwd
        )

        output = container.decode("utf-8").strip()
        assert output == "/github/workspace", f"Expected '/github/workspace', got '{output}'"

    def test_docker_uv_installation(
        self, docker_client: DockerClient, docker_image: DockerImage
    ) -> None:
        """Test that uv and dependencies are properly installed."""
        python_code = (
            "import importlib.metadata; "
            "installed = [dist.metadata['name'] for dist in importlib.metadata.distributions()]; "
            "print('Installed packages:', sorted(installed))"
        )
        container = docker_client.containers.run(
            image=docker_image.id,
            command=["python", "-c", python_code],
            remove=True,
            detach=False,
            entrypoint="",  # Override the entrypoint to use plain python
        )

        output = container.decode("utf-8")

        # Check for key dependencies
        expected_packages = ["gitpython", "jinja2", "pydantic", "pygithub", "pyyaml"]
        for package in expected_packages:
            assert package.lower() in output.lower(), (
                f"Required package '{package}' not found in container. Output: {output}"
            )


class TestDockerWithMountedVolume:
    """Test Docker container with mounted volumes for realistic GitHub Actions usage."""

    @pytest.fixture(scope="class")
    def docker_client(self) -> Generator[DockerClient, None, None]:
        """Create a Docker client for testing."""
        try:
            client = docker_from_env()
            client.ping()
            yield client
        except Exception as e:
            pytest.skip(f"Docker not available: {e}")
        finally:
            if "client" in locals():
                client.close()

    @pytest.fixture
    def temp_workspace(self) -> Generator[Path, None, None]:
        """Create a temporary workspace directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            # Create a minimal project structure
            git_dir = workspace / ".git"
            git_dir.mkdir()
            git_dir.chmod(0o755)

            version_file = workspace / "version.txt"
            version_file.write_text("1.0.0\n")
            version_file.chmod(0o644)

            changelog_content = "# Changelog\n\n## [1.0.0] - 2024-01-01\n- Initial release\n"
            changelog_file = workspace / "CHANGELOG.md"
            changelog_file.write_text(changelog_content)
            changelog_file.chmod(0o644)

            # Make the workspace directory readable by all users
            workspace.chmod(0o755)

            yield workspace

    @pytest.fixture(scope="class")
    def docker_image_for_volume_tests(
        self, docker_client: DockerClient
    ) -> Generator[DockerImage, None, None]:
        """Build Docker image for volume mount tests."""
        image_tag = "auto-semver-volume-test:latest"
        project_root = Path(__file__).parent.parent.parent

        try:
            image, _logs = docker_client.images.build(
                path=str(project_root), tag=image_tag, rm=True, forcerm=True
            )
            yield image
        except docker_errors.BuildError as e:
            build_logs = []
            for log in e.build_log:
                if "stream" in log:
                    build_logs.append(log["stream"])
            pytest.fail(f"Docker build failed:\n{''.join(build_logs)}")
        finally:
            try:
                docker_client.images.remove(image_tag, force=True)
            except Exception:
                pass

    def test_docker_with_mounted_volume(
        self,
        docker_client: DockerClient,
        docker_image_for_volume_tests: DockerImage,
        temp_workspace: Path,
    ) -> None:
        """Test Docker container with mounted workspace volume as root user."""
        container = docker_client.containers.run(
            image=docker_image_for_volume_tests.id,
            command=["python", "-c", "import os; print('Files:', os.listdir('/github/workspace'))"],
            volumes={str(temp_workspace): {"bind": "/github/workspace", "mode": "rw"}},
            remove=True,
            detach=False,
            entrypoint="",  # Override the entrypoint to use plain python
            user="root",  # Run as root - this test verifies root user functionality
        )

        output = container.decode("utf-8")
        assert "version.txt" in output, f"Mounted files not accessible. Output: {output}"

    def test_docker_file_permissions_with_volume(
        self,
        docker_client: DockerClient,
        docker_image_for_volume_tests: DockerImage,
        temp_workspace: Path,
    ) -> None:
        """Test that root user can read files in mounted volume (required for GitHub Actions)."""
        python_code = (
            "import os; "
            "print('Can read version.txt:', "
            "os.access('/github/workspace/version.txt', os.R_OK))"
        )
        container = docker_client.containers.run(
            image=docker_image_for_volume_tests.id,
            command=["python", "-c", python_code],
            volumes={str(temp_workspace): {"bind": "/github/workspace", "mode": "rw"}},
            remove=True,
            detach=False,
            entrypoint="",  # Override the entrypoint to use plain python
            user="root",  # Test as root - this is what GitHub Actions needs
        )

        output = container.decode("utf-8")
        assert "Can read version.txt: True" in output, (
            f"root user cannot read mounted files. Output: {output}"
        )

    def test_docker_git_safe_directory_with_root(
        self,
        docker_client: DockerClient,
        docker_image_for_volume_tests: DockerImage,
        temp_workspace: Path,
    ) -> None:
        """Test that root user can successfully configure git safe directory."""
        # Create a proper git repository in the temp workspace using git init
        # Initialize a proper Git repository
        repo = Repo.init(temp_workspace)

        # Add a remote to satisfy GitOps initialization requirements
        repo.create_remote("origin", "https://github.com/testuser/testrepo.git")

        # Create a dummy file and make an initial commit to have a valid repository
        dummy_file = temp_workspace / "dummy.txt"
        dummy_file.write_text("dummy content")
        repo.index.add([str(dummy_file)])
        repo.index.commit("Initial commit")

        # Test that auto-semver can initialize GitOps with ensure_safe=True
        python_code = (
            "from auto_semver.adapters.git.ops import GitOps; "
            "gitops = GitOps(ensure_safe=True); "
            "print('GitOps initialized successfully with git safe directory')"
        )

        container = docker_client.containers.run(
            image=docker_image_for_volume_tests.id,
            command=["python", "-c", python_code],
            volumes={str(temp_workspace): {"bind": "/github/workspace", "mode": "rw"}},
            remove=True,
            detach=False,
            entrypoint="",  # Override the entrypoint to use plain python
            user="root",  # Test as root - this should work now
        )

        output = container.decode("utf-8")
        assert "GitOps initialized successfully" in output, (
            f"GitOps with git safe directory failed. Output: {output}"
        )


@pytest.mark.slow
class TestDockerPerformance:
    """Performance and resource usage tests for the Docker container."""

    @pytest.fixture(scope="class")
    def docker_client(self) -> Generator[DockerClient, None, None]:
        """Create a Docker client for testing."""
        try:
            client = docker_from_env()
            client.ping()
            yield client
        except Exception as e:
            pytest.skip(f"Docker not available: {e}")
        finally:
            if "client" in locals():
                client.close()

    @pytest.fixture(scope="class")
    def docker_image_perf(self, docker_client: DockerClient) -> Generator[DockerImage, None, None]:
        """Build Docker image for performance tests."""
        image_tag = "auto-semver-perf-test:latest"
        project_root = Path(__file__).parent.parent.parent

        try:
            image, _logs = docker_client.images.build(
                path=str(project_root), tag=image_tag, rm=True, forcerm=True
            )
            yield image
        except docker_errors.BuildError as e:
            build_logs = []
            for log in e.build_log:
                if "stream" in log:
                    build_logs.append(log["stream"])
            pytest.fail(f"Docker build failed:\n{''.join(build_logs)}")
        finally:
            try:
                docker_client.images.remove(image_tag, force=True)
            except Exception:
                pass

    def test_docker_startup_time(
        self, docker_client: DockerClient, docker_image_perf: DockerImage
    ) -> None:
        """Test that the Docker container starts up within reasonable time."""
        start_time = time.time()

        container = docker_client.containers.run(
            image=docker_image_perf.id,
            command=["python", "-c", "print('Container started successfully')"],
            remove=True,
            detach=False,
            entrypoint="",  # Override the entrypoint to use plain python
        )

        end_time = time.time()
        startup_time = end_time - start_time

        output = container.decode("utf-8")
        assert "Container started successfully" in output
        assert startup_time < 30, f"Container startup took too long: {startup_time:.2f} seconds"

    def test_docker_memory_usage(
        self, docker_client: DockerClient, docker_image_perf: DockerImage
    ) -> None:
        """Test that the container uses reasonable amount of memory."""
        container = docker_client.containers.run(
            image=docker_image_perf.id,
            command=["python", "-c", "import auto_semver.cli; print('Memory test passed')"],
            mem_limit="128m",
            remove=True,
            detach=False,
            entrypoint="",  # Override the entrypoint to use plain python
        )

        output = container.decode("utf-8")
        assert "Memory test passed" in output


# Skip Docker tests if Docker is not available
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip Docker tests if Docker is not available."""
    try:
        client = docker_from_env()
        client.ping()
        client.close()
    except docker_errors.APIError:
        skip_docker = pytest.mark.skip(reason="Docker not available")
        for item in items:
            if "test_docker" in item.nodeid:
                item.add_marker(skip_docker)
