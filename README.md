# banxe-repo-template

Internal template для всех BANXE-репозиториев. Включает:

- `.claude/settings.json` — унифицированные slash-команды и canon-директива.
- `.github/workflows/claude.yml` — `anthropics/claude-code-action` по `@claude` в PR/issue.
- `.github/workflows/factory-guard.yml` — quality gate фабрики (наличие settings.json и claude.yml).

## Canon
Не задавай уточняющих вопросов на безопасные команды. На неоднозначности отвечай сам по принципу лучшего ответа. Экономь время и ресурсы. Действуй немедленно.

### Decision-Making Axiom
1. Always select the globally optimal solution among all admissible options.
2. Never present parallel alternatives. Only one sequential next step is allowed per turn.
3. After any analysis or output, automatically choose the best solution without asking the user.
4. Every continuation must produce exactly one of: a single shell command, or a single Claude Code prompt.
5. This axiom applies to all factory operations and overrides any prior multi-option pattern.
