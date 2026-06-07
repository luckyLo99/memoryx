# Contributing to MemoryX

We welcome all forms of contribution — code, documentation, issues, and feedback.

## Development Principles

This project follows the **Karpathy Engineering Guidelines**:

1. **Think Before Coding** — Expose assumptions before writing code
2. **Simplicity First** — Solve only the current problem, no speculative generality
3. **Surgical Changes** — Change only what must be changed
4. **Goal-Driven** — Define verifiable goals, test before implementation

## Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Write tests first (red-green cycle)
4. Implement minimal code to make tests pass
5. Run full regression: `pytest -q`
6. Submit a pull request

### Testing

```bash
# Run all tests
pytest -q

# Run specific test file
pytest tests/unit/cognitive/test_ebbinghaus.py -v

# Run benchmark tests
pytest tests/benchmarks/ -v

# Run architecture contract tests
pytest tests/unit/architecture/ -v

# Run with coverage
pytest --cov=memoryx
```

### Code Style

- Format with [Black](https://github.com/psf/black): `black memoryx/ tests/`
- Lint with [Ruff](https://github.com/astral-sh/ruff): `ruff check memoryx/ tests/`
- All Python files must be UTF-8 encoded
- Follow existing naming conventions in the codebase

## Adding Cognitive Models

When implementing a new cognitive model:

1. Add the model module under `memoryx/cognitive/` or appropriate directory
2. Write comprehensive unit tests in `tests/unit/cognitive/`
3. Add integration tests if the model affects retrieval or storage paths
4. Update `docs/cognitive/` with bilingual (Chinese/English) documentation
5. Register new test markers in `pyproject.toml` if needed

## Pull Request Guidelines

- Keep PRs focused on a single concern
- Include test evidence in the PR description
- Ensure all CI checks pass
- Update relevant documentation
- Add CHANGELOG entry for user-visible changes

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Questions?

Open a [GitHub Issue](https://github.com/luckyl214/memoryx/issues) or start a discussion.

---

## 贡献指南

我们欢迎任何形式的贡献 — 代码、文档、Issue 和反馈。

### 开发原则

1. **先思考后编码** — 暴露假设再写代码
2. **简洁至上** — 只解决当前问题
3. **手术式修改** — 只改必须改的
4. **目标驱动** — 先测试后实现

### 开发流程

1. Fork 本仓库
2. 创建特性分支: `git checkout -b feature/your-feature`
3. 先写测试（红绿循环）
4. 实现最小代码使测试通过
5. 运行全量回归: `pytest -q`
6. 提交 PR