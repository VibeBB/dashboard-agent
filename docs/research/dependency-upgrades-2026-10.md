# Dependency upgrade review — October 2026

Reviewed the complete upstream release notes between the previous lock and the
`uv lock --upgrade` result. The five transitive upgrades are used by the
development/plugin-check dependency graph; dashboard runtime code does not
call their service APIs or send analytics.

| Component | Previous → new | Release notes reviewed | Evaluation |
| --- | --- | --- | --- |
| boto3 | 1.43.105 → 1.43.106 | [1.43.106 changelog](https://github.com/boto/boto3/blob/1.43.106/CHANGELOG.rst) | This release adds AWS service model operations and fields. The repository does not use boto3 or AWS services, so no application feature applies. |
| botocore | 1.43.105 → 1.43.106 | [1.43.106 changelog](https://github.com/boto/botocore/blob/1.43.106/CHANGELOG.rst) | The release adds service API model support and documentation. No corresponding AWS integration exists in the repository. |
| google-api-python-client | 2.200.0 → 2.201.0 | [2.201.0 changelog](https://github.com/googleapis/google-api-python-client/blob/v2.201.0/CHANGELOG.md) | The release refreshes generated discovery clients across Google APIs. The repository does not build or call these clients, so no generated API is relevant to adopt. |
| google-auth | 2.59.0 → 2.59.1 | [2.59.1 release notes](https://github.com/googleapis/google-cloud-python/releases/tag/google-auth-v2.59.1) | The patch adds mTLS support for `requests.Request` during token refresh and impersonation. No Google authentication or mTLS request path is used here. |
| posthog | 7.61.0 → 7.61.1 | [7.61.1 changelog change](https://github.com/PostHog/posthog-python/commit/bcf9d3426d1c2a6dc1966338e0d5409906387875) | The patch narrows MCP `$mcp_tools_list` event payloads. Dashboard does not instrument or send PostHog events, so no integration change applies. |

`pytest-cov==7.1.0` is a new development dependency. Its full release history
through 7.1.0 was reviewed in the [pytest-cov changelog](https://github.com/pytest-dev/pytest-cov/blob/v7.1.0/CHANGELOG.rst).
The deterministic `--cov-fail-under` total is used for the new 56% coverage
gate. Its improved SQLite `ResourceWarning` filtering needs no repository
configuration. Version 7.0 dropped subprocess coverage, which this project
does not rely on: coverage is limited to `src/dashboard`, while subprocess
hook tests assert their outputs and side effects.
