---
prp_id: PRP-49
feature_name: Iteration 7 - Validate Root Cause Fixes (Before Real Project)
status: pending
created: 2025-11-12T12:00:00Z
updated: 2025-11-12T12:00:00Z
complexity: high
estimated_hours: 3.5
dependencies: init_project.py, memories.py, blender.py, validation-gates
issue: TBD
---

# Iteration 7: Validate Root Cause Fixes (Before Applying to Real Project)

## 1. TL;DR

**Objective**: Validate all 3 root cause fixes work correctly on fresh install before applying to real certinia project

**What**:
- Phase 1: Implement extraction fix, blend preservation fix, validation fix (2-3h)
- Phase 2: Test on fresh install with 23 user memories (20min)
- Phase 3: Run 6-gate validation (10min)

**Why**: Iteration 6 revealed critical issues with knowledge loss and structural violations. Must validate fixes work before applying to real project.

**Success Criteria**: All fixes working + full knowledge preserved (47 memories) + 6-gates PASS

**Effort**: ~3.5 hours total (2.5-3h implementation + 20min testing + 10min validation)

**Dependencies**:
- Iteration 6 analysis documents (root cause clarification)
- PRP-INIT-PROJECT-ROOT-CAUSE-FIXES.md (identifies 3 universal fixes)
- certinia-test-target baseline (fresh copy for safe testing)

---

## 2. Context

### Background

**Iteration 6 Critical Findings**:
1. Double-nesting `.ce/.ce/` structure violates config.yml expectations
2. Knowledge loss: 23 project memories deleted without framework equivalents
3. Git inconsistency: mixed staged deletions + untracked framework memories

**Root Cause Analysis** (from ITERATION-6-CERTINIA-CRITICAL-FINDINGS.md):
1. **Extraction Issue**: init_project.py:extract() doesn't detect/flatten nested .ce/ directories
2. **Blend Issue**: Directory is cleared BEFORE preservation logic runs (preservation code exists at lines 191-232 in memories.py, but never executes)
3. **Validation Issue**: No DataLossValidator prevents knowledge loss during commit

**Why Iteration 7 Matters**:
- Iteration 6 ran on REAL certinia project - found critical issues but unsafe to commit
- Must validate fixes work on FRESH INSTALL before touching real project
- After Iteration 7 passes, can confidently apply fixes to real certinia with Option A (preserve all 23 memories)

### Constraints and Considerations

**Safety First**:
- Must use fresh copy (certinia-test-iter7) for all testing
- Real certinia stays untouched until validation passes
- Can reset to main HEAD at any time

**Success Criteria**:
- Fix 1: No .ce/.ce/ nesting at any depth
- Fix 2: All 23 user memories preserved (not deleted)
- Fix 3: DataLossValidator detects preservation, audit passes
- Full: All 6-gate validation PASS

**Knowledge Preservation**:
- Before blend: 23 user memories
- After blend: 23 user + 24 framework = 47 total
- CRITICAL: Zero file deletions allowed (only additions)

### Documentation References

- ITERATION-6-CERTINIA-CRITICAL-FINDINGS.md (issue overview)
- KNOWLEDGE-LOSS-AUDIT.md (detailed loss analysis)
- ITERATION-6-ACTION-PLAN.md (remediation phases)
- PRP-INIT-PROJECT-ROOT-CAUSE-FIXES.md (3 universal fixes)
- ITERATION-7-VALIDATION-PLAN.md (detailed phase breakdown)

---

## 3. Implementation Steps

### Phase 1: Apply Root Cause Fixes (2-3 hours)

**Duration**: 2-3 hours
**Scope**: Implement all 3 fixes to make init-project safe for real projects

#### Step 1.1: Fix Extraction (1 hour) - `tools/ce/init_project.py`

**Problem**: Extraction creates nested .ce/ directories

**Location**: init_project.py, extract() method, lines 111-140

**Solution**: Add recursive nested structure detection and flattening

**Code to add** (after line 139, moving temp/.ce/ contents):

