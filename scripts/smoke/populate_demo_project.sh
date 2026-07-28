#!/usr/bin/env bash
# Smoke test (GitHub issue #31): runs the doc-28 dev coordinator
# (`diffpype-manage populate-demo-project`) against a live `docker compose up`
# stack and asserts the domain graph actually got populated.
#
# Deliberately not wired into CI: it needs real Celery workers consuming the
# queue, and CI currently starts only db/minio directly, not the full stack.
# Run manually, locally, against your own docker compose stack.
#
# Built on top of the coordinator rather than reimplementing its sequence —
# the coordinator already polls each Celery task (ingest, mosaic) to a
# terminal state internally, so this script does not need its own poll loop.
#
# PREREQUISITE (GitHub issue #34, not yet resolved): this needs a real
# --S3_PREFIX already populated with FITS files in MinIO. There is currently
# no minio-init fiducial seed dataset, so this script cannot run end-to-end
# until #34 lands — the assertions below document what "success" means once
# it does.
set -euo pipefail

: "${PROJECT_NAME:=SmokeTestProject}"
: "${USER_ID:?USER_ID must be set to an existing User id}"
: "${S3_PREFIX:?S3_PREFIX must be set to a populated storage prefix (see issue #34)}"
: "${RA:?RA must be set (deg)}"
: "${DECL:?DECL must be set (deg)}"
: "${RADIUS_DEG:?RADIUS_DEG must be set (deg)}"
: "${BAND_ID:?BAND_ID must be set to an existing Band id}"
: "${INSTRUMENT_ID:?INSTRUMENT_ID must be set to an existing Instrument id}"

echo "Running populate-demo-project against the live docker compose stack..."
docker compose exec -T api diffpype-manage populate-demo-project \
    --project-name "$PROJECT_NAME" \
    --user-id "$USER_ID" \
    --s3-prefix "$S3_PREFIX" \
    --ra "$RA" \
    --decl "$DECL" \
    --radius-deg "$RADIUS_DEG" \
    --band-id "$BAND_ID" \
    --instrument-id "$INSTRUMENT_ID"

echo ""
echo "Asserting the domain graph was actually populated..."
docker compose exec -T db psql -U "${POSTGRES_USER:-diffpype}" -d "${POSTGRES_DB:-diffpype}" -v ON_ERROR_STOP=1 <<SQL
DO \$\$
DECLARE
    proj_id INT;
    n_images INT;
    n_tiles INT;
    n_epochs INT;
    n_mosaics INT;
BEGIN
    SELECT id INTO proj_id FROM projects WHERE name = '${PROJECT_NAME}' ORDER BY id DESC LIMIT 1;
    IF proj_id IS NULL THEN
        RAISE EXCEPTION 'SMOKE TEST FAILED: no project named %', '${PROJECT_NAME}';
    END IF;

    SELECT count(*) INTO n_images FROM level2_calibrations WHERE project_id = proj_id;
    SELECT count(*) INTO n_tiles FROM tiles WHERE project_id = proj_id;
    SELECT count(*) INTO n_epochs FROM epochs WHERE project_id = proj_id;
    SELECT count(*) INTO n_mosaics FROM level3_mosaics WHERE project_id = proj_id AND status = 'complete';

    RAISE NOTICE 'project_id=%, calibrations=%, tiles=%, epochs=%, complete_mosaics=%',
        proj_id, n_images, n_tiles, n_epochs, n_mosaics;

    IF n_images = 0 THEN
        RAISE EXCEPTION 'SMOKE TEST FAILED: no Level2Calibration rows for project %', proj_id;
    END IF;
    IF n_tiles = 0 THEN
        RAISE EXCEPTION 'SMOKE TEST FAILED: no Tile rows for project %', proj_id;
    END IF;
    IF n_epochs = 0 THEN
        RAISE EXCEPTION 'SMOKE TEST FAILED: no Epoch rows for project %', proj_id;
    END IF;
    IF n_mosaics = 0 THEN
        RAISE EXCEPTION 'SMOKE TEST FAILED: no COMPLETE Level3Mosaic rows for project %', proj_id;
    END IF;

    RAISE NOTICE 'SMOKE TEST PASSED';
END \$\$;
SQL

echo "Done."
