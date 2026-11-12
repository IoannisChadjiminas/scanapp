#!/bin/bash
# Build one inactive catalogue candidate on top of a parent release package and stage its artifacts.
#   build_stage.sh RUN_DIR PARENT_RELEASE_DIR NAME TARGET_SCHEMA TARGET_IMPORT PARENT_SCHEMA PARENT_IMPORT \
#                  PARENT_FEATURES NEW_FEATURES NEW_ARTWORK NEW_IMAGEDIR_NAME PARENT_LOCAL_DATA READ_ROLE_JSON ENV_FILE
# Needs the ssh alias auctaro-staging, the repository venv, pscale, and ENV_FILE exporting the JAREC_* texts
# (JAREC_RIGHTS, JAREC_NAME_DECISION, JAREC_PROVENANCE, JAREC_VERIFIED_AT). The decision file RUN_DIR/index-decision.json
# must already exist (decide_lookalikes.py). Steps: build_release, prepare_sql (signature rows), stage the images,
# artwork and reference features on the staging host (own memory-capped container, never the live API),
# prepare_sql again with the real feature manifest hash, apply_sql with a 1 h admin role, copy the artifacts into
# RUN_DIR/local-data for the local replay. Never prints a database URL.
set -euo pipefail
RUN=$1 PARENT_REL=$2 NAME=$3 TARGET=$4 IMPORT=$5 PSCHEMA=$6 PIMPORT=$7 PFEAT=$8 NFEAT=$9 NART=${10} NIMG=${11} PLOCAL=${12} ROLE=${13} ENVF=${14}
PY=/Users/ioannischadjiminas/WebstormProjects/scanapp/.venv/bin/python
S=api/scripts/ja_set_recovery
. "$ENVF"
export JAREC_IMAGE_DIR=/data/reference-images/$NIMG JAREC_PARENT=$PSCHEMA JAREC_PARENT_IMPORT=$PIMPORT JAREC_TARGET=$TARGET JAREC_IMPORT=$IMPORT JAREC_RUN_DIR=$RUN
REL=$RUN/$NAME
V=/var/lib/docker/volumes/scanapp-scanapp-z1mwj4_scanapp-data/_data
rm -rf "$REL"
$PY $S/build_release.py "$RUN" "$PARENT_REL" "$NAME" | grep -E "cards_total|scannable|no_image"
$PY $S/prepare_sql.py "$REL" "$ROLE" 0000000000000000000000000000000000000000000000000000000000000000 >/dev/null
WK=/root/stage-$NAME
ssh auctaro-staging "rm -rf $WK; mkdir -p $WK/work"
scp -q "$REL/feature-rows.json" "$REL/signature-rows.json" $S/stage_features.py auctaro-staging:$WK/work/
scp -q -r "$REL/artwork" auctaro-staging:$WK/artwork
if [ -d "$REL/images" ] && [ -n "$(ls -A "$REL/images")" ]; then scp -q -r "$REL/images" auctaro-staging:$WK/images; else ssh auctaro-staging "mkdir -p $WK/images"; fi
FEATJSON=$(ssh auctaro-staging "sudo -n mkdir -p $V/reference-images/$NIMG $V/artwork/$NART && sudo -n cp --update=none $WK/images/* $V/reference-images/$NIMG/ 2>/dev/null; sudo -n cp --update=none $WK/artwork/* $V/artwork/$NART/ && docker run --rm --memory 1200m --memory-swap 1200m --cpus 1 -v $V:/data -v $WK/work:/work scanapp-scanapp-z1mwj4-api:latest python3 /work/stage_features.py $PFEAT $NFEAT 2>&1 | grep -v -i warn | tail -1")
echo "$FEATJSON"
SHA=$(echo "$FEATJSON" | $PY -I -c "import json,sys; print(json.loads(sys.stdin.read())['manifest_sha256'])")
$PY $S/prepare_sql.py "$REL" "$ROLE" "$SHA" | grep -E "sql_sha"
ADM=$(dirname "$ROLE")/admin.json
( cd "$(dirname "$ROLE")" && umask 077 && pscale role create pokesingle-db main sbcards-admin-$NAME-$(date +%H%M) --inherited-roles postgres --ttl 1h --format json > admin.json 2> admin.err )
sleep 20
$PY $S/apply_sql.py "$REL/sql/candidate.sql" "$ADM" | grep -E "committed|rolled|message"
L=$RUN/local-data
mkdir -p "$L/reference-features" "$L/artwork"
cp -Rc "$PLOCAL/reference-features/$PFEAT" "$L/reference-features/$NFEAT"
ssh auctaro-staging "cd $V/reference-features; sudo -n cat $NFEAT/manifest.json" > "$L/reference-features/$NFEAT/manifest.json"
ssh auctaro-staging "cd $V/reference-features; sudo -n find $NFEAT -type f -links 1 -printf '%P\n' | sudo -n tar -C $NFEAT -cf - -T -" | tar -C "$L/reference-features/$NFEAT" -xf -
cp -R "$REL/artwork" "$L/artwork/$NART"
[ -e "$L/reference-images" ] || cp -Rc "$PLOCAL/reference-images" "$L/reference-images"
[ -d "$REL/images" ] && cp -R "$REL/images" "$L/reference-images/$NIMG"
[ -e "$L/models" ] || cp -Rc "$PLOCAL/models" "$L/models"
echo "STAGED $NAME features=$NFEAT sha=$SHA"
