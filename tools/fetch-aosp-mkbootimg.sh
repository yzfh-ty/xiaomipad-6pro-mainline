#!/bin/sh

set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
extract_dir="$project_root/tools/local/aosp-mkbootimg"
commit=954bc3ead5e679005fddf3484d247f2557b3c2c9
mkbootimg_sha256=37d84b3d162e0bc62e36c1f4e1c63c85ea0caa9f29be023eb2f8efe006ad948c
unpack_sha256=06b54dd9a07c5281778e29e234e76f6e3faee8bf0c904a5ef88fdee30eeed12e

# Gitiles tar.gz wrappers can change independently of the source. Fetch the
# exact Git tree and retain the hashes of both consumed Python entry points.
if [ ! -d "$extract_dir/.git" ]; then
	[ ! -e "$extract_dir" ] || { echo 'Use a fresh mkbootimg input directory' >&2; exit 1; }
	mkdir -p "$extract_dir"
	git -C "$extract_dir" init -q
	git -C "$extract_dir" fetch --depth=1 \
		https://android.googlesource.com/platform/system/tools/mkbootimg "$commit"
	git -C "$extract_dir" checkout --detach FETCH_HEAD
fi
[ "$(git -C "$extract_dir" rev-parse HEAD)" = "$commit" ]
[ -z "$(git -C "$extract_dir" status --porcelain --untracked-files=no)" ]
echo "$mkbootimg_sha256  $extract_dir/mkbootimg.py" | sha256sum --check
echo "$unpack_sha256  $extract_dir/unpack_bootimg.py" | sha256sum --check

printf 'AOSP tag: android-16.0.0_r4\ncommit: %s\n' "$commit"
python3 "$extract_dir/mkbootimg.py" --help >/dev/null
python3 "$extract_dir/unpack_bootimg.py" --help >/dev/null
