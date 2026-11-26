#!/usr/bin/env bash
# Run cartography.py (or the tests) in a throwaway python container.
# Passes GITLAB_TOKEN / GITLAB_URL through from the environment, and
# PIP_INDEX_URL / PIP_TRUSTED_HOST when set (for a corporate PyPI mirror).
#
# Corporate CA: set CA_CERT to the path of the PEM certificate file, e.g.
#   export CA_CERT=/usr/local/share/ca-certificates/corp.crt
# It is trusted in addition to the usual public CAs (for pip and for GitLab).
#
#   ./run-in-docker.sh --suffix=-framework --groups grp-a,grp-b
#   ./run-in-docker.sh --test
set -euo pipefail

cd "$(dirname "$0")"
IMAGE="${CARTOGRAF_IMAGE:-python:3.13-slim}"

args=(--rm -v "$PWD":/w -w /w -v cartograf-pip-cache:/root/.cache/pip
      -e GITLAB_TOKEN -e GITLAB_URL -e PIP_INDEX_URL -e PIP_TRUSTED_HOST
      -e PIP_ROOT_USER_ACTION=ignore -e PYTHONDONTWRITEBYTECODE=1)
setup=""
if [ -n "${CA_CERT:-}" ]; then
  if [ ! -f "$CA_CERT" ]; then
    echo "CA_CERT file not found: $CA_CERT" >&2
    exit 2
  fi
  # Public CAs + the given cert in one bundle, used by requests (GitLab) and pip.
  args+=(-v "$(realpath "$CA_CERT")":/ca/extra.crt:ro
         -e REQUESTS_CA_BUNDLE=/tmp/ca-bundle.pem -e SSL_CERT_FILE=/tmp/ca-bundle.pem
         -e PIP_CERT=/tmp/ca-bundle.pem)
  setup='cat /etc/ssl/certs/ca-certificates.crt /ca/extra.crt > /tmp/ca-bundle.pem && '
fi
[ -t 1 ] && args+=(-t)

if [ "${1:-}" = "--test" ]; then
  shift
  cmd='pip install -q --disable-pip-version-check -r requirements.txt -r requirements-dev.txt && python -m pytest -p no:cacheprovider "$@"'
else
  cmd='pip install -q --disable-pip-version-check -r requirements.txt && python cartography.py "$@"'
fi

exec docker run "${args[@]}" "$IMAGE" sh -c "$setup$cmd" sh "$@"
