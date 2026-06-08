#!/usr/bin/env python3
"""Validate this plugin repository without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


TODO_MARKER = "[TODO:"
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?"
    r"(?:\+[0-9A-Za-z.-]+)?$"
)
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Agentic Factory plugin.")
    parser.add_argument("plugin_root", nargs="?", default=".")
    args = parser.parse_args()

    plugin_root = Path(args.plugin_root).expanduser().resolve()
    errors = validate(plugin_root)
    if errors:
        print("Plugin validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Plugin validation passed: {plugin_root}")
    return 0


def validate(plugin_root: Path) -> list[str]:
    errors: list[str] = []
    if not plugin_root.is_dir():
        return [f"plugin root does not exist: {plugin_root}"]

    manifest = load_json_object(plugin_root / ".codex-plugin" / "plugin.json", errors)
    if manifest is not None:
        reject_todos(manifest, "$", errors)
        validate_manifest(plugin_root, manifest, errors)
    validate_factory_contracts(plugin_root, errors)

    for required_file in (
        "README.md",
        "LICENSE",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "docs/installation.md",
        "docs/usage.md",
        "docs/vision.md",
        "docs/runtime-modes.md",
        "docs/agent-packets.md",
        "docs/agent-adapters.md",
        "docs/dashboard.md",
        "docs/configuration.md",
        "docs/cli.md",
        "docs/schema.md",
        "requirements-dashboard.txt",
        "dashboard/package.json",
        "dashboard/package-lock.json",
        "dashboard/dist/index.html",
        "examples/codex-orchestrated-session.md",
        "examples/basic-factory/session.md",
    ):
        if not (plugin_root / required_file).is_file():
            errors.append(f"missing open-source hygiene file `{required_file}`")

    if not (plugin_root / "tests").is_dir():
        errors.append("missing `tests/` directory")
    return errors


def validate_factory_contracts(plugin_root: Path, errors: list[str]) -> None:
    orchestration = plugin_root / "skills" / "agentic-factory-orchestration" / "SKILL.md"
    operational = plugin_root / "skills" / "agentic-factory" / "SKILL.md"
    required_orchestration_markers = (
        "## Required Sequence",
        "This sequence is a contract, not a recommendation.",
        "run `factory.py up --background`",
        "PAUSE.",
        "factory operations may begin",
        "Before step 5 is complete, do not run `baton create`",
    )
    required_operational_markers = (
        "## Build Request Gate",
        "start with baton commands",
        "`agentic-factory-orchestration` and follow its Required Sequence",
        "the agent runs `factory.py up --background`",
    )
    validate_text_markers(orchestration, required_orchestration_markers, errors)
    validate_text_markers(operational, required_operational_markers, errors)


def validate_text_markers(path: Path, markers: tuple[str, ...], errors: list[str]) -> None:
    if not path.is_file():
        return
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"unable to read `{path}`: {exc}")
        return
    for marker in markers:
        if marker not in contents:
            errors.append(f"`{path.relative_to(path.parents[2])}` is missing required contract marker: {marker}")


def load_json_object(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append("missing `.codex-plugin/plugin.json`")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"unable to read `{path}`: {exc}")
        return None
    except json.JSONDecodeError as exc:
        errors.append(f"`{path}` is invalid JSON: {exc}")
        return None
    if not isinstance(payload, dict):
        errors.append("`.codex-plugin/plugin.json` must contain a JSON object")
        return None
    return payload


def reject_todos(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        if TODO_MARKER in value:
            errors.append(f"{path} contains a `[TODO: ...]` placeholder")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_todos(item, f"{path}[{index}]", errors)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            reject_todos(item, f"{path}.{key}", errors)


def validate_manifest(plugin_root: Path, manifest: dict[str, Any], errors: list[str]) -> None:
    allowed_keys = {
        "id",
        "name",
        "version",
        "description",
        "skills",
        "apps",
        "mcpServers",
        "interface",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
    }
    reject_unknown_fields(manifest, allowed_keys, "plugin.json", errors)

    require_non_empty_string(manifest, "name", errors)
    version = require_non_empty_string(manifest, "version", errors)
    if version and SEMVER_RE.fullmatch(version) is None:
        errors.append("plugin.json field `version` must be semver")
    require_non_empty_string(manifest, "description", errors)
    require_non_empty_string(manifest, "license", errors)

    author = require_object(manifest, "author", errors)
    if author is not None:
        reject_unknown_fields(author, {"name", "email", "url"}, "author", errors)
        require_non_empty_string(author, "name", errors, prefix="author")

    skills = manifest.get("skills")
    if normalize_contract_path(skills) != "skills":
        errors.append("plugin.json field `skills` must resolve to `skills`")

    if "apps" in manifest:
        errors.append("plugin.json field `apps` should be omitted unless `.app.json` exists")
    if "mcpServers" in manifest:
        errors.append("plugin.json field `mcpServers` should be omitted unless `.mcp.json` exists")

    interface = require_object(manifest, "interface", errors)
    if interface is not None:
        validate_interface(plugin_root, interface, errors)

    validate_skills(plugin_root, errors)


def validate_interface(plugin_root: Path, interface: dict[str, Any], errors: list[str]) -> None:
    allowed_keys = {
        "displayName",
        "shortDescription",
        "longDescription",
        "developerName",
        "category",
        "capabilities",
        "websiteURL",
        "privacyPolicyURL",
        "termsOfServiceURL",
        "brandColor",
        "composerIcon",
        "logo",
        "screenshots",
        "defaultPrompt",
        "default_prompt",
    }
    reject_unknown_fields(interface, allowed_keys, "interface", errors)
    for key in (
        "displayName",
        "shortDescription",
        "longDescription",
        "developerName",
        "category",
    ):
        require_non_empty_string(interface, key, errors, prefix="interface")

    if "defaultPrompt" not in interface and "default_prompt" not in interface:
        errors.append("plugin.json field `interface.defaultPrompt` is required")

    capabilities = interface.get("capabilities")
    if not isinstance(capabilities, list) or not all(
        isinstance(value, str) and value.strip() for value in capabilities
    ):
        errors.append("plugin.json field `interface.capabilities` must be an array of strings")

    brand_color = interface.get("brandColor")
    if brand_color is not None and (
        not isinstance(brand_color, str) or HEX_COLOR_RE.fullmatch(brand_color) is None
    ):
        errors.append("plugin.json field `interface.brandColor` must use `#RRGGBB`")

    for key in ("composerIcon", "logo"):
        validate_asset_path(plugin_root, interface.get(key), f"interface.{key}", errors)

    screenshots = interface.get("screenshots", [])
    if not isinstance(screenshots, list):
        errors.append("plugin.json field `interface.screenshots` must be an array")
    else:
        for index, raw_path in enumerate(screenshots):
            validate_asset_path(plugin_root, raw_path, f"interface.screenshots[{index}]", errors)


def validate_skills(plugin_root: Path, errors: list[str]) -> None:
    skills_root = plugin_root / "skills"
    if not skills_root.is_dir():
        errors.append("missing `skills/` directory")
        return
    skill_dirs = [path for path in sorted(skills_root.iterdir()) if path.is_dir()]
    if not skill_dirs:
        errors.append("`skills/` must contain at least one skill")
        return

    for skill_root in skill_dirs:
        skill_md = skill_root / "SKILL.md"
        if not skill_md.is_file():
            errors.append(f"skill `{skill_root.name}` is missing `SKILL.md`")
            continue
        try:
            contents = skill_md.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"unable to read skill `{skill_root.name}`: {exc}")
            continue
        reject_todos(contents, f"skill `{skill_root.name}`", errors)
        frontmatter = parse_frontmatter(contents, skill_root.name, errors)
        if frontmatter is None:
            continue
        name = frontmatter.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"skill `{skill_root.name}` frontmatter field `name` must be non-empty")
        description = frontmatter.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append(
                f"skill `{skill_root.name}` frontmatter field `description` must be non-empty"
            )


def parse_frontmatter(
    contents: str,
    skill_name: str,
    errors: list[str],
) -> dict[str, Any] | None:
    if not contents.startswith("---\n"):
        errors.append(f"skill `{skill_name}` must start with YAML frontmatter")
        return None
    end = contents.find("\n---", 4)
    if end == -1:
        errors.append(f"skill `{skill_name}` frontmatter is not closed")
        return None

    result: dict[str, Any] = {}
    for line_number, raw_line in enumerate(contents[4:end].splitlines(), start=2):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            errors.append(
                f"skill `{skill_name}` frontmatter line {line_number} must use `key: value`"
            )
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            errors.append(f"skill `{skill_name}` frontmatter line {line_number} has empty key")
            continue
        if not value:
            result[key] = ""
        elif value in {"true", "false"}:
            result[key] = value == "true"
        elif (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            result[key] = value[1:-1]
        else:
            result[key] = value
    return result


def reject_unknown_fields(
    payload: dict[str, Any],
    allowed: set[str],
    label: str,
    errors: list[str],
) -> None:
    for key in sorted(set(payload) - allowed):
        errors.append(f"{label} field `{key}` is not accepted")


def require_object(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
) -> dict[str, Any] | None:
    value = payload.get(key)
    if not isinstance(value, dict):
        errors.append(f"plugin.json field `{key}` must be an object")
        return None
    return value


def require_non_empty_string(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str | None = None,
) -> str | None:
    value = payload.get(key)
    field = f"{prefix}.{key}" if prefix else key
    if not isinstance(value, str) or not value.strip():
        errors.append(f"plugin.json field `{field}` must be a non-empty string")
        return None
    return value


def normalize_contract_path(raw_path: Any) -> str | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    path = PurePosixPath(raw_path.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return None
    return path.as_posix().lstrip("./").rstrip("/") or None


def validate_asset_path(
    plugin_root: Path,
    raw_path: Any,
    field: str,
    errors: list[str],
) -> None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        errors.append(f"plugin.json field `{field}` must be a non-empty relative path")
        return
    candidate = PurePosixPath(raw_path.replace("\\", "/"))
    if candidate.is_absolute() or any(part in {"", ".."} for part in candidate.parts):
        errors.append(f"plugin.json field `{field}` must stay inside the plugin archive")
        return
    resolved = (plugin_root / candidate.as_posix()).resolve()
    if not resolved.is_relative_to(plugin_root):
        errors.append(f"plugin.json field `{field}` must stay inside the plugin archive")
        return
    if not resolved.is_file():
        errors.append(f"plugin.json field `{field}` points to a missing file")


if __name__ == "__main__":
    raise SystemExit(main())