```python
# Detect and flatten nested .ce/ structures (universal fix for any project)
self._flatten_nested_structures(self.ce_dir)

def _flatten_nested_structures(self, root_dir: Path) -> None:
    """Recursively flatten nested .ce/ directories at any depth."""
    nested_ce = root_dir / ".ce"
    if nested_ce.exists() and nested_ce.is_dir():
        logger.warning(f"Detected nested .ce/ structure - flattening...")

        for item in nested_ce.iterdir():
            dest = root_dir / item.name
            if dest.exists():
                if dest.is_dir() and item.is_dir():
                    # Merge directory contents
                    for subitem in item.iterdir():
                        shutil.move(str(subitem), str(dest / subitem.name))
                else:
                    # Replace file or dir with file
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                    shutil.move(str(item), str(dest))
            else:
                shutil.move(str(item), str(dest))

        shutil.rmtree(nested_ce)
        self._flatten_nested_structures(root_dir)  # Recursive check for deeper nesting
        logger.info("Nested directory structure flattened")
```

**Verification**:
```bash
# After extraction, verify NO nested .ce/ exists
find .ce -name ".ce" -type d
# Expected: No results (empty)
```

#### Step 1.2: Fix Blend Strategy (1 hour) - `tools/ce/blending/strategies/memories.py`

**Problem**: Directory cleared BEFORE preservation logic runs

**Location**: memories.py, blend() method (around line 170-190)

**Current problematic code**:
```python
output_path.mkdir(parents=True, exist_ok=True)  # Creates but clears existing
```

**Solution**: Preserve existing directory content before blending

**Code to change**:
```python
# BEFORE: mkdir clears directory
output_path.mkdir(parents=True, exist_ok=True)

# AFTER: Preserve existing content, THEN blend
if output_path.exists():
    # Directory exists - preserve user files for target-only logic
    existing_user_files = self._list_memory_files(output_path)
else:
    # Directory doesn't exist - create it
    output_path.mkdir(parents=True, exist_ok=True)
    existing_user_files = []

# Ensure preservation logic runs (already implemented, just needs chance to execute)
if target_path:
    target_only = set(target_files) - set(framework_files)
    for target_file in target_only:
        self._preserve_target_memory(
            target_file=target_path / target_file,
            output_file=output_path / target_file
        )
```

**Verification**:
```bash
# Before blend: Check memory count
ls /Users/bprzybyszi/nc-src/certinia-test-iter7/.serena/memories/ | wc -l
# Expected: 23 (user memories)

# After blend: Check memory count
ls /Users/bprzybyszi/nc-src/certinia-test-iter7/.serena/memories/ | wc -l
# Expected: 47 (23 user + 24 framework)

# Verify no files deleted
ls .serena/memories/ | sort > /tmp/after.txt
# All 23 original files should still be present
```

#### Step 1.3: Add Data Loss Prevention (30 minutes) - `tools/ce/blender.py`

**Problem**: No validation prevents knowledge loss

**Location**: blender.py, blend() method (main orchestration)

**Solution**: Add DataLossValidator before/after blend

**Code to add** (before blend execution):

```python
# Capture state before blend for validation
validator = DataLossValidator(self.config)
validator.capture_before_state(self.target_project)

# Run blend
result = subprocess.run([...])

# Capture state after blend
validator.capture_after_state(self.target_project)

# Validate no knowledge loss occurred
try:
    validator.validate()
except ValueError as e:
    logger.error(f"Blend would delete user files: {e}")
    raise

# Generate audit report
audit_report = validator.generate_audit_report()
logger.info(f"Blend audit: {audit_report}")
```

**DataLossValidator Implementation** (new class):

