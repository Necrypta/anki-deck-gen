# Build label. CI overwrites this file before packaging (see scripts/stamp_build.py):
#   "v0.2.0"            tagged release
#   "PR #4 · a1b2c3d"   pull-request test build
#   "main · a1b2c3d"    build of main
# "dev" means running from source.
BUILD = "dev"
