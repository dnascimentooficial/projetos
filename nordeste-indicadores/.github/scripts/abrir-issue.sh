#!/usr/bin/env bash
# Abre uma issue com o titulo e o corpo dados; se ja ha uma aberta com o mesmo titulo, comenta nela em vez de duplicar.
# Uso: .github/scripts/abrir-issue.sh "<titulo>" <arquivo-do-corpo>
# Precisa de GH_TOKEN (e de GH_REPO ou de um checkout do repositorio). O corpo vai sempre por arquivo.
set -euo pipefail

titulo=$1
corpo=$2

# Lista sem --search: a busca do GitHub tem atraso de indice e le "palavra:" como filtro; o titulo e comparado inteiro.
numero=$(gh issue list --state open --limit 1000 --json number,title | python3 -c '
import json, sys
titulo = sys.argv[1]
print(next((str(i["number"]) for i in json.load(sys.stdin) if i["title"] == titulo), ""))
' "$titulo")

if [ -n "$numero" ]; then
  gh issue comment "$numero" --body-file "$corpo"
else
  gh issue create --title "$titulo" --body-file "$corpo"
fi