```python
class DataLossValidator:
    """Validates that blend operations don't delete user knowledge."""

    def __init__(self, config):
        self.config = config
        self.before_state = {}
        self.after_state = {}

    def capture_before_state(self, project_path):
        """Capture file counts before blend."""
        self.before_state = {
            'memories': self._count_files(project_path / '.serena' / 'memories'),
            'examples': self._count_files(project_path / 'examples'),
            'prps': self._count_files(project_path / '.serena' / 'prps' / 'executed'),
        }

    def capture_after_state(self, project_path):
        """Capture file counts after blend."""
        self.after_state = {
            'memories': self._count_files(project_path / '.serena' / 'memories'),
            'examples': self._count_files(project_path / 'examples'),
            'prps': self._count_files(project_path / '.serena' / 'prps' / 'executed'),
        }

    def validate(self):
        """Fail if user files would be deleted."""
        for domain, before_count in self.before_state.items():
            after_count = self.after_state.get(domain, 0)
            if after_count < before_count:
                raise ValueError(
                    f"Blend would delete {before_count - after_count} {domain} files"
                )

    def generate_audit_report(self):
        """Generate human-readable audit report."""
        return {
            'memories_preserved': self.after_state['memories'] >= self.before_state['memories'],
            'examples_preserved': self.after_state['examples'] >= self.before_state['examples'],
            'prps_preserved': self.after_state['prps'] >= self.before_state['prps'],
            'total_files_before': sum(self.before_state.values()),
            'total_files_after': sum(self.after_state.values()),
        }

    @staticmethod
    def _count_files(path):
        """Count files in directory (recursive)."""
        if not path.exists():
            return 0
        return sum(1 for _ in path.rglob('*') if _.is_file())
```

**Verification**:
```bash
# Blend should complete without deletion warnings
# Check audit report shows all preserved counts >= before counts
grep "preserved: true" audit_report.json
# Expected: All domains show preserved=true
```

---

### Phase 2: Fresh Install Test (20 minutes)

**Duration**: 20 minutes
**Scope**: Test all fixes on fresh copy with 23 user memories

#### Step 2.1: Create Test Environment (5 min)

```bash
cd /Users/bprzybyszi/nc-src

# Create fresh test copy from baseline
cp -r certinia certinia-test-iter7

# Add 23 user memories (restore from git history)
mkdir -p certinia-test-iter7/.serena/memories
git -C certinia show iteration-6:.serena/memories/ | \
  while read -r file; do
    git -C certinia show "iteration-6:.serena/memories/$file" \
      > "certinia-test-iter7/.serena/memories/$file"
  done

# Verify 23 memories present
echo "Before blend: $(ls certinia-test-iter7/.serena/memories/ | wc -l) files"
```

#### Step 2.2: Run Extraction (5 min)

```bash
cd /Users/bprzybyszi/nc-src/ctx-eng-plus

# Run extract phase with Fix 1 applied
uv run ce init-project \
  --target /Users/bprzybyszi/nc-src/certinia-test-iter7 \
  --phase extract

# Verify: No .ce/.ce/ nesting
find /Users/bprzybyszi/nc-src/certinia-test-iter7/.ce -name ".ce" -type d
# Expected: No results (Fix 1 works)

echo "✓ Fix 1 verified: No nested .ce/ structures"
```

#### Step 2.3: Run Blend (5 min)

```bash
# Run blend phase with Fix 2 & 3 applied
uv run ce init-project \
  --target /Users/bprzybyszi/nc-src/certinia-test-iter7 \
  --phase blend

# Verify: 47 total memories (23 user + 24 framework)
echo "After blend: $(ls /Users/bprzybyszi/nc-src/certinia-test-iter7/.serena/memories/ | wc -l) files"
# Expected: 47

# Verify: User memories preserved
ls /Users/bprzybyszi/nc-src/certinia-test-iter7/.serena/memories/ | grep -E "cost_center|india_geographic|master_project"
# Expected: All 3 files present (user-specific domain files)

echo "✓ Fix 2 verified: All 23 user memories preserved"
echo "✓ Fix 3 verified: DataLossValidator passed (audit clean)"
```

#### Step 2.4: Git State Check (5 min)

