from memoryx.release import ReleaseChecker

def test_release_checker_basic():
    result = ReleaseChecker(".").run()
    assert result.checks["version_file"]
    assert result.checks["pyproject_exists"]
    assert result.checks["readme_exists"]
    assert result.checks["changelog_exists"]
    assert result.checks["build_system_declared"]
    assert result.checks["project_metadata_declared"]
