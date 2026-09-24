#!/usr/bin/env bash
# =============================================================================
# run_tests.sh — CI runner for the uPC1237_SSR speaker-protection project.
#
# What it does
#   * finds every tests/*.cir and runs it in batch mode with ngspice-45:
#         nix shell nixpkgs#ngspice -c ngspice -b <file>
#   * parses the `.meas` scalars printed by ngspice ("name = 1.234e-05")
#   * evaluates tests/criteria.tsv (test ; metric ; operator ; threshold)
#   * prints a per-criterion PASS/FAIL table
#   * writes tests/results.json (machine-readable, always)
#   * exits non-zero if any test FAILs, or if the suite cannot be verified
#
# Exit codes
#   0  all tests PASS (or --check: all checks OK)
#   1  at least one test FAIL / check FAIL
#   2  usage or configuration error (bad criteria.tsv, missing tool)
#   3  prerequisites missing (no tests, unreferenced/absent master netlist)
#
# Options
#   --check            run static checks only, do not simulate anything
#   --json             emit the results JSON on stdout (human output -> stderr)
#   --no-wait          do not wait for the master netlist to appear
#   --wait SECONDS     max time to wait for tests/master netlist (default 600)
#   --only NAME        run only the test whose basename matches glob NAME
#   --report           also write CI_REPORT.md next to the project root
#   --verbose          echo each ngspice command before running it
#   -h | --help        this help
#
# Environment overrides: ROOT, TESTS_DIR, CRITERIA, RESULTS, LOG_DIR, MASTER,
#                        WAIT_SECONDS, POLL_SECONDS, NGSPICE_TIMEOUT.
#
# The script only READS tests/*.cir and uPC1237_SSR.cir. It writes results.json,
# ci_logs/*.log and (with --report) CI_REPORT.md.
# =============================================================================
set -u -o pipefail
export LC_ALL=C

SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd -- "$(dirname -- "$SCRIPT_PATH")" >/dev/null 2>&1 && pwd -P)"
ROOT="${ROOT:-$SCRIPT_DIR}"
TESTS_DIR="${TESTS_DIR:-$ROOT/tests}"
CRITERIA="${CRITERIA:-$TESTS_DIR/criteria.tsv}"
RESULTS="${RESULTS:-$TESTS_DIR/results.json}"
LOG_DIR="${LOG_DIR:-$ROOT/ci_logs}"
MASTER="${MASTER:-$ROOT/uPC1237_SSR.cir}"