```bash
cd /Users/bprzybyszi/nc-src/certinia-test-iter7

# Verify git state is clean (no mixed staged/untracked)
git status
# Expected: Clean tree (no staged deletions + untracked additions)

echo "✓ Git state consistent after blend"
```

---

### Phase 3: Full Validation Gates (10 minutes)

**Duration**: 10 minutes
**Scope**: Run 6-gate validation on test-iter7

```bash
cd /Users/bprzybyszi/nc-src/ctx-eng-plus

# Run all 6 validation gates
python tools/ce/validation/gates.py \
  --target /Users/bprzybyszi/nc-src/certinia-test-iter7 \
  --all-gates

# Expected output:
# Gate 1: System Structure ✓ PASS
# Gate 2: Examples Migration ✓ PASS
# Gate 3: PRPs Migration ✓ PASS
# Gate 4: Memories Migration ✓ PASS (with 47 memories)
# Gate 5: CLAUDE.md Blending ✓ PASS
# Gate 6: Deduplication ✓ PASS

echo "✓ All 6 gates PASS with preserved user knowledge"
```

---

## 4. Validation Gates

### Gate 1: Fix 1 Verification (Extraction)

**Objective**: Verify nested .ce/ structures are flattened

**Command**:
```bash
find /Users/bprzybyszi/nc-src/certinia-test-iter7/.ce -name ".ce" -type d | wc -l
```

**Expected**: `0` (no nested .ce/ directories at any depth)

**Failure Recovery**: Re-examine _flatten_nested_structures() logic, ensure recursive call works correctly

---

### Gate 2: Fix 2 Verification (Blend Preservation)

**Objective**: Verify all 23 user memories preserved

**Command**:
```bash
# Before blend
BEFORE=$(ls /Users/bprzybyszi/nc-src/certinia/.serena/memories/ 2>/dev/null | wc -l)

# After blend
AFTER=$(ls /Users/bprzybyszi/nc-src/certinia-test-iter7/.serena/memories/ | wc -l)

echo "Before: $BEFORE, After: $AFTER"
# Expected: Before >= 23, After = $BEFORE + 24 (or 47 if exactly 23 before)
```

**Expected**: After count >= Before count (no deletions, only additions)

**Failure Recovery**: Check if output directory is being cleared before preservation logic runs; add logging to blend strategy

---

### Gate 3: Fix 3 Verification (Validation)

**Objective**: Verify DataLossValidator prevents deletion

**Command**:
```bash
grep -i "preserved\|deletion\|loss" /Users/bprzybyszi/nc-src/certinia-test-iter7/audit_report.json
```

**Expected**: All domains show `preserved: true`, 0 deletions

**Failure Recovery**: Improve capture_before_state() and capture_after_state() logic; verify file counting is accurate

---

### Gate 4: Full System Structure

**Objective**: Run complete 6-gate validation

**Command**:
```bash
cd /Users/bprzybyszi/nc-src/ctx-eng-plus
python tools/ce/validation/gates.py \
  --target /Users/bprzybyszi/nc-src/certinia-test-iter7 \
  --all-gates --verbose
```

**Expected**: All 6 gates PASS

**Success Criteria**:
- Gate 1: System Structure ✓
- Gate 2: Examples Migration ✓
- Gate 3: PRPs Migration ✓
- Gate 4: Memories Migration ✓ (with 47 preserved memories)
- Gate 5: CLAUDE.md Blending ✓
- Gate 6: Deduplication ✓

**Failure Recovery**: If specific gate fails, review gate implementation and fix root cause

---

## 5. Testing Strategy

### Test Framework
Python pytest

### Test Command
```bash
cd /Users/bprzybyszi/nc-src/ctx-eng-plus
uv run pytest tools/tests/test_init_project.py -v
```

### Test Cases

**Test 1: Extraction handles nested structures** (Fix 1)
```python
def test_flatten_nested_ce_structures():
    """Test that nested .ce/ structures are flattened."""
    # Setup: Create nested structure .ce/.ce/examples/
    # Execute: Call _flatten_nested_structures()
    # Verify: No .ce/.ce/ exists, examples/ at root level
```

