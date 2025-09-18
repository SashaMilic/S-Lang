#!/bin/bash
#init
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
cd "$root"
git ls-files > tools/.filelist
tar -czf /tmp/S-Lang-src.tgz -T tools/.filelist
echo "Packed to /tmp/S-Lang-src.tgz"