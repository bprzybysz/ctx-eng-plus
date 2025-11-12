#!/usr/bin/env python3
"""
CE Framework Project Initializer - Core Module

Implements the 4-phase pipeline for installing CE framework on target projects:
1. Extract: Unpack ce-infrastructure.xml to target project
2. Blend: Merge framework + user files (CLAUDE.md, settings, commands)
3. Initialize: Run uv sync to install dependencies
4. Verify: Validate installation and report status
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from ce.config_loader import BlendConfig


class ProjectInitializer:
    """
    Core initializer for CE Framework installation on target projects.

    Handles 4-phase pipeline:
    - extract: Unpack repomix package to .ce/
    - blend: Merge framework + user files
    - initialize: Install Python dependencies
    - verify: Validate installation
    """

    def __init__(self, target_project: Path, dry_run: bool = False):
        """
        Initialize ProjectInitializer.

        Args:
            target_project: Path to target project root
            dry_run: If True, show actions without executing
        """
        self.target_project = Path(target_project).resolve()
        self.dry_run = dry_run

        # Paths to framework packages (in ctx-eng-plus repo)
        self.ctx_eng_root = Path(__file__).parent.parent.parent.resolve()
        self.infrastructure_xml = self.ctx_eng_root / ".ce" / "ce-infrastructure.xml"
        self.workflow_xml = self.ctx_eng_root / ".ce" / "ce-workflow-docs.xml"

        # Load unified configuration (config.yml) from ctx-eng-plus repo
        config_path = self.ctx_eng_root / ".ce" / "config.yml"
        self.config = BlendConfig(config_path)

        # Resolve all paths from config (config-driven, not hardcoded)
        self.ce_dir = self.target_project / self.config.get_dir_path("ce_root")
        self.tools_dir = self.target_project / self.config.get_dir_path("tools")
        self.serena_dir = self.target_project / self.config.get_dir_path("serena_memories").parent

    def run(self, phase: str = "all") -> Dict:
        """
        Run initialization pipeline.

        Args:
            phase: Which phase(s) to run - "all", "extract", "blend", "initialize", "verify"

        Returns:
            Dict with status info for each phase executed

        Raises:
            ValueError: If invalid phase specified
        """
        valid_phases = ["all", "extract", "blend", "initialize", "verify"]
        if phase not in valid_phases:
            raise ValueError(f"Invalid phase '{phase}'. Must be one of: {valid_phases}\n🔧 Troubleshooting: Check input parameters and documentation")

        results = {}

        if phase == "all":
            results["extract"] = self.extract()
            results["blend"] = self.blend()
            results["initialize"] = self.initialize()
            results["verify"] = self.verify()
        else:
            # Run single phase
            method = getattr(self, phase)
            results[phase] = method()

        return results

    def extract(self) -> Dict:
        """
        Extract ce-infrastructure.xml to target project.

        Steps:
        1. Clean git state if repo is dirty (Fix 3)
        2. Check if ce-infrastructure.xml exists
        3. Extract to .ce/ directory
        4. Reorganize tools/ to .ce/tools/
        5. Copy ce-workflow-docs.xml to .ce/
        6. Flatten nested .ce/ structures (Fix 1)

        Returns:
            Dict with extraction status and file counts
        """
        import logging
        logger = logging.getLogger(__name__)

        status = {"success": False, "files_extracted": 0, "message": ""}

        # Fix 3: FIRST - Ensure clean git state before extraction
        if self.target_project.exists() and (self.target_project / ".git").exists():
            logger.info("Cleaning git state before extraction...")
            result = subprocess.run(
                ["git", "reset", "--hard", "HEAD"],
                cwd=self.target_project,
                capture_output=True,
                text=True
            )
            if result.returncode != 0 and "fatal:" not in result.stderr:
                logger.warning(f"Git reset warning: {result.stderr.strip()}")
            elif result.returncode == 0:
                logger.info("Git state reset successfully")

            # Clean untracked files
            result = subprocess.run(
                ["git", "clean", "-fd"],
                cwd=self.target_project,
                capture_output=True,
                text=True
            )
            logger.info("Untracked files cleaned")

        # Check for infrastructure package
        if not self.infrastructure_xml.exists():
            status["message"] = (
                f"❌ ce-infrastructure.xml not found at {self.infrastructure_xml}\n"
                f"🔧 Ensure you're running from ctx-eng-plus repo root"
            )
            return status

        if self.dry_run:
            status["success"] = True
            status["message"] = f"[DRY-RUN] Would extract to {self.ce_dir}"
            return status

        # Check for existing .ce/ directory - rename to .ce.old
        ce_old_dir = self.target_project / ".ce.old"
        renamed_existing = False
        if self.ce_dir.exists():
            # Remove old .ce.old if it exists
            if ce_old_dir.exists():
                shutil.rmtree(ce_old_dir)

            # Rename .ce to .ce.old
            shutil.move(str(self.ce_dir), str(ce_old_dir))
            renamed_existing = True

        try:
            # Import repomix_unpack module
            from ce.repomix_unpack import extract_files

            # Extract to temporary location first
            temp_extract = self.target_project / "tmp" / "ce-extraction"
            temp_extract.mkdir(parents=True, exist_ok=True)

            # Extract files
            files_extracted = extract_files(
                xml_path=self.infrastructure_xml,
                target_dir=temp_extract,
                verbose=False
            )

            if files_extracted == 0:
                status["message"] = "❌ No files extracted from package"
                return status

            # Reorganize extracted files to .ce/ structure
            self.ce_dir.mkdir(parents=True, exist_ok=True)

            # Reorganize extracted files:
            # - .ce/* contents → target/.ce/ (blend-config.yml, PRPs/, etc.)
            # - .serena/ → target/.serena/ (project root - configured as output/framework location)
            # - .claude/, tools/, CLAUDE.md, examples/ → target/.ce/ (framework files for blending)

            # First, move .ce/ contents to target/.ce/
            ce_extracted = temp_extract / ".ce"
            if ce_extracted.exists():
                for item in ce_extracted.iterdir():
                    dest = self.ce_dir / item.name
                    if dest.exists():
                        if dest.is_dir():
                            shutil.rmtree(dest)
                        else:
                            dest.unlink()
                    shutil.move(str(item), str(dest))

            # Then, move other extracted directories
            for item in temp_extract.iterdir():
                if item.name == ".ce":
                    continue  # Already processed

                # Special case: .serena goes to project root (from config)
                if item.name == ".serena":
                    dest = self.serena_dir.parent / item.name  # .serena/ at project root
                else:
                    dest = self.ce_dir / item.name

                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                shutil.move(str(item), str(dest))

            # Detect and flatten nested .ce/ structures (universal fix for any project)
            self._flatten_nested_structures(self.ce_dir)

            # Copy ce-workflow-docs.xml (reference package)
            if self.workflow_xml.exists():
                shutil.copy2(self.workflow_xml, self.ce_dir / "ce-workflow-docs.xml")

            # Copy unified config.yml (single source of truth)
            # Note: Extracted package may contain deprecated directories.yml/blend-config.yml
            # but config.yml is the authoritative configuration
            config_src = self.ctx_eng_root / ".ce" / "config.yml"
            config_dst = self.ce_dir / "config.yml"
            if config_src.exists():
                try:
                    shutil.copy2(config_src, config_dst)
                except Exception:
                    pass  # If copy fails, init-project will use source config from ctx-eng-plus

            # Cleanup temp directory
            shutil.rmtree(temp_extract.parent)

            status["success"] = True
            status["files_extracted"] = files_extracted

            # Include rename message if applicable
            if renamed_existing:
                status["message"] = (
                    f"ℹ️  Renamed existing .ce/ to .ce.old/\n"
                    f"💡 .ce.old/ will be included as additional context source during blend\n"
                    f"✅ Extracted {files_extracted} files to {self.ce_dir}"
                )
            else:
                status["message"] = f"✅ Extracted {files_extracted} files to {self.ce_dir}"

        except Exception as e:
            status["message"] = f"❌ Extraction failed: {str(e)}\n🔧 Check error details above"

        return status

    def _ensure_critical_files_exist(self) -> None:
        """
        Ensure critical files exist after blend phase.

        Creates CLAUDE.md and settings.local.json if they don't exist.
        This handles cases where blend didn't create them.

        Creates:
        - .claude/settings.local.json (from framework template)
        - CLAUDE.md (from framework template)
        """
        # Ensure .claude/ directory exists
        claude_dir = self.target_project / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)

        # Create settings.local.json if missing
        settings_file = claude_dir / "settings.local.json"
        if not settings_file.exists():
            # Try to get template from framework
            framework_settings = self.ctx_eng_root / ".claude" / "settings.local.json"
            if framework_settings.exists():
                shutil.copy2(framework_settings, settings_file)
            else:
                # Create minimal settings template
                import json
                minimal_settings = {
                    "allow": ["Bash(git:*)", "Bash(python:*)", "Bash(uv:*)", "Bash(pytest:*)"],
                    "ask": ["Bash(rm:*)", "Bash(mv:*)", "Bash(cp:*)"],
                    "deny": []
                }
                with open(settings_file, 'w') as f:
                    json.dump(minimal_settings, f, indent=2)

        # Create CLAUDE.md if missing
        claude_md = self.target_project / "CLAUDE.md"
        if not claude_md.exists():
            # Try to get template from framework
            framework_claude_md = self.ctx_eng_root / "CLAUDE.md"
            if framework_claude_md.exists():
                shutil.copy2(framework_claude_md, claude_md)
            else:
                # Create minimal CLAUDE.md template
                minimal_claude_md = """# Project Guide