**Test 2: Blend preserves user files** (Fix 2)
```python
def test_blend_preserves_user_memories():
    """Test that blend preserves existing user memories."""
    # Setup: 23 user memories in .serena/memories/
    # Execute: Run blend phase
    # Verify: All 23 still present, 24 framework added = 47 total
```

**Test 3: Data loss validation prevents deletion** (Fix 3)
```python
def test_data_loss_validation_fails_on_deletion():
    """Test that DataLossValidator fails if knowledge would be deleted."""
    # Setup: Create scenario where files would be deleted
    # Execute: Run blend with validation
    # Verify: Blend fails with ValueError, no actual deletion occurs
```

**Test 4: Git state consistency**
```python
def test_git_state_after_blend():
    """Test that git state is clean after blend."""
    # Setup: git repo with tracked user files
    # Execute: Run blend
    # Verify: git status shows clean (no mixed staged/untracked)
```

### Test Execution
```bash
# Run all init_project tests
uv run pytest tools/tests/test_init_project.py::test_flatten_nested_ce_structures -v
uv run pytest tools/tests/test_init_project.py::test_blend_preserves_user_memories -v
uv run pytest tools/tests/test_init_project.py::test_data_loss_validation_fails_on_deletion -v
uv run pytest tools/tests/test_init_project.py::test_git_state_after_blend -v

# Expected: All 4 tests PASS
```

---

## 6. Rollout Plan

### Phase 1: Implement Fixes (2-3 hours)
- **Day 1**: Apply Fix 1 (extraction flattening) + tests
- **Day 1**: Apply Fix 2 (blend preservation) + tests
- **Day 1**: Apply Fix 3 (DataLossValidator) + tests
- **Validation**: All unit tests pass

### Phase 2: Fresh Install Testing (20 minutes)
- Create certinia-test-iter7 from baseline
- Restore 23 project memories
- Run extract (verify no nesting)
- Run blend (verify 47 memories preserved)
- Verify git state is clean

### Phase 3: Validation Gates (10 minutes)
- Run all 6 gates on test-iter7
- Expected: All 6 PASS
- Confirm user knowledge preserved

### Phase 4: Apply to Real Project (conditional)
**IF** Iteration 7 passes (all gates PASS):
1. Apply fixes to init_project code in ctx-eng-plus
2. Re-run Iteration 6 on real certinia with fixed version
3. Restore all 23 project memories (Option A)
4. Commit certinia with 47 total memories (23 user + 24 framework)

**IF** any phase fails:
1. Analyze failure logs
2. Fix issue in init_project code
3. Retry Phase 2 on test-iter7
4. Confirm all gates pass before proceeding

---

## 7. Success Checklist

### Fix 1: Extraction
- [ ] `_flatten_nested_structures()` method implemented
- [ ] Recursive nesting detection works (any depth)
- [ ] No .ce/.ce/ directories created (test-iter7 verification)
- [ ] Unit tests pass

### Fix 2: Blend Strategy
- [ ] Output directory NOT cleared before blend (preserved)
- [ ] All 23 user memories still present after blend
- [ ] All 24 framework memories added
- [ ] Total 47 memories after blend
- [ ] No files deleted (only additions)
- [ ] User memories have type: user
- [ ] Framework memories have type: framework
- [ ] Unit tests pass

### Fix 3: Validation
- [ ] DataLossValidator class implemented
- [ ] capture_before_state() works correctly
- [ ] capture_after_state() works correctly
- [ ] validate() method fails on knowledge loss
- [ ] generate_audit_report() shows preservation
- [ ] Audit report shows 0 deletions
- [ ] Git state is clean after blend
- [ ] Unit tests pass

### Full Validation
- [ ] Gate 1: System Structure PASS
- [ ] Gate 2: Examples Migration PASS
- [ ] Gate 3: PRPs Migration PASS
- [ ] Gate 4: Memories Migration PASS (with 47 memories)
- [ ] Gate 5: CLAUDE.md Blending PASS
- [ ] Gate 6: Deduplication PASS