NGSPICE_BASE=(nix shell nixpkgs#ngspice -c ngspice)
WAIT_SECONDS="${WAIT_SECONDS:-600}"
POLL_SECONDS="${POLL_SECONDS:-30}"
NGSPICE_TIMEOUT="${NGSPICE_TIMEOUT:-180}"

CHECK_ONLY=0
JSON_OUT=0
NO_WAIT=0
VERBOSE=0
WRITE_REPORT=0
ONLY_PATTERN=""

# --- error/warning classification -------------------------------------------
# Anything matching FATAL_RE makes a test FAIL regardless of the ngspice exit
# code (ngspice-45 can return 0 after a failed .meas or a missing vector).
FATAL_RE="Error:|Fatal error|fatal error|no such vector|unimplemented|unrecognized parameter|[Cc]annot find|[Cc]ould not find|[Cc]an.t find|singular matrix|[Tt]imestep too small|doAnalyses|simulation aborted|measure[a-z]* .* failed"
WARN_RE="Warning|unrecognized parameter"
# ngspice-45 emits this for a perfectly valid `.print op v(x)`; it is recorded
# but does not fail a test.
BENIGN_RE="[Ww]arning: can.t parse"

# --- tiny IO helpers ---------------------------------------------------------
if [[ -t 2 ]]; then
  C_RED=$'\e[31m'; C_GRN=$'\e[32m'; C_YEL=$'\e[33m'; C_BLD=$'\e[1m'; C_RST=$'\e[0m'
else
  C_RED=""; C_GRN=""; C_YEL=""; C_BLD=""; C_RST=""
fi

say()  { printf '%s\n' "$*" >&2; }
info() { printf '%s\n' "$*" >&2; }
err()  { printf '%serror:%s %s\n' "$C_RED" "$C_RST" "$*" >&2; }
warn() { printf '%swarn:%s %s\n' "$C_YEL" "$C_RST" "$*" >&2; }

usage() { sed -n '2,40p' "$SCRIPT_PATH" | sed 's/^# \{0,1\}//'; }

die() { err "$*"; exit 2; }

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

is_number() {
  [[ "$1" =~ ^[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?$ ]]
}

# num_cmp VALUE OP THRESHOLD -> exit 0 pass, 1 fail, 2 error
num_cmp() {
  awk -v v="$1" -v op="$2" -v t="$3" 'BEGIN{
    a=v+0; b=t+0;
    if (op ~ /^abs/) { a=(a<0?-a:a); op=substr(op,4); }
    if      (op==">=") ok=(a>=b);
    else if (op=="<=") ok=(a<=b);
    else if (op==">")  ok=(a>b);
    else if (op=="<")  ok=(a<b);
    else if (op=="==") ok=(a==b);
    else if (op=="!=") ok=(a!=b);
    else exit 2;
    exit(ok?0:1);
  }'
}

# =============================================================================
# test discovery / waiting
# =============================================================================
TESTS=()

discover_tests() {
  TESTS=()
  local f
  shopt -s nullglob
  for f in "$TESTS_DIR"/*.cir; do
    [[ -f "$f" ]] || continue
    if [[ -n "$ONLY_PATTERN" ]]; then
      # shellcheck disable=SC2053  # glob match is intentional
      [[ "$(basename "$f" .cir)" == $ONLY_PATTERN ]] || continue
    fi
    TESTS+=("$f")
  done
  shopt -u nullglob
}

tests_reference_master() {
  ((${#TESTS[@]})) || return 1
  grep -rlF 'uPC1237_SSR.cir' --include='*.cir' "${TESTS[@]}" >/dev/null 2>&1
}

wait_for_inputs() {
  local deadline=$((SECONDS + WAIT_SECONDS)) need why
  while :; do
    discover_tests
    need=0; why=""
    if ((${#TESTS[@]} == 0)); then
      need=1; why="no tests/*.cir found"
    elif tests_reference_master && [[ ! -f "$MASTER" ]]; then
      need=1; why="tests include uPC1237_SSR.cir but it does not exist"
    fi
    ((need == 0)) && return 0
    if ((SECONDS >= deadline)); then
      warn "$why — waited ${WAIT_SECONDS}s"
      return 1
    fi
    info "waiting: $why; ${deadline}-${SECONDS}s left (poll ${POLL_SECONDS}s)"
    sleep "$POLL_SECONDS"
  done
}

# =============================================================================
# criteria
# =============================================================================
CRIT_TEST=(); CRIT_METRIC=(); CRIT_OP=(); CRIT_THR=(); CRIT_NOTE=()

parse_criteria() {
  CRIT_TEST=(); CRIT_METRIC=(); CRIT_OP=(); CRIT_THR=(); CRIT_NOTE=()
  [[ -f "$CRITERIA" ]] || { err "criteria file not found: $CRITERIA"; return 1; }
  local ln=0 line c1 c2 c3 c4 c5
  while IFS= read -r line || [[ -n "$line" ]]; do
    ln=$((ln + 1))
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    IFS=';' read -r c1 c2 c3 c4 c5 <<<"$line"
    c1="$(trim "$c1")"; c2="$(trim "$c2")"; c3="$(trim "$c3")"; c4="$(trim "$c4")"
    c5="$(trim "${c5:-}")"
    if [[ -z "$c1" || -z "$c2" || -z "$c3" || -z "$c4" ]]; then
      err "criteria line $ln: expected 4 columns (test ; metric ; operator ; threshold)"
      return 1
    fi
    case "$c3" in
      '>='|'<='|'>'|'<'|'=='|'!='|'abs>='|'abs<='|'abs>'|'abs<') ;;
      *) err "criteria line $ln: unsupported operator '$c3'"; return 1 ;;
    esac
    if ! is_number "$c4"; then
      err "criteria line $ln: threshold '$c4' is not a number"; return 1
    fi
    CRIT_TEST+=("$c1"); CRIT_METRIC+=("$c2"); CRIT_OP+=("$c3"); CRIT_THR+=("$c4"); CRIT_NOTE+=("$c5")
  done <"$CRITERIA"
  ((${#CRIT_TEST[@]} > 0)) || { err "criteria file has no rules: $CRITERIA"; return 1; }
  return 0
}

# =============================================================================
# ngspice output parsing
# =============================================================================
declare -A MEAS=() MEASRAW=()

parse_meas() {
  MEAS=(); MEASRAW=()
  local log="$1" line name val first in=0 seen=0
  while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*Measurements[[:space:]]+for[[:space:]] ]]; then
      in=1; seen=0; continue
    fi
    if ((in)); then
      if [[ "$line" =~ ^[[:space:]]*$ ]]; then
        ((seen)) && in=0
        continue
      fi
      if [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_.]*)[[:space:]]*=[[:space:]]*(.+)$ ]]; then
        name="${BASH_REMATCH[1]}"; val="${BASH_REMATCH[2]}"
        MEASRAW["$name"]="$val"
        first="${val%%[[:space:]]*}"
        if is_number "$first"; then MEAS["$name"]="$first"; else MEAS["$name"]=""; fi
        seen=1
      else
        in=0
      fi
    fi
  done <"$log"
}

# =============================================================================
# static checks (--check)
# =============================================================================
CHECK_NDJSON=""
CHECK_FAIL=0
CHK_TOTAL=0

check_add() { # name status detail
  local name="$1" status="$2" detail="$3"
  CHK_TOTAL=$((CHK_TOTAL + 1))
  [[ "$status" == FAIL ]] && CHECK_FAIL=1
  if ((JSON_OUT)); then
    jq -cn --arg n "$name" --arg s "$status" --arg d "$detail" \
      '{name:$n,status:$s,detail:$d}' >>"$CHECK_NDJSON"
  else
    printf '%-34s %s  %s\n' "$name" "$status" "$detail" >&2
  fi
}

run_checks() {
  CHECK_NDJSON="$(mktemp)"
  info "${C_BLD}== static checks ==${C_RST}"
  local t

  for t in jq nix timeout grep awk; do
    if command -v "$t" >/dev/null 2>&1; then check_add "tool:$t" PASS "$(command -v "$t")"
    else check_add "tool:$t" FAIL "not found in PATH"; fi
  done

  if "${NGSPICE_BASE[@]}" --version >/dev/null 2>&1; then
    check_add "ngspice" PASS "$(ngspice_version)"
  else
    check_add "ngspice" FAIL "nix shell nixpkgs#ngspice -c ngspice --version failed"
  fi

  if [[ -f "$CRITERIA" ]]; then
    if parse_criteria >/dev/null 2>&1; then
      check_add "criteria.tsv" PASS "$CRITERIA (${#CRIT_TEST[@]} rules)"
    else
      check_add "criteria.tsv" FAIL "$(parse_criteria 2>&1 | tail -1)"
    fi
  else
    check_add "criteria.tsv" FAIL "missing: $CRITERIA"
  fi

  discover_tests
  if ((${#TESTS[@]} > 0)); then
    check_add "tests/*.cir" PASS "${#TESTS[@]} file(s): $(printf '%s ' "${TESTS[@]##*/}")"
  else
    check_add "tests/*.cir" FAIL "no tests in $TESTS_DIR"
  fi

  local f base bad
  for f in "${TESTS[@]}"; do
    base="$(basename "$f")"
    bad=""
    grep -qE '^[[:space:]]*\.step\b' "$f" && bad+=".step "
    grep -qE 'TRIG[[:space:]]+[^ ]+[[:space:]]*=[^[:space:]]' "$f" && bad+="TRIG v(x)=y "
    grep -qE 'FIND[[:space:]]+abs[[:space:]]*\(' "$f" && bad+="FIND abs(...) "
    grep -qiE 'vdmos.*[^a-z]ron[[:space:]]*=' "$f" && bad+="VDMOS Ron= "
    [[ -s "$f" ]] || bad+="empty "
    if [[ -n "$bad" ]]; then
      check_add "netlist:$base" FAIL "ngspice-45 incompatible/ignored: $bad"
    else
      check_add "netlist:$base" PASS "no known ngspice-45 hazards"
    fi
  done

  if tests_reference_master; then
    if [[ -f "$MASTER" ]]; then check_add "master netlist" PASS "$MASTER"
    else check_add "master netlist" FAIL "referenced by tests but missing: $MASTER"; fi
  else
    check_add "master netlist" PASS "not referenced by tests (not required)"
  fi

  # criteria coverage
  if parse_criteria >/dev/null 2>&1; then
    local i matched=0 unknowns=0
    for i in "${!CRIT_TEST[@]}"; do
      matched=0
      for f in "${TESTS[@]}"; do
        # shellcheck disable=SC2053
        if [[ "$(basename "$f" .cir)" == "${CRIT_TEST[$i]}" ]]; then matched=1; break; fi
      done
      ((matched)) || { unknowns=$((unknowns + 1)); warn "criteria rule for unknown test '${CRIT_TEST[$i]}'"; }
    done
    for f in "${TESTS[@]}"; do
      base="$(basename "$f" .cir)"; matched=0
      for i in "${!CRIT_TEST[@]}"; do
        [[ "${CRIT_TEST[$i]}" == "$base" ]] && { matched=1; break; }
      done
      ((matched)) || check_add "criteria:$base" FAIL "test has no criteria"
    done
    ((unknowns == 0)) && check_add "criteria coverage" PASS "all rules map to existing tests" \
      || check_add "criteria coverage" FAIL "$unknowns rule(s) reference unknown tests"
  fi

  return "$CHECK_FAIL"
}

