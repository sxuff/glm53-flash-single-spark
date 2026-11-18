#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
image="${IMAGE:-sxuff/glm53f-gr8-tail:2}"
revision=d598965a1bbf3cd220ad9ad856bfd63da2466424
source_tree=3c0f8ddf3fe179e2444e1444599bfec9407a6b19
patch_sha=4e939f1faea365381586cfcb8959f1cbc7e60d99894430d8288138b24c4795ec

(cd "$here" && printf '%s  glmtail.patch\n' "$patch_sha" | sha256sum --check)
build_dir="$(mktemp -d)"
trap 'rm -rf -- "$build_dir"' EXIT
src="$build_dir/gr8"
git init -q "$src"
git -C "$src" fetch -q --depth=1 https://github.com/kindlingai/gr8.git "$revision"
git -C "$src" checkout -q --detach FETCH_HEAD
if [[ "$(git -C "$src" rev-parse HEAD)" != "$revision" || "$(git -C "$src" rev-parse 'HEAD^{tree}')" != "$source_tree" ]]; then
  echo "Unexpected GR8 source revision or tree." >&2
  exit 1
fi
git -C "$src" apply --check "$here/glmtail.patch"
git -C "$src" apply "$here/glmtail.patch"
# The upstream dist-flash-int4 stage produces the engine binary. Append only
# the packaging stage so BuildKit can copy that binary between stages directly.
cat "$src/Dockerfile" > "$build_dir/Dockerfile"
printf '\n' >> "$build_dir/Dockerfile"
cat "$here/Dockerfile.tail" >> "$build_dir/Dockerfile"
docker buildx build --platform linux/arm64 --target sxuff-turn-tail --load \
  --tag "$image" --file "$build_dir/Dockerfile" "$src"
docker image inspect --format 'Built {{.Id}}' "$image"