---

## 8. Risk Mitigation

### If Fix 1 Fails
**Symptom**: Extraction still creates .ce/.ce/ nesting

**Recovery**:
1. Check _flatten_nested_structures() for logic errors
2. Add logging to trace flattening steps
3. Test with synthetic nested structure
4. Retry extraction with debug output

### If Fix 2 Fails
**Symptom**: User memories not preserved after blend

**Recovery**:
1. Verify output_path.exists() check works
2. Check if directory is cleared elsewhere in blend phase
3. Trace memory file lifecycle with logging
4. Verify preservation logic runs at correct time

### If Fix 3 Fails
**Symptom**: DataLossValidator doesn't catch deletions

**Recovery**:
1. Improve file counting logic (_count_files)
2. Add explicit file list comparison (not just counts)
3. Verify before/after state capture is accurate
4. Add detailed logging to validate() method

### If Gates Fail
**Symptom**: One or more gates don't pass on test-iter7

**Recovery**:
1. Review gate implementation for strictness
2. Check if gate expects old state (needs update for 47 memories)
3. Fix gate logic if incorrect
4. Retry on test-iter7 with fixed gates

---

## 9. Notes for Execution

### Key Files
- `tools/ce/init_project.py` (extract method, ~lines 111-140)
- `tools/ce/blending/strategies/memories.py` (blend method, ~lines 170-190)
- `tools/ce/blender.py` (main orchestration, add validator before blend)

### Important Commands
```bash
# Setup test environment
cp -r /Users/bprzybyszi/nc-src/certinia /Users/bprzybyszi/nc-src/certinia-test-iter7

# Run extraction with Fix 1
uv run ce init-project --target /Users/bprzybyszi/nc-src/certinia-test-iter7 --phase extract

# Run blending with Fixes 2 & 3
uv run ce init-project --target /Users/bprzybyszi/nc-src/certinia-test-iter7 --phase blend

# Run validation
python tools/ce/validation/gates.py --target /Users/bprzybyszi/nc-src/certinia-test-iter7 --all-gates
```

### Do NOT
- ❌ Commit to real certinia until Iteration 7 fully passes
- ❌ Skip validation gates (all 6 must PASS)
- ❌ Ignore audit reports (must show 0 deletions)
- ❌ Apply fixes to init_project without fresh install test first

### Do
- ✅ Test on certinia-test-iter7 (fresh copy)
- ✅ Restore 23 memories before blend
- ✅ Verify 47 memories after blend
- ✅ Run all 6 gates on test-iter7
- ✅ Document any issues found during testing

---

## 10. After Iteration 7 Success

**IF all phases pass**:
1. Fixes are validated as working correctly
2. Can confidently apply to real certinia with Option A
3. Real certinia will have 47 total memories (23 user + 24 framework)
4. All 6 gates will PASS on real project

**Option A Application** (upon full success):
```bash
# Apply fixes to init_project code
# (Already implemented if all phases passed)

# Re-run Iteration 6 on real certinia with fixed version
cd /Users/bprzybyszi/nc-src
git checkout iteration-6
uv run ce init-project --target /Users/bprzybyszi/nc-src/certinia --phase all

# Restore all 23 project memories
git restore .serena/memories/

# Stage all changes
git add .

# Commit with knowledge preserved
git commit -m "Initialize certinia with CE framework + preserve all domain knowledge

- Extracted CE framework to .ce/
- Fixed nested directory structures (Fix 1)
- Preserved 23 project-specific memories (Fix 2)
- Validated with DataLossValidator (Fix 3)
- All 6-gate validation checks PASSING
- 47 total memories (23 user + 24 framework)"
```

---

**Status**: Ready for Phase 1 implementation upon user confirmation.

**Estimated Total Timeline**: ~3.5 hours (2.5-3h implementation + 20min testing + 10min validation)

**Next Action**: Begin Phase 1 implementation of all 3 fixes.