# =============================================================================
# run one test
# =============================================================================
NDJSON=""

run_sim() { # file -> prints one JSON test object, returns 0 pass / 1 fail
  local file="$1"
  local base log rc start dur
  base="$(basename "$file" .cir)"
  log="$LOG_DIR/$base.log"

  start="${EPOCHREALTIME:-$SECONDS}"
  if ((VERBOSE)); then info "+ (cd $ROOT && ${NGSPICE_BASE[*]} -b $file) > $log"; fi
  (cd "$ROOT" && timeout "$NGSPICE_TIMEOUT" "${NGSPICE_BASE[@]}" -b "$file") >"$log" 2>&1
  rc=$?
  dur="$(awk -v a="$start" -v b="${EPOCHREALTIME:-$SECONDS}" 'BEGIN{printf "%.3f", b-a}')"

  parse_meas "$log"

  local -a err_lines=() warn_lines=() benign_lines=()
  local flt wl
  flt="$(mktemp)"
  # drop the echoed netlist title ("Circuit: ...") so a comment containing a
  # diagnostic word cannot be mistaken for a real ngspice message
  grep -vE '^[[:space:]]*(Circuit:|Title:|\*)' "$log" >"$flt" 2>/dev/null || true
  mapfile -t err_lines < <(grep -iE -- "$FATAL_RE" "$flt" 2>/dev/null || true)
  mapfile -t wl < <(grep -iE -- "$WARN_RE" "$flt" 2>/dev/null || true)
  for wl in "${wl[@]+"${wl[@]}"}"; do
    if [[ "$wl" =~ $BENIGN_RE ]]; then benign_lines+=("$wl"); else warn_lines+=("$wl"); fi
  done

  # ---- criteria ----
  local -a crit_rows=() fail_reasons=()
  local i used alias val cr cstatus creason metric_raw
  local found_rows=0 crit_fail=0
  for i in "${!CRIT_TEST[@]}"; do
    [[ "${CRIT_TEST[$i]}" == "$base" ]] || continue
    found_rows=1
    metric_raw="${CRIT_METRIC[$i]}"
    used=""; val=""
    local -a aliases=()
    IFS='|' read -r -a aliases <<<"$metric_raw"
    for alias in "${aliases[@]}"; do
      alias="$(trim "$alias")"
      if [[ -v "MEAS[$alias]" ]]; then used="$alias"; val="${MEAS[$alias]}"; break; fi
    done
    cstatus=FAIL; creason=""
    if [[ -z "$used" ]]; then
      creason="metric not found in ngspice output"
      crit_fail=1
    elif [[ -z "$val" ]]; then
      creason="non-numeric value '${MEASRAW[$used]}'"
      crit_fail=1
    else
      num_cmp "$val" "${CRIT_OP[$i]}" "${CRIT_THR[$i]}"; cr=$?
      if ((cr == 0)); then cstatus=PASS
      elif ((cr == 1)); then cstatus=FAIL; creason="value $val does not satisfy ${CRIT_OP[$i]} ${CRIT_THR[$i]}"; crit_fail=1
      else cstatus=ERROR; creason="bad operator"; crit_fail=1
      fi
    fi
    crit_rows+=("$(jq -cn \
      --arg metric "$metric_raw" --arg resolved "$used" --arg op "${CRIT_OP[$i]}" \
      --argjson thr "${CRIT_THR[$i]}" \
      --arg val "$val" --arg raw "$( [[ -n "$used" ]] && printf '%s' "${MEASRAW[$used]:-}" )" \
      --arg status "$cstatus" --arg reason "$creason" --arg note "${CRIT_NOTE[$i]}" \
      '{metric:$metric,resolved:$resolved,operator:$op,threshold:$thr,value:(if $val=="" then null else ($val|tonumber) end),raw_value:$raw,status:$status,reason:$reason,note:$note}')")
  done

  local status=PASS fail=0
  ((${#err_lines[@]} == 0)) || { fail=1; fail_reasons+=("ngspice error output: ${err_lines[0]}"); }
  ((${#warn_lines[@]} == 0)) || { fail=1; fail_reasons+=("ngspice warning output: ${warn_lines[0]}"); }
  ((rc == 0)) || { fail=1; fail_reasons+=("ngspice exit code $rc"); }
  if ((rc == 124)); then fail_reasons+=("timeout after ${NGSPICE_TIMEOUT}s"); fi
  ((crit_fail)) && { fail=1; fail_reasons+=("acceptance criteria not met"); }
  if ((found_rows == 0)); then fail=1; fail_reasons+=("no criteria for test in criteria.tsv"); fi
  ((fail)) && status=FAIL

  local -a err_json=() warn_json=() benign_json=() crit_json_arr=()
  local x
  for x in "${err_lines[@]+"${err_lines[@]}"}"; do err_json+=("$x"); done
  for x in "${warn_lines[@]+"${warn_lines[@]}"}"; do warn_json+=("$x"); done
  for x in "${benign_lines[@]+"${benign_lines[@]}"}"; do benign_json+=("$x"); done
  for x in "${crit_rows[@]+"${crit_rows[@]}"}"; do crit_json_arr+=("$x"); done

  local err_file warn_file ben_file crit_file meas_file
  err_file="$(mktemp)"; warn_file="$(mktemp)"; ben_file="$(mktemp)"; crit_file="$(mktemp)"; meas_file="$(mktemp)"
  printf '%s\n' "${err_json[@]+"${err_json[@]}"}" | jq -Rsc 'split("\n")|map(select(length>0))' >"$err_file"
  printf '%s\n' "${warn_json[@]+"${warn_json[@]}"}" | jq -Rsc 'split("\n")|map(select(length>0))' >"$warn_file"
  printf '%s\n' "${benign_json[@]+"${benign_json[@]}"}" | jq -Rsc 'split("\n")|map(select(length>0))' >"$ben_file"
  if ((${#crit_json_arr[@]})); then printf '%s\n' "${crit_json_arr[@]}" | jq -s . >"$crit_file"; else echo '[]' >"$crit_file"; fi
  # measurements object
  local k mv meas_json='{}'
  local -a meas_keys=()
  if ((${#MEAS[@]})); then
    mapfile -t meas_keys < <(printf '%s\n' "${!MEAS[@]}" | sort)
  fi
  for k in "${meas_keys[@]+"${meas_keys[@]}"}"; do
    mv="${MEAS[$k]}"
    if [[ -n "$mv" ]]; then
      meas_json="$(jq -cn --argjson b "$meas_json" --arg k "$k" --argjson v "$mv" '$b+{($k):$v}')"
    else
      meas_json="$(jq -cn --argjson b "$meas_json" --arg k "$k" --arg v "${MEASRAW[$k]}" '$b+{($k):$v}')"
    fi
  done
  echo "$meas_json" >"$meas_file"

  local reason=""
  if ((${#fail_reasons[@]})); then
    reason="$(printf '%s; ' "${fail_reasons[@]}")"
    reason="${reason%; }"
  fi

  jq -cn \
    --arg test "$base" --arg file "$file" --arg log "$log" --arg status "$status" \
    --argjson exit_code "$rc" --argjson duration_s "$dur" \
    --slurpfile measurements "$meas_file" \
    --slurpfile criteria "$crit_file" \
    --slurpfile errors "$err_file" \
    --slurpfile warnings "$warn_file" \
    --slurpfile benign "$ben_file" \
    --arg reason "$reason" \
    '{test:$test,file:$file,log:$log,status:$status,exit_code:$exit_code,duration_s:$duration_s,
      measurements:$measurements[0],criteria:$criteria[0],errors:$errors[0],
      warnings:$warnings[0],benign_warnings:$benign[0],reason:$reason}'

  rm -f "$flt" "$err_file" "$warn_file" "$ben_file" "$crit_file" "$meas_file"
  ((fail == 0))
}

# =============================================================================
# report
# =============================================================================
write_report() { # results.json -> CI_REPORT.md
  local report_path="$ROOT/CI_REPORT.md"
  {
    echo "# CI report — uPC1237_SSR"
    echo
    echo "- Generated: $(jq -r '.generated_at' "$RESULTS")"
    echo "- ngspice: \`$(jq -r '.ngspice' "$RESULTS")\`"
    echo "- Command: \`$(jq -r '.command' "$RESULTS")\`"
    echo "- Verdict: **$(jq -r '.summary.status' "$RESULTS")** — $(jq -r '.summary.passed' "$RESULTS") passed, $(jq -r '.summary.failed' "$RESULTS") failed of $(jq -r '.summary.total' "$RESULTS")"
    echo
    echo "## Summary"
    echo
    echo "| test | status | exit | time, s | measurements |"
    echo "|---|---|---|---|---|"
    jq -r '.tests[] | "| \(.test) | \(.status) | \(.exit_code) | \(.duration_s) | \(.measurements|to_entries|map("\(.key)=\(.value)")|join(", ")) |"' "$RESULTS"
    echo
    echo "## Details"
    echo
    jq -r '.tests[] |
      "### \(.test) — \(.status)\n\n" +
      (if .reason != "" then "Reason: `\(.reason)`\n\n" else "" end) +
      "Criteria:\n\n| metric | op | threshold | value | status |\n|---|---|---|---|---|\n" +
      (.criteria | map("| \(.metric) | \(.operator) | \(.threshold) | \(.value // "—") | \(.status) |") | join("\n")) +
      "\n\nngspice measured output:\n\n```\n" +
      (.measurements | to_entries | map("\(.key) = \(.value)") | join("\n")) +
      "\n```\n\n" +
      (if (.errors|length)>0 then "ngspice errors:\n\n```\n" + (.errors|join("\n")) + "\n```\n\n" else "" end) +
      (if (.warnings|length)>0 then "ngspice warnings:\n\n```\n" + (.warnings|join("\n")) + "\n```\n\n" else "" end) +
      (if (.benign_warnings|length)>0 then "benign warnings (recorded, not fatal):\n\n```\n" + (.benign_warnings|join("\n")) + "\n```\n\n" else "" end) +
      "Raw log: `\(.log)`\n"' "$RESULTS"
  } >"$report_path"
  info "${C_BLD}wrote $report_path${C_RST}"
}

# =============================================================================
# main
# =============================================================================
parse_args() {
  while (($#)); do
    case "$1" in
      --check) CHECK_ONLY=1 ;;
      --json) JSON_OUT=1 ;;
      --no-wait) NO_WAIT=1 ;;
      --wait) shift; [[ $# ]] || die "--wait needs a number"; WAIT_SECONDS="$1" ;;
      --wait=*) WAIT_SECONDS="${1#*=}" ;;
      --only) shift; [[ $# ]] || die "--only needs a pattern"; ONLY_PATTERN="$1" ;;
      --only=*) ONLY_PATTERN="${1#*=}" ;;
      --report) WRITE_REPORT=1 ;;
      --verbose|-v) VERBOSE=1 ;;
      -h|--help) usage; exit 0 ;;
      *) die "unknown option: $1 (try --help)" ;;
    esac
    shift
  done
  [[ "$WAIT_SECONDS" =~ ^[0-9]+$ ]] || die "--wait must be an integer"
}

ngspice_version() {
  "${NGSPICE_BASE[@]}" --version 2>&1 | grep -m1 -oE 'ngspice-[0-9]+' || echo "ngspice-unknown"
}

main() {
  parse_args "$@"
  command -v jq >/dev/null 2>&1 || die "jq is required"
  command -v nix >/dev/null 2>&1 || die "nix is required"
  command -v timeout >/dev/null 2>&1 || die "timeout is required"

  if ((CHECK_ONLY)); then
    run_checks; rc=$?
    if ((JSON_OUT)); then
      jq -s --argjson ok "$((rc == 0 ? 1 : 0))" '{mode:"check",ok:($ok==1),checks:.}' "$CHECK_NDJSON"
    fi
    rm -f "$CHECK_NDJSON"
    ((rc == 0)) && info "${C_GRN}check: OK${C_RST}" || err "check: FAIL"
    exit "$rc"
  fi

  NGVER="$(ngspice_version)"
  mkdir -p "$LOG_DIR"
  NDJSON="$(mktemp)"

  if ((NO_WAIT)); then
    discover_tests
    if ((${#TESTS[@]} == 0)); then err "no tests/*.cir found in $TESTS_DIR"; exit 3; fi
    if tests_reference_master && [[ ! -f "$MASTER" ]]; then
      err "tests include uPC1237_SSR.cir but $MASTER is missing (--no-wait)"; exit 3
    fi
  else
    wait_for_inputs || { err "inputs did not appear within ${WAIT_SECONDS}s"; exit 3; }
  fi
  discover_tests
  ((${#TESTS[@]})) || { err "no tests/*.cir found in $TESTS_DIR"; exit 3; }

  parse_criteria || exit 2

  ((JSON_OUT)) || info "${C_BLD}== run: ${#TESTS[@]} test(s), ngspice $NGVER ==${C_RST}"
  local f base status
  N_TOTAL=0; N_PASS=0; N_FAIL=0
  for f in "${TESTS[@]}"; do
    base="$(basename "$f" .cir)"
    ((JSON_OUT)) || printf '%-28s ' "$base" >&2
    if run_sim "$f" >>"$NDJSON"; then
      status=PASS
    else
      status=FAIL
    fi
    N_TOTAL=$((N_TOTAL + 1))
    if [[ "$status" == PASS ]]; then N_PASS=$((N_PASS + 1)); else N_FAIL=$((N_FAIL + 1)); fi
    ((JSON_OUT)) || {
      if [[ "$status" == PASS ]]; then printf '%sPASS%s\n' "$C_GRN" "$C_RST" >&2
      else printf '%sFAIL%s\n' "$C_RED" "$C_RST" >&2; fi
    }
  done

  local overall=PASS ts
  ((N_FAIL == 0)) || overall=FAIL
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  local commit=""
  if command -v git >/dev/null 2>&1; then commit="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"; fi

  jq -s \
    --arg schema "uPC1237_SSR/ci-results/1" \
    --arg generated_at "$ts" \
    --arg root "$ROOT" \
    --arg ngspice "$NGVER" \
    --arg command "${NGSPICE_BASE[*]} -b <test.cir>" \
    --arg host "$(uname -srm)" \
    --arg git_commit "$commit" \
    --argjson total "$N_TOTAL" --argjson passed "$N_PASS" --argjson failed "$N_FAIL" \
    --arg status "$overall" \
    '{schema:$schema,generated_at:$generated_at,root:$root,ngspice:$ngspice,command:$command,host:$host,git_commit:$git_commit,summary:{total:$total,passed:$passed,failed:$failed,status:$status},tests:.}' \
    "$NDJSON" >"$RESULTS"

  if ((JSON_OUT)); then
    cat "$RESULTS"
  else
    info ""
    info "${C_BLD}== per-criterion detail ==${C_RST}"
    jq -r '.tests[] | .test as $t | .criteria[] | "\($t)\t\(.metric)\t\(.operator)\t\(.threshold)\t\(if .value==null then "—" else (.value|tostring) end)\t\(.status)"' "$RESULTS" \
      | awk -F'\t' 'BEGIN{printf "%-24s %-22s %-6s %-12s %-12s %s\n","test","metric","op","threshold","value","result"}
                     {printf "%-24s %-22s %-6s %-12s %-12s %s\n",$1,$2,$3,$4,$5,$6}'
    info ""
    if [[ "$overall" == PASS ]]; then
      info "${C_GRN}${C_BLD}RESULT: PASS${C_RST} (${N_PASS}/${N_TOTAL})"
    else
      info "${C_RED}${C_BLD}RESULT: FAIL${C_RST} (${N_PASS} passed, ${N_FAIL} failed of ${N_TOTAL})"
      jq -r '.tests[] | select(.status!="PASS") | "  - \(.test): \(.reason)"' "$RESULTS" >&2
    fi
    info "results: $RESULTS"
  fi

  ((WRITE_REPORT)) && write_report
  rm -f "$NDJSON"
  ((N_FAIL == 0)) && exit 0 || exit 1
}

main "$@"
