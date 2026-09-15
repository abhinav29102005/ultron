# Migration Guide: Resolving File Structure Conflicts

This guide is for developers who were working on active branches prior to the **August 2026 File Structure Reorganization**. 

If you are trying to merge your older branch into `main` (or rebase onto `main`) and are hitting massive merge conflicts, it is because we completely cleaned up the root directory and relocated/deleted several ad-hoc scripts.

Follow this guide to easily migrate your changes and resolve those conflicts.

---

## 1. Moved Scratch & Test Scripts

We moved 13 ad-hoc testing and debugging scripts from the root directory into the new `tests/scratch/` folder. 

**Important:** The `tests/scratch/` folder has been added to `.gitignore`. These files are no longer tracked by Git. 

If you made changes to any of the following files on your branch, **Git will show them as deleted on `main`**. If you want to keep your changes, you must manually move your updated file to `tests/scratch/` locally, but they will not be committed to `main`.

*Files moved to `tests/scratch/` (now ignored):*
- `debug_202.py`
- `debug_all_links.py`
- `debug_ddg.py`
- `debug_lite.py`
- `debug_parser.py`
- `debug_search_url.py`
- `qwen_test.py`
- `speechtesting.py`
- `test_lite_ddg.py`
- `test_search.py`
- `test_web_intent.py`
- `test_web_skill.py`
- `testing.py`

**How to resolve the conflict:** Accept the deletion on `main`.

---

## 2. Bootstrapper Moved

The root `bootstrap.py` file was moved to the `scripts/` directory to keep the root clean.

- **Old Path:** `/bootstrap.py`
- **New Path:** `/scripts/bootstrap.py`

**How to resolve the conflict:** If you made changes to `bootstrap.py`, apply those changes to `scripts/bootstrap.py` instead.

---

## 3. Unused Wakeword Directory Deleted

The `wakeword/model.py` file and the `wakeword/` directory were deleted because they were unused scaffold files (the actual wake word detector is at `speech/wake_word/detector.py`).

**How to resolve the conflict:** Accept the deletion.

---

## 4. `pyproject.toml` Updates

Several changes were made to `pyproject.toml`:
1. The `wakeword` package was removed from the hatch build targets.
2. The `intelligence`, `memory`, and `ui` packages were **added** to the hatch build targets.
3. Added `--ignore=tests/scratch` to the `pytest` addopts so pytest no longer crashes trying to run the ignored scratch scripts.

**How to resolve the conflict:** Accept the changes from `main`. If you added new dependencies on your branch, ensure they are kept, but keep the `packages` list and `addopts` from `main`.

---

## 5. New Files Added (No Conflicts Expected)

We added several new files that should not cause conflicts, but you should be aware of them:

1. **`assets/friday-banner.jpg`**: The new project logo.
2. **`README.md`**: Completely rewritten with comprehensive documentation.
3. **`scripts/install.sh`**: The payload for the new one-line installer.
4. **`deploy/installer/`**: The Cloudflare Worker project that serves the installer.
5. **`.github/workflows/deploy-installer.yml`**: GitHub Action for the installer.

---

## Summary Checklist for Rebasing/Merging

When you run `git merge main` (or `git rebase main`):

1. `git rm` all the `debug_*.py` and `test_*.py` files in the root.
2. `git rm wakeword/model.py`.
3. Apply any changes you made to `bootstrap.py` to `scripts/bootstrap.py`.
4. Accept `main`'s version of `.gitignore`.
5. Carefully merge `pyproject.toml` (keep your new dependencies, but accept `main`'s package list and pytest config).
