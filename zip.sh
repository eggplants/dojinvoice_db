#!/usr/bin/env bash

set -euxo pipefail

[[ -f dojinvoice.db ]] || {
  echo 'Please create dojinvoice.db'>&2
  exit 1
}

CREATED_AT="$(date +%Y%m%d)"

TAR_NAME="dojinvoice.db.${CREATED_AT}.tar.gz"
time tar -I 'gzip -9' -cf "$TAR_NAME" dojinvoice.db

ZIP_NAME="dojinvoice.db.${CREATED_AT}.zip"
time zip -9 "$ZIP_NAME" dojinvoice.db

du -ch dojinvoice.db "$TAR_NAME" "$ZIP_NAME"
