# Language Extensions PARTIAL-Mode Resolver Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four resolvers in `samcli/lib/cfn_language_extensions/resolvers/` that wrongly raise `InvalidTemplateException` when an argument resolves to an unresolved intrinsic dict in `ResolutionMode.PARTIAL`, restoring `sam build` for templates that use `AWS::LanguageExtensions` with parameters lacking defaults/overrides (regression in 1.160.0, GitHub issue #9004).

**Architecture:** Each resolver currently runs `parent.resolve_value(arg)` and then validates the result with `isinstance(arg, str|int|list)`, raising "layout is incorrect" if validation fails. In `PARTIAL` mode, an unresolved `Ref` legitimately comes back as a single-key dict (e.g. `{"Ref": "Stage"}`) — that's the contract `FnRefResolver` upholds. The fix: before raising, check if the post-resolution value is a single-key intrinsic dict via `is_intrinsic_key()` from `samcli/lib/cfn_language_extensions/utils.py:59`, and in PARTIAL mode reconstruct and return the original call with resolved sub-pieces preserved. This mirrors the working pattern already used by `fn_split.py:87-94` and `fn_length.py:71-77`.

**Tech Stack:** Python 3.x, pytest, the existing `cfn_language_extensions` package. No new dependencies.

---

## Background — Why Each Site Is Broken

Confirmed by direct repro on `develop` (commit `c406852f9`) — see `tests/unit/lib/cfn_language_extensions/` for context. All four sites reproduce with `ResolutionMode.PARTIAL` and a parameter that has no `Default` and no `parameter_values` override:

| # | File:line | Trigger that fails today |
|---|-----------|--------------------------|
| 1 | `samcli/lib/cfn_language_extensions/resolvers/fn_find_in_map.py:99-104` | `{"Fn::FindInMap": ["M", {"Ref": "Stage"}, "k"]}` |
| 2 | `samcli/lib/cfn_language_extensions/resolvers/fn_join.py:74-75, 82-83` | `{"Fn::Join": [{"Ref": "Sep"}, ["a","b"]]}` and `{"Fn::Join": [",", {"Ref": "L"}]}` |
| 3 | `samcli/lib/cfn_language_extensions/resolvers/fn_select.py:82-83` | `{"Fn::Select": [{"Ref": "Idx"}, ["a","b","c"]]}` |
| 4 | `samcli/lib/cfn_language_extensions/resolvers/fn_base64.py:68-69` | `{"Fn::Base64": {"Ref": "UserData"}}` |

For all four, the same shape applies: the resolved sub-arg is a dict with a single key like `Ref`/`Fn::*`, but the resolver has already executed `not isinstance(_, str)` and raised, never giving PARTIAL mode a chance to preserve.

## File Structure

**Files modified (production code):**
- `samcli/lib/cfn_language_extensions/resolvers/fn_find_in_map.py` — preserve in PARTIAL when any of `map_name`/`top_key`/`second_key` resolves to an unresolved intrinsic dict
- `samcli/lib/cfn_language_extensions/resolvers/fn_join.py` — preserve in PARTIAL when delimiter or list resolves to an unresolved intrinsic dict
- `samcli/lib/cfn_language_extensions/resolvers/fn_select.py` — preserve in PARTIAL when index resolves to an unresolved intrinsic dict (source-list path is already correct, lines 92-99)
- `samcli/lib/cfn_language_extensions/resolvers/fn_base64.py` — preserve in PARTIAL when arg resolves to an unresolved intrinsic dict

**Files modified (tests):**
- `tests/unit/lib/cfn_language_extensions/test_fn_find_in_map.py` — add PARTIAL-mode tests
- `tests/unit/lib/cfn_language_extensions/test_fn_join.py` — add PARTIAL-mode tests
- `tests/unit/lib/cfn_language_extensions/test_fn_select.py` — add PARTIAL-mode tests
- `tests/unit/lib/cfn_language_extensions/test_fn_base64.py` — add PARTIAL-mode tests

**No new files.** All fixes follow patterns already present in `fn_split.py` and `fn_length.py`.

## Conventions Used Throughout the Plan

Each resolver fix uses this helper check (already defined at `samcli/lib/cfn_language_extensions/utils.py:59`):

```python
from samcli.lib.cfn_language_extensions.utils import is_intrinsic_key

def _is_unresolved_intrinsic(value: Any) -> bool:
    """Return True if value is a single-key dict whose key is Fn::* or Ref/Condition."""
    return (
        isinstance(value, dict)
        and len(value) == 1
        and is_intrinsic_key(next(iter(value.keys())))
    )
```

