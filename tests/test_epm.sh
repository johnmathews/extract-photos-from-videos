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

# 5. Unknown positional argument -- exits 1, stderr contains "unknown argument"
output=$("$EPM" bogus 2>&1)
[[ $? -ne 0 ]]; check "unknown arg 'bogus' exits non-zero" $?
echo "$output" | grep -q "unknown argument"
check "unknown arg 'bogus' says unknown" $?

# 6. Unknown --flag argument -- exits 1, stderr contains "unknown argument"
output=$("$EPM" --flag 2>&1)
[[ $? -ne 0 ]]; check "unknown arg '--flag' exits non-zero" $?
echo "$output" | grep -q "unknown argument"
check "unknown arg '--flag' says unknown" $?

# 7. Valid required args -- parsing succeeds (no usage/parsing error), but SSH fails
output=$("$EPM" input_file=/foo output_dir=/bar 2>&1)
rc=$?
[[ $rc -ne 0 ]]; check "valid args exits non-zero (ssh unreachable)" $?
echo "$output" | grep -q "unknown argument" && failed=1 || failed=0
check "valid args no 'unknown argument'" $failed
echo "$output" | grep -q "input_file is required" && failed=1 || failed=0
check "valid args no 'required'" $failed

# 8. Optional args with valid required args -- parsing succeeds
output=$("$EPM" input_file=/foo output_dir=/bar step_time=1.0 ssim_threshold=0.95 2>&1)
rc=$?
[[ $rc -ne 0 ]]; check "optional args exits non-zero (ssh unreachable)" $?
echo "$output" | grep -q "unknown argument" && failed=1 || failed=0
check "optional args no 'unknown argument'" $failed
echo "$output" | grep -q "input_file is required" && failed=1 || failed=0
check "optional args no 'required'" $failed

# 9. Args in any order -- parsing succeeds
output=$("$EPM" output_dir=/bar step_time=1.0 input_file=/foo 2>&1)
rc=$?
[[ $rc -ne 0 ]]; check "reordered args exits non-zero (ssh unreachable)" $?
echo "$output" | grep -q "unknown argument" && failed=1 || failed=0
check "reordered args no 'unknown argument'" $failed
echo "$output" | grep -q "input_file is required" && failed=1 || failed=0
check "reordered args no 'required'" $failed

# 10. Default output_dir -- uses /mnt/nfs/photos/reference
output=$("$EPM" input_file=/foo 2>&1)
echo "$output" | grep -q "/mnt/nfs/photos/reference"
check "default output_dir shown" $?

echo ""
echo "Results: $PASS passed, $FAIL failed"
exit "$FAIL"
