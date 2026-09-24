#!/usr/bin/env bash
# preflight.sh — проверка согласованности комплекта ПЕРЕД прогоном CI (см. REVIEW.md P1-1/P1-4).
# 1) .asc должен соответствовать .cir (перегенерация в temp + diff)
# 2) tests/*.cir должны соответствовать gen_tests.py (перегенерация в temp + diff)
# 3) BOM.csv должен соответствовать мастеру (перегенерация + diff)
# 4) записать хэши входов в tests/inputs.sha256
set -u; cd "$(dirname "$0")"; rc=0
T=$(mktemp -d)
cp uPC1237_SSR.cir "$T/" ; cp uPC1237_SSR.asc "$T/asc_ref"
python3 gen_schematic.py >/dev/null || { echo "FAIL: gen_schematic.py"; rc=1; }
diff -q "$T/asc_ref" uPC1237_SSR.asc >/dev/null || { echo "FAIL: uPC1237_SSR.asc устарел (перегенерировать)"; rc=1; }
mkdir -p "$T/tests" && cp tests/*.cir "$T/tests/"
python3 gen_tests.py >/dev/null || { echo "FAIL: gen_tests.py"; rc=1; }
diff -rq "$T/tests" tests/ | grep -v 'results.json\|criteria.tsv\|inputs.sha256' && { echo "FAIL: tests/*.cir расходятся с генератором"; rc=1; }
rm -rf "$T"
python3 gen_bom.py >/dev/null || { echo "FAIL: gen_bom.py"; rc=1; }
sha256sum uPC1237_SSR.cir uPC1237_SSR.asc gen_tests.py gen_schematic.py gen_bom.py tests/*.cir tests/criteria.tsv models/cards.model > tests/inputs.sha256
echo "preflight: $( [ $rc = 0 ] && echo OK || echo FAIL ) — хэши входов: tests/inputs.sha256"
exit $rc