This project uses the Context Engineering framework.

See `.claude/` for detailed configuration and examples.
"""
                claude_md.write_text(minimal_claude_md)

    def _flatten_nested_structures(self, root_dir: Path) -> None:
        """
        Recursively flatten nested .ce/ directories at any depth (Fix 1).

        Repomix extraction can sometimes create nested .ce/.ce/ structures
        which violates the config.yml expectation of a flat .ce/ directory.
        This method detects and flattens any nested structures with strong
        verification to ensure no nesting remains.

        Args:
            root_dir: Root directory to check for nested .ce/ structures

        Raises:
            RuntimeError: If nested .ce/ structures cannot be fully flattened
        """
        import logging
        logger = logging.getLogger(__name__)

        max_depth = 5
        attempt_count = 0

        while attempt_count < max_depth:
            nested_ce = root_dir / ".ce"

            # Verify nested .ce/ exists
            if not nested_ce.exists() or not nested_ce.is_dir():
                if attempt_count == 0:
                    logger.info("No nested .ce/ structures found")
                else:
                    logger.info(f"Nested structures fully flattened (took {attempt_count} iterations)")
                break

            # Check if nested_ce contains .ce/ subdirectory (indicates nesting)
            sub_nested = nested_ce / ".ce"
            if not sub_nested.exists():
                logger.info("No further nesting detected")
                break

            logger.warning(f"Detected nested .ce/ at iteration {attempt_count + 1} - flattening...")

            # Flatten this level: move all items from nested_ce up to root_dir
            try:
                for item in nested_ce.iterdir():
                    dest = root_dir / item.name

                    # Skip .ce directory itself (will be removed later)
                    if item.name == ".ce":
                        continue

                    # Handle conflicts
                    if dest.exists():
                        if dest.is_dir() and item.is_dir():
                            # Merge directory contents
                            logger.info(f"Merging {item.name}")
                            for subitem in item.iterdir():
                                subdest = dest / subitem.name
                                if subdest.exists():
                                    if subdest.is_dir():
                                        shutil.rmtree(subdest)
                                    else:
                                        subdest.unlink()
                                shutil.move(str(subitem), str(subdest))
                        else:
                            # Replace file or dir with file
                            logger.info(f"Overwriting {item.name}")
                            if dest.is_dir():
                                shutil.rmtree(dest)
                            else:
                                dest.unlink()
                            shutil.move(str(item), str(dest))
                    else:
                        shutil.move(str(item), str(dest))

                # Remove the now-empty nested .ce/ directory
                try:
                    shutil.rmtree(nested_ce)
                    logger.info(f"Removed nested .ce/ level {attempt_count + 1}")
                except Exception as e:
                    logger.error(f"Failed to remove nested .ce/ at level {attempt_count + 1}: {e}")
                    break

            except Exception as e:
                logger.error(f"Error during flattening iteration {attempt_count + 1}: {e}")
                break

            attempt_count += 1

        # VERIFICATION: Check for remaining nested structures
        nested_check = list((root_dir / ".ce").glob("**/.ce")) if (root_dir / ".ce").exists() else []
        if nested_check:
            error_msg = f"VERIFICATION FAILED: {len(nested_check)} nested .ce/ still exist after flattening:\n"
            for nc in nested_check[:5]:  # Show first 5
                error_msg += f"  - {nc}\n"
            logger.error(error_msg)
            raise RuntimeError("Nested .ce/ structures not fully flattened")
        else:
            logger.info("✓ VERIFICATION PASSED: No nested .ce/ structures")

    def _fix_yaml_indentation(self, yaml_path: Path) -> None:
        """
        Fix YAML indentation in extracted config files.

        Repomix sometimes strips indentation when packing. This method loads
        the YAML and re-dumps it with correct indentation.

        Args:
            yaml_path: Path to YAML file to fix
        """
        try:
            import yaml

            # Load the YAML
            with open(yaml_path) as f:
                data = yaml.safe_load(f)

            if data is None:
                return  # Empty or unparseable file

            # Re-dump with proper indentation
            with open(yaml_path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, indent=2)
        except Exception:
            # If fixing fails, continue anyway (shouldn't block initialization)
            pass

    def blend(self) -> Dict:
        """
        Blend framework + user files.

        Delegates to: uv run ce blend --all --target-dir <target>

        Returns:
            Dict with blend status and stdout/stderr
        """
        status = {"success": False, "stdout": "", "stderr": ""}

        if self.dry_run:
            status["success"] = True
            status["stdout"] = f"[DRY-RUN] Would run: uv run ce blend --all --target-dir {self.target_project}"
            return status

        try:
            # Use unified config.yml (single source of truth from ctx-eng-plus)
            # The blend tool will read from this config in target project
            unified_config = self.ctx_eng_root / ".ce" / "config.yml"

            # Run blend command - it will use config.yml for all path decisions
            result = subprocess.run(
                ["uv", "run", "ce", "blend", "--all",
                 "--config", str(unified_config),
                 "--target-dir", str(self.target_project)],
                cwd=self.ctx_eng_root / "tools",
                capture_output=True,
                text=True,
                timeout=120
            )

            status["stdout"] = result.stdout
            status["stderr"] = result.stderr
            status["success"] = result.returncode == 0

            if not status["success"]:
                status["message"] = (
                    f"❌ Blend phase failed (exit code {result.returncode})\n"
                    f"🔧 Check blend tool output:\n{result.stderr}"
                )
            else:
                # Cleanup: Remove framework .claude/ and CLAUDE.md from .ce/ after blending
                # Config specifies these should only exist at root, not in .ce/
                ce_claude = self.ce_dir / ".claude"
                ce_claude_md = self.ce_dir / "CLAUDE.md"

                if ce_claude.exists():
                    shutil.rmtree(ce_claude)
                if ce_claude_md.exists():
                    ce_claude_md.unlink()

                # Post-blend file creation: ensure critical files exist
                self._ensure_critical_files_exist()

                # Check if .ce.old exists to mention it
                ce_old_dir = self.target_project / ".ce.old"
                if ce_old_dir.exists():
                    status["message"] = (
                        "✅ Blend phase completed\n"
                        "💡 Note: .ce.old/ detected - blend tool will include it as additional source"
                    )
                else:
                    status["message"] = "✅ Blend phase completed"

        except subprocess.TimeoutExpired:
            status["message"] = "❌ Blend phase timed out (120s limit)\n🔧 Check for hanging processes"
        except FileNotFoundError:
            status["message"] = (
                "❌ uv not found in PATH\n"
                "🔧 Install UV: curl -LsSf https://astral.sh/uv/install.sh | sh"
            )
        except Exception as e:
            status["message"] = f"❌ Blend phase failed: {str(e)}"

        return status

    def initialize(self) -> Dict:
        """
        Initialize Python environment.

        Runs: uv sync in .ce/tools/ directory

        Returns:
            Dict with initialization status and command output
        """
        status = {"success": False, "stdout": "", "stderr": ""}

        if not self.tools_dir.exists():
            status["message"] = (
                f"❌ Tools directory not found: {self.tools_dir}\n"
                f"🔧 Run extract phase first"
            )
            return status

        if self.dry_run:
            status["success"] = True
            status["stdout"] = f"[DRY-RUN] Would run: uv sync in {self.tools_dir}"
            return status

        try:
            # Run uv sync
            result = subprocess.run(
                ["uv", "sync"],
                cwd=self.tools_dir,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes for dependency installation
            )

            status["stdout"] = result.stdout
            status["stderr"] = result.stderr
            status["success"] = result.returncode == 0

            if not status["success"]:
                status["message"] = (
                    f"❌ UV sync failed (exit code {result.returncode})\n"
                    f"🔧 Check pyproject.toml and dependency versions:\n{result.stderr}"
                )
            else:
                status["message"] = "✅ Python environment initialized"

        except subprocess.TimeoutExpired:
            status["message"] = "❌ UV sync timed out (300s limit)\n🔧 Check network connection or package mirrors"
        except FileNotFoundError:
            status["message"] = (
                "❌ uv not found in PATH\n"
                "🔧 Install UV: curl -LsSf https://astral.sh/uv/install.sh | sh"
            )
        except Exception as e:
            status["message"] = f"❌ Initialize phase failed: {str(e)}"

        return status

    def verify(self) -> Dict:
        """
        Verify installation.

        Checks:
        1. Critical files exist (.ce/tools/, .claude/, .serena/)
        2. settings.local.json is valid JSON
        3. pyproject.toml exists
        4. Reports summary

        Returns:
            Dict with verification results and warnings
        """
        status = {"success": True, "warnings": [], "checks": []}

        # Critical files to check
        critical_files = [
            self.ce_dir / "tools" / "pyproject.toml",
            self.target_project / ".claude" / "settings.local.json",
            self.target_project / ".serena" / "memories",
            self.ce_dir / "RULES.md"
        ]

        for file_path in critical_files:
            if file_path.exists():
                status["checks"].append(f"✅ {file_path.relative_to(self.target_project)}")
            else:
                status["warnings"].append(f"⚠️  Missing: {file_path.relative_to(self.target_project)}")
                status["success"] = False

        # Validate settings.local.json
        settings_file = self.target_project / ".claude" / "settings.local.json"
        if settings_file.exists():
            try:
                with open(settings_file) as f:
                    json.load(f)
                status["checks"].append("✅ settings.local.json is valid JSON")
            except json.JSONDecodeError as e:
                status["warnings"].append(f"⚠️  Invalid JSON in settings.local.json: {str(e)}")
                status["success"] = False
        else:
            status["warnings"].append("⚠️  settings.local.json not found")

        # Check Python installation
        venv_dir = self.tools_dir / ".venv"
        if venv_dir.exists():
            status["checks"].append("✅ Python virtual environment created")
        else:
            status["warnings"].append("⚠️  Virtual environment not found (run initialize phase)")

        # Summary message
        if status["success"]:
            status["message"] = f"✅ Installation verified ({len(status['checks'])} checks passed)"
        else:
            status["message"] = (
                f"⚠️  Installation incomplete ({len(status['warnings'])} warnings)\n"
                f"🔧 Review warnings above and re-run failed phases"
            )

        return status


def main():
    """CLI entry point for testing."""
    if len(sys.argv) < 2:
        print("Usage: python init_project.py <target-project-path> [--dry-run]")
        sys.exit(1)

    target = Path(sys.argv[1])
    dry_run = "--dry-run" in sys.argv

    initializer = ProjectInitializer(target, dry_run=dry_run)
    results = initializer.run(phase="all")

    # Print results
    for phase, result in results.items():
        print(f"\n=== Phase: {phase} ===")
        print(result.get("message", "No message"))
        if not result.get("success", True):
            sys.exit(1)

    print("\n✅ Initialization complete!")


if __name__ == "__main__":
    main()