We won't centralize this helper in `utils.py` — duplicating the 3-line check inline keeps each resolver self-contained, and the existing `fn_split.py:87-94` precedent does it inline. We'll add the import and the inline check per file.

For all production code edits, also add this import line near the top of the file (alongside the existing `from ... import IntrinsicFunctionResolver`):

```python
from samcli.lib.cfn_language_extensions.models import ResolutionMode
from samcli.lib.cfn_language_extensions.utils import is_intrinsic_key
```

(`fn_split.py` already has the `is_intrinsic_key` import; `fn_ref.py` already has the `ResolutionMode` lazy import inside `resolve()`. We do top-level imports because they're cleaner; the circular-import worry that prompted the lazy import in `fn_ref.py` doesn't apply here because `models.py` and `utils.py` don't import from `resolvers/`.)

For all test edits, the new tests reuse the existing `TestFn<Name>ResolverPartialMode` class in each test file, adding new methods.

---

## Task 1: Fix Fn::FindInMap PARTIAL preservation (issue #9004 root cause)

**Files:**
- Modify: `samcli/lib/cfn_language_extensions/resolvers/fn_find_in_map.py:99-104`
- Test: `tests/unit/lib/cfn_language_extensions/test_fn_find_in_map.py` (append to existing test classes)

- [ ] **Step 1: Write the failing test**

Open `tests/unit/lib/cfn_language_extensions/test_fn_find_in_map.py`. Find the bottom of the file. Append a new test class. The imports `pytest`, `TemplateProcessingContext`, `ResolutionMode`, `ParsedTemplate`, `IntrinsicResolver`, `FnFindInMapResolver`, `InvalidTemplateException` are already present at the top of the file (verify by reading lines 28-41). Also add to the imports near the top of the file:

```python
from samcli.lib.cfn_language_extensions.resolvers.fn_ref import FnRefResolver
```

(Verify it's not already there before adding.)

Append at the end of the file:

```python
class TestFnFindInMapResolverPartialMode:
    """Tests for FnFindInMapResolver in PARTIAL resolution mode (issue #9004)."""

    @pytest.fixture
    def partial_context(self) -> TemplateProcessingContext:
        parsed = ParsedTemplate(
            parameters={"Stage": {"Type": "String"}},
            mappings={"M": {"dev": {"k": "v"}}},
        )
        return TemplateProcessingContext(
            fragment={"Resources": {}},
            resolution_mode=ResolutionMode.PARTIAL,
            parsed_template=parsed,
        )

    @pytest.fixture
    def orchestrator(self, partial_context: TemplateProcessingContext) -> IntrinsicResolver:
        orchestrator = IntrinsicResolver(partial_context)
        orchestrator.register_resolver(FnRefResolver)
        orchestrator.register_resolver(FnFindInMapResolver)
        return orchestrator

    def test_unresolved_top_key_is_preserved_in_partial_mode(self, orchestrator: IntrinsicResolver):
        """Issue #9004: top-level key is Ref to a parameter without default/override."""
        value = {"Fn::FindInMap": ["M", {"Ref": "Stage"}, "k"]}
        result = orchestrator.resolve_value(value)
        assert result == {"Fn::FindInMap": ["M", {"Ref": "Stage"}, "k"]}

    def test_unresolved_map_name_is_preserved_in_partial_mode(self, orchestrator: IntrinsicResolver):
        value = {"Fn::FindInMap": [{"Ref": "Stage"}, "dev", "k"]}
        result = orchestrator.resolve_value(value)
        assert result == {"Fn::FindInMap": [{"Ref": "Stage"}, "dev", "k"]}

    def test_unresolved_second_key_is_preserved_in_partial_mode(self, orchestrator: IntrinsicResolver):
        value = {"Fn::FindInMap": ["M", "dev", {"Ref": "Stage"}]}
        result = orchestrator.resolve_value(value)
        assert result == {"Fn::FindInMap": ["M", "dev", {"Ref": "Stage"}]}

    def test_unresolved_key_with_default_value_is_preserved_in_partial_mode(self, orchestrator: IntrinsicResolver):
        """When DefaultValue is present, preserve the entire call including the options dict."""
        value = {"Fn::FindInMap": ["M", {"Ref": "Stage"}, "k", {"DefaultValue": "fallback"}]}
        result = orchestrator.resolve_value(value)
        assert result == {"Fn::FindInMap": ["M", {"Ref": "Stage"}, "k", {"DefaultValue": "fallback"}]}

    def test_resolved_keys_still_perform_lookup_in_partial_mode(self, orchestrator: IntrinsicResolver):
        """Sanity: when keys do resolve, lookup still works in PARTIAL mode."""
        value = {"Fn::FindInMap": ["M", "dev", "k"]}
        result = orchestrator.resolve_value(value)
        assert result == "v"

    def test_unresolved_top_key_still_raises_in_full_mode(self):
        """In FULL mode, an unresolvable Ref raises (regression-guard for the FULL path)."""
        from samcli.lib.cfn_language_extensions.exceptions import UnresolvableReferenceError
        parsed = ParsedTemplate(mappings={"M": {"dev": {"k": "v"}}})
        ctx = TemplateProcessingContext(
            fragment={"Resources": {}},
            resolution_mode=ResolutionMode.FULL,
            parsed_template=parsed,
        )
        orch = IntrinsicResolver(ctx)
        orch.register_resolver(FnRefResolver)
        orch.register_resolver(FnFindInMapResolver)
        with pytest.raises((InvalidTemplateException, UnresolvableReferenceError)):
            orch.resolve_value({"Fn::FindInMap": ["M", {"Ref": "Missing"}, "k"]})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/lib/cfn_language_extensions/test_fn_find_in_map.py::TestFnFindInMapResolverPartialMode -v`

Expected: 5 of the 6 tests FAIL with `InvalidTemplateException: Fn::FindInMap layout is incorrect`. The `test_resolved_keys_still_perform_lookup_in_partial_mode` may PASS (it doesn't exercise the bug). The FULL-mode test PASSES.

- [ ] **Step 3: Implement the fix**

Edit `samcli/lib/cfn_language_extensions/resolvers/fn_find_in_map.py`:

(a) Update imports near the top (currently lines 12-15):

```python
from typing import Any, Dict

from samcli.lib.cfn_language_extensions.exceptions import InvalidTemplateException
from samcli.lib.cfn_language_extensions.models import ResolutionMode
from samcli.lib.cfn_language_extensions.resolvers.base import IntrinsicFunctionResolver
from samcli.lib.cfn_language_extensions.utils import is_intrinsic_key
```

(b) Replace lines 98-104 (the three `if not isinstance(... str)` checks) with:

```python
        # In PARTIAL mode, any key that didn't resolve down to a string is a
        # legitimately deferred reference (e.g. a Ref to a parameter without a
        # default value and no override). Preserve the call so CloudFormation
        # can resolve it at deploy time. See GitHub issue #9004.
        unresolved = [
            k for k in (map_name, top_key, second_key)
            if not isinstance(k, str)
        ]
        if unresolved:
            if self.context.resolution_mode == ResolutionMode.PARTIAL and all(
                isinstance(k, str) or _is_unresolved_intrinsic(k) for k in (map_name, top_key, second_key)
            ):
                preserved = [map_name, top_key, second_key]
                if len(args) >= self._ARGS_WITH_DEFAULT:
                    preserved.append(args[3])
                return {"Fn::FindInMap": preserved}
            raise InvalidTemplateException("Fn::FindInMap layout is incorrect")
```

(c) Add a module-level helper at the bottom of `fn_find_in_map.py` (after the class definition):

```python
def _is_unresolved_intrinsic(value: Any) -> bool:
    """Return True if value is a single-key dict whose key is an intrinsic function name."""
    return (
        isinstance(value, dict)
        and len(value) == 1
        and is_intrinsic_key(next(iter(value.keys())))
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/lib/cfn_language_extensions/test_fn_find_in_map.py -v`

Expected: ALL tests PASS, including the new partial-mode class and the previously-existing tests (no regressions).

- [ ] **Step 5: Commit**

```bash
git add samcli/lib/cfn_language_extensions/resolvers/fn_find_in_map.py tests/unit/lib/cfn_language_extensions/test_fn_find_in_map.py
git commit -m "fix: preserve Fn::FindInMap with unresolved Ref keys in PARTIAL mode (#9004)"
```

---

## Task 2: Fix Fn::Join PARTIAL preservation

**Files:**
- Modify: `samcli/lib/cfn_language_extensions/resolvers/fn_join.py:69-83`
- Test: `tests/unit/lib/cfn_language_extensions/test_fn_join.py` (extend `TestFnJoinResolverPartialMode` class at line 375)

- [ ] **Step 1: Write the failing tests**

Open `tests/unit/lib/cfn_language_extensions/test_fn_join.py`. The class `TestFnJoinResolverPartialMode` already exists at line 375. The orchestrator fixture there only registers `FnJoinResolver` — we need a new fixture that also registers `FnRefResolver` and a `parsed_template` with a parameter declaration (so `FnRefResolver` recognizes it as a parameter that didn't get a value, and preserves the Ref).

Append two new methods to `TestFnJoinResolverPartialMode` (just before the next class at line 414). They construct their own context/orchestrator inline to avoid tampering with the shared fixture:

```python
    def test_unresolved_delimiter_is_preserved_in_partial_mode(self):
        from samcli.lib.cfn_language_extensions.models import ParsedTemplate
        ctx = TemplateProcessingContext(
            fragment={"Resources": {}},
            resolution_mode=ResolutionMode.PARTIAL,
            parsed_template=ParsedTemplate(parameters={"Sep": {"Type": "String"}}),
        )
        orch = IntrinsicResolver(ctx)
        orch.register_resolver(FnRefResolver)
        orch.register_resolver(FnJoinResolver)

        value = {"Fn::Join": [{"Ref": "Sep"}, ["a", "b"]]}
        result = orch.resolve_value(value)
        assert result == {"Fn::Join": [{"Ref": "Sep"}, ["a", "b"]]}

    def test_unresolved_list_is_preserved_in_partial_mode(self):
        from samcli.lib.cfn_language_extensions.models import ParsedTemplate
        ctx = TemplateProcessingContext(
            fragment={"Resources": {}},
            resolution_mode=ResolutionMode.PARTIAL,
            parsed_template=ParsedTemplate(parameters={"L": {"Type": "CommaDelimitedList"}}),
        )
        orch = IntrinsicResolver(ctx)
        orch.register_resolver(FnRefResolver)
        orch.register_resolver(FnJoinResolver)

        value = {"Fn::Join": [",", {"Ref": "L"}]}
        result = orch.resolve_value(value)
        assert result == {"Fn::Join": [",", {"Ref": "L"}]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/lib/cfn_language_extensions/test_fn_join.py::TestFnJoinResolverPartialMode -v`

Expected: 2 new tests FAIL with `InvalidTemplateException: Fn::Join layout is incorrect`. Existing tests in the class still PASS.

- [ ] **Step 3: Implement the fix**

Edit `samcli/lib/cfn_language_extensions/resolvers/fn_join.py`:

(a) Update imports near the top (currently lines 10-13):

```python
from typing import Any, Dict

from samcli.lib.cfn_language_extensions.exceptions import InvalidTemplateException
from samcli.lib.cfn_language_extensions.models import ResolutionMode
from samcli.lib.cfn_language_extensions.resolvers.base import IntrinsicFunctionResolver
from samcli.lib.cfn_language_extensions.utils import is_intrinsic_key
```

(b) Replace the body of `resolve()` from line 66 (`delimiter = args[0]`) through line 83 (the `raise` after the list-type check) with:

```python
        delimiter = args[0]
        list_to_join = args[1]

        # Resolve any nested intrinsic functions in the delimiter
        if self.parent is not None:
            delimiter = self.parent.resolve_value(delimiter)

        # Resolve any nested intrinsic functions in the list
        if self.parent is not None:
            list_to_join = self.parent.resolve_value(list_to_join)

        # In PARTIAL mode, preserve the call when either argument is still an
        # unresolved intrinsic (e.g. a Ref to a parameter without a default/override).
        delim_is_unresolved = _is_unresolved_intrinsic(delimiter)
        list_is_unresolved = _is_unresolved_intrinsic(list_to_join)
        if delim_is_unresolved or list_is_unresolved:
            if self.context.resolution_mode == ResolutionMode.PARTIAL:
                return {"Fn::Join": [delimiter, list_to_join]}
            raise InvalidTemplateException("Fn::Join layout is incorrect")

        # Validate delimiter is a string
        if not isinstance(delimiter, str):
            raise InvalidTemplateException("Fn::Join layout is incorrect")

        # Validate the list
        if not isinstance(list_to_join, list):
            raise InvalidTemplateException("Fn::Join layout is incorrect")
```

(c) Add a module-level helper at the bottom of `fn_join.py` (after the class definition):

```python
def _is_unresolved_intrinsic(value: Any) -> bool:
    """Return True if value is a single-key dict whose key is an intrinsic function name."""
    return (
        isinstance(value, dict)
        and len(value) == 1
        and is_intrinsic_key(next(iter(value.keys())))
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/lib/cfn_language_extensions/test_fn_join.py -v`

Expected: ALL tests PASS, including the two new ones and all previously-existing tests.

- [ ] **Step 5: Commit**

```bash
git add samcli/lib/cfn_language_extensions/resolvers/fn_join.py tests/unit/lib/cfn_language_extensions/test_fn_join.py
git commit -m "fix: preserve Fn::Join with unresolved Ref args in PARTIAL mode"
```

---

## Task 3: Fix Fn::Select PARTIAL preservation (index path)

**Files:**
- Modify: `samcli/lib/cfn_language_extensions/resolvers/fn_select.py:73-83`
- Test: `tests/unit/lib/cfn_language_extensions/test_fn_select.py` (extend `TestFnSelectResolverPartialMode` class at line 482)

The source-list path (`fn_select.py:92-99`) is already correct. We only need to fix the index path.

- [ ] **Step 1: Write the failing test**

Open `tests/unit/lib/cfn_language_extensions/test_fn_select.py`. The class `TestFnSelectResolverPartialMode` exists at line 482. Append a new test method to it:

```python
    def test_unresolved_index_is_preserved_in_partial_mode(self):
        from samcli.lib.cfn_language_extensions.models import ParsedTemplate
        ctx = TemplateProcessingContext(
            fragment={"Resources": {}},
            resolution_mode=ResolutionMode.PARTIAL,
            parsed_template=ParsedTemplate(parameters={"Idx": {"Type": "Number"}}),
        )
        orch = IntrinsicResolver(ctx)
        orch.register_resolver(FnRefResolver)
        orch.register_resolver(FnSelectResolver)

        value = {"Fn::Select": [{"Ref": "Idx"}, ["a", "b", "c"]]}
        result = orch.resolve_value(value)
        assert result == {"Fn::Select": [{"Ref": "Idx"}, ["a", "b", "c"]]}
```

`FnRefResolver` is already imported at line 29 of the test file. Verify before adding any imports.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/lib/cfn_language_extensions/test_fn_select.py::TestFnSelectResolverPartialMode::test_unresolved_index_is_preserved_in_partial_mode -v`

Expected: FAIL with `InvalidTemplateException: Fn::Select layout is incorrect`.

- [ ] **Step 3: Implement the fix**

Edit `samcli/lib/cfn_language_extensions/resolvers/fn_select.py`:

(a) Update imports near the top (currently lines 10-13):

```python
from typing import Any, Dict

from samcli.lib.cfn_language_extensions.exceptions import InvalidTemplateException
from samcli.lib.cfn_language_extensions.models import ResolutionMode
from samcli.lib.cfn_language_extensions.resolvers.base import IntrinsicFunctionResolver
from samcli.lib.cfn_language_extensions.utils import is_intrinsic_key
```

(b) Replace lines 73-83 (the index-resolution and validation block) with:

```python
        # Resolve any nested intrinsic functions in the index
        if self.parent is not None:
            index = self.parent.resolve_value(index)

        # In PARTIAL mode, if the index is still an unresolved intrinsic,
        # preserve the call. We must still resolve the source list below in
        # case it contains resolvable intrinsics — that way, partial expansion
        # makes maximal progress.
        if _is_unresolved_intrinsic(index):
            if self.context.resolution_mode != ResolutionMode.PARTIAL:
                raise InvalidTemplateException("Fn::Select layout is incorrect")
            if self.parent is not None:
                source_list = self.parent.resolve_value(source_list)
            return {"Fn::Select": [index, source_list]}

        # Validate index is an integer (or can be converted to one)
        if isinstance(index, str):
            try:
                index = int(index)
            except ValueError:
                raise InvalidTemplateException("Fn::Select layout is incorrect")
        elif not isinstance(index, int):
            raise InvalidTemplateException("Fn::Select layout is incorrect")
```

(c) Add a module-level helper at the bottom of `fn_select.py` (after the class definition):

```python
def _is_unresolved_intrinsic(value: Any) -> bool:
    """Return True if value is a single-key dict whose key is an intrinsic function name."""
    return (
        isinstance(value, dict)
        and len(value) == 1
        and is_intrinsic_key(next(iter(value.keys())))
    )
```

Note: `bool` is a subclass of `int` in Python, so `isinstance(True, int)` is True. This is the existing behavior at line 82 and we preserve it. `_is_unresolved_intrinsic` correctly returns False for booleans (they aren't dicts), so it doesn't interfere.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/lib/cfn_language_extensions/test_fn_select.py -v`

Expected: ALL tests PASS, including the new one and all previously-existing tests.

- [ ] **Step 5: Commit**

```bash
git add samcli/lib/cfn_language_extensions/resolvers/fn_select.py tests/unit/lib/cfn_language_extensions/test_fn_select.py
git commit -m "fix: preserve Fn::Select with unresolved Ref index in PARTIAL mode"
```

---

## Task 4: Fix Fn::Base64 PARTIAL preservation

**Files:**
- Modify: `samcli/lib/cfn_language_extensions/resolvers/fn_base64.py:60-69`
- Test: `tests/unit/lib/cfn_language_extensions/test_fn_base64.py` (extend `TestFnBase64ResolverPartialMode` class at line 441)

- [ ] **Step 1: Write the failing test**

Open `tests/unit/lib/cfn_language_extensions/test_fn_base64.py`. The class `TestFnBase64ResolverPartialMode` exists at line 441. Verify whether `FnRefResolver` is imported at the top of the file. If not, add:

```python
from samcli.lib.cfn_language_extensions.resolvers.fn_ref import FnRefResolver
```

Append a new test method to `TestFnBase64ResolverPartialMode`:

```python
    def test_unresolved_arg_is_preserved_in_partial_mode(self):
        from samcli.lib.cfn_language_extensions.models import ParsedTemplate
        ctx = TemplateProcessingContext(
            fragment={"Resources": {}},
            resolution_mode=ResolutionMode.PARTIAL,
            parsed_template=ParsedTemplate(parameters={"UserData": {"Type": "String"}}),
        )
        orch = IntrinsicResolver(ctx)
        orch.register_resolver(FnRefResolver)
        orch.register_resolver(FnBase64Resolver)

        value = {"Fn::Base64": {"Ref": "UserData"}}
        result = orch.resolve_value(value)
        assert result == {"Fn::Base64": {"Ref": "UserData"}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/lib/cfn_language_extensions/test_fn_base64.py::TestFnBase64ResolverPartialMode::test_unresolved_arg_is_preserved_in_partial_mode -v`

Expected: FAIL with `InvalidTemplateException: Fn::Base64 layout is incorrect`.

- [ ] **Step 3: Implement the fix**

Edit `samcli/lib/cfn_language_extensions/resolvers/fn_base64.py`:

(a) Update imports near the top (currently lines 8-12):

```python
import base64
from typing import Any, Dict

from samcli.lib.cfn_language_extensions.exceptions import InvalidTemplateException
from samcli.lib.cfn_language_extensions.models import ResolutionMode
from samcli.lib.cfn_language_extensions.resolvers.base import IntrinsicFunctionResolver
from samcli.lib.cfn_language_extensions.utils import is_intrinsic_key
```

(b) Replace lines 67-69 (the `isinstance(resolved_args, str)` check) with:

```python
        # In PARTIAL mode, if the argument is still an unresolved intrinsic
        # (e.g. a Ref to a parameter without a default/override), preserve the
        # call so CloudFormation can resolve it at deploy time.
        if _is_unresolved_intrinsic(resolved_args):
            if self.context.resolution_mode == ResolutionMode.PARTIAL:
                return {"Fn::Base64": resolved_args}
            raise InvalidTemplateException("Fn::Base64 layout is incorrect")

        # Validate that the resolved value is a string
        if not isinstance(resolved_args, str):
            raise InvalidTemplateException("Fn::Base64 layout is incorrect")
```

Note: the function's return type is `str` but in PARTIAL mode we return a dict. Update the return annotation to be consistent. Change line 35 from:

```python
    def resolve(self, value: Dict[str, Any]) -> str:
```

to:

```python
    def resolve(self, value: Dict[str, Any]) -> Any:
```

(matching the pattern in `fn_find_in_map.py:50` and `fn_select.py:41` which return `Any`).

(c) Add a module-level helper at the bottom of `fn_base64.py` (after the class definition):

```python
def _is_unresolved_intrinsic(value: Any) -> bool:
    """Return True if value is a single-key dict whose key is an intrinsic function name."""
    return (
        isinstance(value, dict)
        and len(value) == 1
        and is_intrinsic_key(next(iter(value.keys())))
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/lib/cfn_language_extensions/test_fn_base64.py -v`

Expected: ALL tests PASS, including the new one and all previously-existing tests.

- [ ] **Step 5: Commit**

```bash
git add samcli/lib/cfn_language_extensions/resolvers/fn_base64.py tests/unit/lib/cfn_language_extensions/test_fn_base64.py
git commit -m "fix: preserve Fn::Base64 with unresolved Ref arg in PARTIAL mode"
```

---

## Task 5: End-to-end regression test mirroring issue #9004

**Files:**
- Test: `tests/unit/lib/cfn_language_extensions/test_fn_find_in_map.py` (add a new class at the end)

Reproduces the user's exact scenario from GitHub issue #9004: a template with `Transform: AWS::LanguageExtensions`, a parameter without a `Default`, and `Fn::FindInMap` keyed off `!Ref` to that parameter — driven through the full pipeline (not just the resolver in isolation).

- [ ] **Step 1: Write the failing test**

Append to the end of `tests/unit/lib/cfn_language_extensions/test_fn_find_in_map.py`:

```python
class TestFnFindInMapIssue9004Regression:
    """End-to-end regression test for GitHub issue #9004.

    Repro: a template with AWS::LanguageExtensions transform, a parameter that
    has no Default and no override, and Fn::FindInMap using !Ref to that
    parameter as a key. Before the fix, this raised "Fn::FindInMap layout is
    incorrect" during sam build. After the fix, the call is preserved verbatim
    in PARTIAL mode and CloudFormation resolves it at deploy time.
    """

    def test_template_with_unresolved_ref_in_findinmap_processes_in_partial_mode(self):
        from samcli.lib.cfn_language_extensions.api import process_template

        template = {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Transform": "AWS::LanguageExtensions",
            "Parameters": {
                "Stage": {"Type": "String"},
            },
            "Mappings": {
                "EnvConfig": {
                    "dev": {"BucketName": "dev-bucket"},
                    "prod": {"BucketName": "prod-bucket"},
                },
            },
            "Resources": {
                "MyBucket": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {
                        "BucketName": {
                            "Fn::FindInMap": ["EnvConfig", {"Ref": "Stage"}, "BucketName"]
                        }
                    },
                },
            },
        }

        # In PARTIAL mode (sam build's mode), processing must not raise.
        result = process_template(template, resolution_mode=ResolutionMode.PARTIAL)

        # The Fn::FindInMap call is preserved unchanged for CloudFormation.
        bucket_name = result["Resources"]["MyBucket"]["Properties"]["BucketName"]
        assert bucket_name == {
            "Fn::FindInMap": ["EnvConfig", {"Ref": "Stage"}, "BucketName"]
        }
```

Note: the import path `samcli.lib.cfn_language_extensions.api.process_template` should match how the package exposes its top-level entry. If the function is named differently (e.g. `process` or `transform_template`), inspect `samcli/lib/cfn_language_extensions/api.py` and adapt the import. The name `process_template` is inferred from `api.py:682` (`process_template(... resolution_mode: ResolutionMode = ResolutionMode.PARTIAL ...)`). If the signature uses a different second-positional argument, adapt accordingly — pass `resolution_mode` as a keyword.

- [ ] **Step 2: Run the test**

Run: `pytest tests/unit/lib/cfn_language_extensions/test_fn_find_in_map.py::TestFnFindInMapIssue9004Regression -v`

Expected (after Tasks 1-4 are merged): PASS. If it fails because of an API name mismatch, fix the import to use the correct entry point and rerun. Do not modify the production code in this task.

- [ ] **Step 3: Run the full language-extensions unit-test suite**

Run: `pytest tests/unit/lib/cfn_language_extensions/ -v`

Expected: ALL tests PASS — both the pre-existing tests and the new ones from Tasks 1-5.

- [ ] **Step 4: Run linters/formatters used by the project**

Run (in this order, only if these are configured for the repo — check `pyproject.toml` / `Makefile` first):

```bash
make lint || ruff check samcli/lib/cfn_language_extensions tests/unit/lib/cfn_language_extensions
make format-check || black --check samcli/lib/cfn_language_extensions tests/unit/lib/cfn_language_extensions
```

If `make lint` exists in the repo, prefer that. If neither command exists, skip this step and note it in the commit. Expected: clean, no errors. If formatting fails, run `make format` or `black samcli/lib/cfn_language_extensions tests/unit/lib/cfn_language_extensions` and commit the formatting changes separately.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/lib/cfn_language_extensions/test_fn_find_in_map.py
git commit -m "test: end-to-end regression test for issue #9004"
```

---

## Task 6: Verify fix manually against the original repro

**Files:** None (verification only).

- [ ] **Step 1: Run the inline repro script**

This is the same script that confirmed the bug originally. After Tasks 1-4, all four lines should now print `OK ...` with the preserved-call dict.

```bash
python3 -c "
from samcli.lib.cfn_language_extensions.models import TemplateProcessingContext, ResolutionMode, ParsedTemplate
from samcli.lib.cfn_language_extensions.resolvers.base import IntrinsicResolver
from samcli.lib.cfn_language_extensions.resolvers.fn_ref import FnRefResolver
from samcli.lib.cfn_language_extensions.resolvers.fn_find_in_map import FnFindInMapResolver
from samcli.lib.cfn_language_extensions.resolvers.fn_join import FnJoinResolver
from samcli.lib.cfn_language_extensions.resolvers.fn_select import FnSelectResolver
from samcli.lib.cfn_language_extensions.resolvers.fn_base64 import FnBase64Resolver

parsed = ParsedTemplate(
    parameters={'Stage': {'Type': 'String'}},
    mappings={'M': {'dev': {'k': 'v'}}},
)
ctx = TemplateProcessingContext(
    fragment={'Resources': {}},
    resolution_mode=ResolutionMode.PARTIAL,
    parsed_template=parsed,
)
o = IntrinsicResolver(ctx)
for cls in (FnRefResolver, FnFindInMapResolver, FnJoinResolver, FnSelectResolver, FnBase64Resolver):
    o.register_resolver(cls)

cases = [
    ('FindInMap[Ref top key]', {'Fn::FindInMap': ['M', {'Ref': 'Stage'}, 'k']}),
    ('Join[Ref delimiter]',    {'Fn::Join': [{'Ref': 'Stage'}, ['a', 'b']]}),
    ('Join[Ref list]',         {'Fn::Join': [',', {'Ref': 'Stage'}]}),
    ('Select[Ref index]',      {'Fn::Select': [{'Ref': 'Stage'}, ['a', 'b', 'c']]}),
    ('Base64[Ref]',            {'Fn::Base64': {'Ref': 'Stage'}}),
]
for label, value in cases:
    try:
        r = o.resolve_value(value)
        print(f'OK   {label}: {r!r}')
    except Exception as e:
        print(f'FAIL {label}: {type(e).__name__}: {e}')
"
```

Expected output: 5 lines starting with `OK   `. No `FAIL` lines.

If any FAIL appears, the corresponding task's fix is incorrect — return to that task and debug.

- [ ] **Step 2: No commit needed for this task** (verification only)

---

## Self-Review

**Spec coverage check:**

| Issue site | Task # | Test added | Production fix | Commit |
|------------|--------|------------|----------------|--------|
| `fn_find_in_map.py:99-104` | Task 1 | ✓ | ✓ | ✓ |
| `fn_join.py:74-75 + 82-83` | Task 2 | ✓ (×2) | ✓ | ✓ |
| `fn_select.py:82-83` | Task 3 | ✓ | ✓ | ✓ |
| `fn_base64.py:68-69` | Task 4 | ✓ | ✓ | ✓ |
| End-to-end #9004 repro | Task 5 | ✓ | n/a (uses Task 1 fix) | ✓ |
| Manual verification | Task 6 | n/a | n/a | n/a |

All four high-severity sites identified in the audit have a dedicated TDD task. The user-reported scenario from #9004 has an end-to-end test in Task 5. Manual verification in Task 6 mirrors the reproducer used to confirm the bug.

**Placeholder scan:** no "TBD"/"implement later"/"add appropriate"/"similar to". One conditional in Task 5 step 1 ("if function is named differently … adapt") — that's a deliberate fallback because I haven't read `api.py` to verify the exact public symbol name. Not a placeholder for the fix itself, just a defensive note for the test import.

**Type consistency:**
- Helper `_is_unresolved_intrinsic(value: Any) -> bool` — same signature in all four files. Each file gets its own copy (intentional — see "Conventions Used" section above).
- `ResolutionMode.PARTIAL` and `is_intrinsic_key` imported consistently in all four resolvers.
- `Fn::Base64` return type annotation widened from `str` to `Any` (Task 4 step 3), matching `fn_find_in_map.py` and `fn_select.py`. No callers depend on the return type being narrowed to `str` — verified by the audit (no resolver expects `Fn::Base64` to be a string post-resolve in PARTIAL mode).

**Test fixture parameters:**
- `Stage`/`Sep`/`Idx`/`UserData`/`L` — declared with `parsed_template=ParsedTemplate(parameters={...})` in every PARTIAL test so `FnRefResolver` recognizes them as parameters without values (path: `fn_ref.py:104-114`, falling through to the `_is_resource_ref` check at `base.py:436-440` which returns False for declared parameters; then `fn_ref.py:88-114` returns None; then `fn_ref.py:76-86` returns the original `{"Ref": ...}` dict). This is the exact mechanism the bug exercises.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-14-language-extensions-partial-mode-fixes.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
