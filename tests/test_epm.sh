#!/usr/bin/env bash
set -uo pipefail

EPM="$(cd "$(dirname "$0")/.." && pwd)/bin/epm"
PASS=0
FAIL=0

check() {
  local name="$1"
  local result="$2"
  if [[ "$result" -eq 0 ]]; then
    echo "PASS: $name"
    ((PASS++))
  else
    echo "FAIL: $name"
    ((FAIL++))
  fi
}

# 1. help -- exits 0, output contains "Usage:"
output=$("$EPM" help 2>&1)
check "help exits 0" $?
echo "$output" | grep -q "Usage:"
check "help shows Usage:" $?

# 2. No args -- exits 1, stderr contains "input_file is required"
output=$("$EPM" 2>&1)
[[ $? -ne 0 ]]; check "no args exits non-zero" $?
echo "$output" | grep -q "input_file is required"
check "no args mentions required" $?

# 3. input_file only -- parsing succeeds (uses default output_dir), but SSH fails
output=$("$EPM" input_file=/foo 2>&1)
rc=$?
[[ $rc -ne 0 ]]; check "input_file only exits non-zero (ssh unreachable)" $?
echo "$output" | grep -q "unknown argument" && failed=1 || failed=0
check "input_file only no 'unknown argument'" $failed

# 4. output_dir only -- exits 1, stderr contains "required"
output=$("$EPM" output_dir=/bar 2>&1)
[[ $? -ne 0 ]]; check "output_dir only exits non-zero" $?
echo "$output" | grep -q "required"
check "output_dir only mentions required" $?

# 5. Bare positional arg treated as input_file -- parsing succeeds, SSH fails
output=$("$EPM" /foo 2>&1)
rc=$?
[[ $rc -ne 0 ]]; check "positional input_file exits non-zero (ssh unreachable)" $?
echo "$output" | grep -q "unknown argument" && failed=1 || failed=0
check "positional input_file no 'unknown argument'" $failed

# 6. Two bare positional args -- second is unknown
output=$("$EPM" /foo /bar 2>&1)
[[ $? -ne 0 ]]; check "two positional args exits non-zero" $?
echo "$output" | grep -q "unknown argument"
check "two positional args says unknown" $?

# 7. Unknown --flag argument -- exits 1, stderr contains "unknown argument"
output=$("$EPM" --flag 2>&1)
[[ $? -ne 0 ]]; check "unknown arg '--flag' exits non-zero" $?
echo "$output" | grep -q "unknown argument"
check "unknown arg '--flag' says unknown" $?

# 9. Valid named args -- parsing succeeds (no usage/parsing error), but SSH fails
output=$("$EPM" input_file=/foo output_dir=/bar 2>&1)
rc=$?
[[ $rc -ne 0 ]]; check "valid args exits non-zero (ssh unreachable)" $?
echo "$output" | grep -q "unknown argument" && failed=1 || failed=0
check "valid args no 'unknown argument'" $failed
echo "$output" | grep -q "input_file is required" && failed=1 || failed=0
check "valid args no 'required'" $failed

# 10. Optional args with valid required args -- parsing succeeds
output=$("$EPM" input_file=/foo output_dir=/bar step_time=1.0 border_px=10 2>&1)
rc=$?
[[ $rc -ne 0 ]]; check "optional args exits non-zero (ssh unreachable)" $?
echo "$output" | grep -q "unknown argument" && failed=1 || failed=0
check "optional args no 'unknown argument'" $failed
echo "$output" | grep -q "input_file is required" && failed=1 || failed=0
check "optional args no 'required'" $failed

# 11. Positional input_file with named options -- parsing succeeds
output=$("$EPM" /foo output_dir=/bar step_time=1.0 2>&1)
rc=$?
[[ $rc -ne 0 ]]; check "positional + options exits non-zero (ssh unreachable)" $?
echo "$output" | grep -q "unknown argument" && failed=1 || failed=0
check "positional + options no 'unknown argument'" $failed

# 12. Args in any order -- parsing succeeds
output=$("$EPM" output_dir=/bar step_time=1.0 input_file=/foo 2>&1)
rc=$?
[[ $rc -ne 0 ]]; check "reordered args exits non-zero (ssh unreachable)" $?
echo "$output" | grep -q "unknown argument" && failed=1 || failed=0
check "reordered args no 'unknown argument'" $failed
echo "$output" | grep -q "input_file is required" && failed=1 || failed=0
check "reordered args no 'required'" $failed

# 13. include_text option -- parsing succeeds
output=$("$EPM" input_file=/foo include_text=false 2>&1)
rc=$?
[[ $rc -ne 0 ]]; check "include_text=false exits non-zero (ssh unreachable)" $?
echo "$output" | grep -q "unknown argument" && failed=1 || failed=0
check "include_text=false no 'unknown argument'" $failed

output=$("$EPM" input_file=/foo include_text=true 2>&1)
rc=$?
[[ $rc -ne 0 ]]; check "include_text=true exits non-zero (ssh unreachable)" $?
echo "$output" | grep -q "unknown argument" && failed=1 || failed=0
check "include_text=true no 'unknown argument'" $failed

# 14. Default output_dir -- help text mentions /mnt/nfs/photos/reference
output=$("$EPM" help 2>&1)
echo "$output" | grep -q "/mnt/nfs/photos/reference"
check "default output_dir in help" $?

echo ""
echo "Results: $PASS passed, $FAIL failed"
exit "$FAIL"
